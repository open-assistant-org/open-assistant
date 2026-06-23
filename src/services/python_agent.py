"""Autonomous Python sub-agent.

Delegates a multi-step Python task to an inner LLM loop that writes, runs,
and refines Python code until the goal is met, returning only a compact
summary plus any output filepaths to the caller.

The sub-agent works like a small coding agent: it gets a stable per-run
**workspace** directory and can inspect inputs and verify its own outputs with
lightweight ``read_file`` / ``list_files`` / ``write_file`` tools instead of
writing throwaway scripts. Each ``python_execute`` call is still a fresh
subprocess (variables/imports do not carry over), but it runs *inside the
workspace*, so files written with relative paths persist and accumulate across
iterations.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.core.tools.schema import pydantic_to_json_schema
from src.models.python_exec import PythonExecuteRequest
from src.services.python_exec import python_execute
from src.utils.json_utils import try_repair_json
from src.utils.logger import get_logger

logger = get_logger(__name__)


# Available packages (kept in sync with the python_execute tool description).
_AVAILABLE_PACKAGES = (
    "'requests' (HTTP), 'pandas' (dataframes/CSV/Excel), 'numpy' (numerical), "
    "'scipy' (scientific), 'matplotlib' (static charts), 'seaborn' (statistical), "
    "'plotly' (interactive HTML — use plotly.io.write_html()), 'kaleido' (export plotly to PNG/SVG), "
    "'jinja2' (HTML templating), 'openpyxl' (.xlsx), 'yfinance' (market data), 'markdown'."
)

_SYSTEM_PROMPT_TEMPLATE = """You are a Python analysis sub-agent. Your job is to accomplish the \
given goal autonomously, working in a stable workspace like a focused coding agent.

Available libraries: standard library plus {packages}

Your workspace is `{workspace}`. It is your current working directory and it persists for the \
whole run: files you write there with relative paths (e.g. `open("data.csv", "w")`) stay \
available to later steps. Save every deliverable the caller might want (datasets, charts, \
reports, downloads) in the workspace.

Your tools:
- `plan` — call this FIRST, before anything else: list your numbered steps and your role.
- `python_execute` — run a Python script in a fresh subprocess inside the workspace. No \
variables or imports carry over between calls, so chain related logic into one script per call.
- `read_file` — read a file (workspace files, or an input file under TMP_DIR that the goal \
points you to). Use this to inspect inputs and to VERIFY your own outputs — do not print-debug \
with python_execute when a quick read will do.
- `list_files` — list what is in the workspace. Use it to check what you have produced.
- `write_file` — write a text deliverable (report, HTML, CSV, JSON) directly, without a \
python_execute round-trip. Prefer this for assembling final text/markup.
- `finish` — end the run and return results to the caller.

How to work (explore → plan → act → verify):
1. If the goal references an input file, `read_file` it first to understand its shape.
2. `plan` your steps.
3. Act: write/run code or `write_file` deliverables. To pass data between python_execute calls, \
write it to the workspace and read it back in the next call.
4. Verify before finishing: `list_files` and/or `read_file` to confirm every deliverable exists \
and looks right. Then `finish`.

Reports & charts:
- For interactive charts, use plotly and `plotly.io.write_html()`.
- Never print large HTML/JSON to stdout — write it to a workspace file instead.

Output handling:
- stdout larger than ~{inline_limit:,} characters is auto-saved to a file and the path is \
returned instead of the text. Prefer writing large outputs to the workspace directly.
- If a tool result has an `output_file` key, that file already holds the large output — include \
it in `finish(output_files=[...])` if it is your deliverable; do not regenerate it.

Recovering from errors:
- If a python_execute call fails, read the stderr/traceback and fix the script in the next call. \
Do not re-run the exact same script.
- If three python_execute calls in a row fail with the same error, call `finish` with \
`success=false` and a short `error`.

Finishing correctly:
You MUST call `finish` when done — do not just describe what you did in a plain message. Pass:
- `summary`: 1–3 sentences on what was accomplished.
- `output_files`: absolute paths of deliverables you wrote (they must actually exist).
- `success`: true if the goal was met, false otherwise.
- `error`: short explanation when `success` is false.

Every response must call a tool. If there is nothing left to do, call `finish` immediately."""


def _build_system_prompt(workspace: str, inline_limit: int) -> str:
    return _SYSTEM_PROMPT_TEMPLATE.format(
        packages=_AVAILABLE_PACKAGES,
        workspace=workspace,
        inline_limit=inline_limit,
    )


def _build_inner_tools() -> List[Dict[str, Any]]:
    """Tool schemas exposed to the sub-agent (OpenAI function-calling format)."""
    python_execute_params = pydantic_to_json_schema(PythonExecuteRequest)
    plan_params = {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered steps to accomplish the goal.",
            },
            "role": {
                "type": "string",
                "description": "Your working role, e.g. 'data analyst', 'HTML report maker'.",
            },
        },
        "required": ["steps", "role"],
    }
    read_file_params = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "File to read. Relative paths resolve inside the workspace; absolute "
                    "paths are allowed only inside the workspace or TMP_DIR (input files)."
                ),
            },
            "max_bytes": {
                "type": "integer",
                "description": "Max characters to return (default 20000). Larger files are truncated.",
            },
            "start_line": {
                "type": "integer",
                "description": "Optional 1-indexed first line to return (inclusive).",
            },
            "end_line": {
                "type": "integer",
                "description": "Optional 1-indexed last line to return (inclusive).",
            },
        },
        "required": ["path"],
    }
    list_files_params = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory to list, relative to the workspace. Defaults to the workspace root.",
            },
        },
    }
    write_file_params = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Destination file, relative to the workspace (absolute paths must stay inside it).",
            },
            "content": {
                "type": "string",
                "description": "Text content to write (overwrites any existing file).",
            },
        },
        "required": ["path", "content"],
    }
    finish_params = {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "1–3 sentence description of what was accomplished.",
            },
            "output_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Absolute paths of files written in the workspace that the caller "
                    "may want to use. They must exist. Empty list if no files were produced."
                ),
            },
            "success": {
                "type": "boolean",
                "description": "True if the goal was achieved, false otherwise.",
            },
            "error": {
                "type": "string",
                "description": "Short explanation if success is false. Omit on success.",
            },
        },
        "required": ["summary", "success"],
    }
    return [
        {
            "type": "function",
            "function": {
                "name": "plan",
                "description": (
                    "Call this FIRST, before any other tool. "
                    "Outline the numbered steps you will take and name your working role."
                ),
                "parameters": plan_params,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "python_execute",
                "description": (
                    "Run a Python script in a fresh subprocess inside the workspace. Returns "
                    "stdout, stderr, exit_code, success. No state carries between calls; persist "
                    "data as workspace files."
                ),
                "parameters": python_execute_params,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": (
                    "Read a text file to inspect an input or verify your own output, without "
                    "writing a python_execute script."
                ),
                "parameters": read_file_params,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files in the workspace (with sizes) to see what you have produced.",
                "parameters": list_files_params,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": (
                    "Write a text deliverable (report, HTML, CSV, JSON) directly to the workspace, "
                    "skipping a python_execute round-trip."
                ),
                "parameters": write_file_params,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "finish",
                "description": (
                    "Terminate the sub-agent loop and return results to the caller. "
                    "Call this when the goal has been met (or definitively cannot be met)."
                ),
                "parameters": finish_params,
            },
        },
    ]


# ---------------------------------------------------------------------------
# Workspace file helpers
# ---------------------------------------------------------------------------


def _resolve_safe_path(raw_path: str, workspace: Path, tmp_dir: Path, *, for_write: bool) -> Path:
    """Resolve *raw_path* and ensure it stays inside allowed roots.

    Reads may target the run workspace or TMP_DIR (where the main loop offloads
    large input files). Writes are restricted to the workspace. Anything else —
    application source, env files, secrets — is rejected.
    """
    if not raw_path or not str(raw_path).strip():
        raise ValueError("path must not be empty")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve()

    workspace_root = workspace.resolve()
    allowed_roots = [workspace_root] if for_write else [workspace_root, tmp_dir.resolve()]
    if not any(resolved == root or resolved.is_relative_to(root) for root in allowed_roots):
        scope = "the workspace" if for_write else "the workspace or TMP_DIR"
        raise ValueError(f"path {raw_path!r} is outside {scope} and is not allowed")
    return resolved


def _tool_read_file(arguments: Dict[str, Any], workspace: Path, tmp_dir: Path) -> Dict[str, Any]:
    try:
        path = _resolve_safe_path(arguments.get("path", ""), workspace, tmp_dir, for_write=False)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    if not path.is_file():
        return {"success": False, "error": f"File not found: {path}"}

    max_bytes = int(arguments.get("max_bytes") or 20000)
    start_line = arguments.get("start_line")
    end_line = arguments.get("end_line")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"success": False, "error": f"Could not read file: {e}"}

    truncated = False
    if start_line is not None or end_line is not None:
        lines = text.splitlines()
        start = max(int(start_line or 1), 1)
        end = int(end_line) if end_line is not None else len(lines)
        text = "\n".join(lines[start - 1 : end])
    if len(text) > max_bytes:
        text = text[:max_bytes]
        truncated = True

    result: Dict[str, Any] = {"success": True, "path": str(path), "content": text}
    if truncated:
        result["truncated"] = True
        result["hint"] = (
            f"Output truncated to {max_bytes} chars. Use start_line/end_line or a larger "
            "max_bytes to read more."
        )
    return result


def _tool_list_files(arguments: Dict[str, Any], workspace: Path, tmp_dir: Path) -> Dict[str, Any]:
    sub = arguments.get("path") or "."
    try:
        target = _resolve_safe_path(sub, workspace, tmp_dir, for_write=False)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    if not target.exists():
        return {"success": True, "path": str(target), "files": []}
    if target.is_file():
        return {
            "success": True,
            "path": str(target),
            "files": [{"path": target.name, "bytes": target.stat().st_size}],
        }

    files: List[Dict[str, Any]] = []
    for p in sorted(target.rglob("*")):
        if p.is_file():
            try:
                rel = str(p.relative_to(target))
                files.append({"path": rel, "bytes": p.stat().st_size})
            except OSError:
                continue
        if len(files) >= 500:
            break
    return {"success": True, "path": str(target), "files": files}


def _tool_write_file(arguments: Dict[str, Any], workspace: Path, tmp_dir: Path) -> Dict[str, Any]:
    try:
        path = _resolve_safe_path(arguments.get("path", ""), workspace, tmp_dir, for_write=True)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    content = arguments.get("content")
    if content is None:
        return {"success": False, "error": "content is required"}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding="utf-8")
    except OSError as e:
        return {"success": False, "error": f"Could not write file: {e}"}
    return {"success": True, "path": str(path), "bytes": len(str(content).encode("utf-8"))}


def _scan_output_files(workspace: Path, since_mtime: float) -> List[str]:
    """Return absolute paths of deliverable files in the workspace.

    Skips the auto-saved ``python_output_*.txt`` stdout-overflow files (kept
    .html ones — those are deliberate deliverables) and leftover .py scripts.
    """
    if not workspace.exists():
        return []
    found: List[str] = []
    for path in workspace.rglob("*"):
        try:
            if not path.is_file() or path.stat().st_mtime < since_mtime:
                continue
            if path.name.startswith("python_output_") and path.suffix == ".txt":
                continue
            if path.suffix in (".py", ".pyc"):
                continue
            found.append(str(path.resolve()))
        except OSError:
            continue
    return sorted(found)


def _stdout_tail(text: str, limit: int = 500) -> str:
    if len(text) <= limit:
        return text
    return "…" + text[-limit:]


async def _complete_with_retry(llm_client, messages, tools, retries: int = 2):
    """Call the LLM, retrying transient failures with exponential backoff."""
    delay = 1.0
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            return await asyncio.to_thread(
                llm_client.complete_with_tools, messages=messages, tools=tools
            )
        except Exception as e:  # noqa: BLE001 - retried/re-raised below
            last_exc = e
            if attempt < retries:
                logger.warning(
                    "python_agent LLM call failed (attempt %d/%d): %s; retrying in %.0fs",
                    attempt + 1,
                    retries + 1,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)
                delay *= 2
    assert last_exc is not None
    raise last_exc


async def python_agent(
    goal: str,
    context: Optional[str] = None,
    max_iterations: int = 8,
    settings_service=None,
) -> Dict[str, Any]:
    """Run an autonomous Python sub-agent until the goal is met.

    Args:
        goal: Natural-language description of what to accomplish.
        context: Optional extra facts the sub-agent needs (file paths, URLs, etc.).
        max_iterations: Cap on inner LLM↔tool turns (1–20).
        settings_service: SettingsService instance used to build the LLM client.

    Returns:
        Dict with keys: summary, output_files, final_stdout_tail, iterations,
        success, error (when applicable).
    """
    if not settings_service:
        raise ValueError("settings_service is required for python_agent")

    max_iterations = max(1, min(int(max_iterations or 8), 20))

    from src.core.llm_client import LLMClient, LLMConfig

    llm_config = LLMConfig.from_settings(settings_service)
    llm_client = LLMClient(llm_config)

    try:
        max_inline_chars = int(
            settings_service.get_config_with_fallback("llm.tool_output_max_chars", 300000)
        )
    except (TypeError, ValueError):
        max_inline_chars = 300000

    from src.utils.tmp import get_tmp_dir

    tmp_dir = get_tmp_dir()
    workspace = tmp_dir / f"agent_{uuid4().hex[:8]}"
    workspace.mkdir(parents=True, exist_ok=True)
    loop_started = time.time()

    inner_tools = _build_inner_tools()
    user_prompt = f"Goal:\n{goal.strip()}"
    if context:
        user_prompt += f"\n\nContext:\n{context.strip()}"

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _build_system_prompt(str(workspace), max_inline_chars)},
        {"role": "user", "content": user_prompt},
    ]

    logger.info(
        "python_agent start: workspace=%s goal=%r context_len=%d max_iterations=%d",
        workspace,
        goal[:120],
        len(context or ""),
        max_iterations,
    )

    last_stdout = ""
    iterations = 0
    finish_args: Optional[Dict[str, Any]] = None

    # Stuck-detection state
    code_signatures: List[str] = []
    consecutive_failures = 0
    last_error_sig = ""
    finish_rejections = 0

    while iterations < max_iterations:
        iterations += 1
        logger.info("python_agent iteration=%d (of %d)", iterations, max_iterations)

        try:
            response = await _complete_with_retry(llm_client, messages, inner_tools)
        except Exception as e:
            logger.error("python_agent LLM call failed at iteration %d: %s", iterations, e)
            return {
                "summary": "",
                "output_files": _scan_output_files(workspace, loop_started),
                "final_stdout_tail": _stdout_tail(last_stdout),
                "iterations": iterations,
                "success": False,
                "error": f"LLM call failed: {e}",
            }

        response_message = response.choices[0].message if response.choices else None
        tool_calls = getattr(response_message, "tool_calls", None) if response_message else None

        if not tool_calls:
            # The sub-agent emitted a plain message instead of calling a tool.
            # Treat it as an implicit finish so the loop can't hang.
            implicit_summary = (
                response_message.content
                if response_message and response_message.content
                else "Sub-agent stopped without calling finish."
            )
            logger.warning(
                "python_agent: implicit finish (no tool_calls) at iteration %d", iterations
            )
            finish_args = {
                "summary": implicit_summary,
                "success": True,
                "output_files": [],
            }
            break

        # Append the assistant message exactly as the main loop does.
        assistant_msg = response_message.model_dump()
        if assistant_msg.get("content") is None:
            assistant_msg["content"] = ""
        messages.append(assistant_msg)

        finished = False
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            tool_call_id = tool_call.id

            raw_args = tool_call.function.arguments or "{}"
            try:
                arguments = json.loads(raw_args)
            except json.JSONDecodeError as exc:
                repaired = try_repair_json(raw_args, hint=exc)
                if repaired is not None:
                    logger.debug(
                        "python_agent: repaired malformed JSON for %s (original error: %s)",
                        tool_name,
                        exc,
                    )
                    arguments = repaired
                else:
                    logger.warning(
                        "python_agent: could not parse arguments for tool '%s' "
                        "(JSONDecodeError at pos %d: %s) — raw: %r",
                        tool_name,
                        exc.pos,
                        exc.msg,
                        raw_args[:200],
                    )
                    hint = (
                        f"JSON parse error at position {exc.pos}: {exc.msg}. "
                        "Make sure all string values are properly JSON-escaped "
                        '(e.g. newlines as \\n, backslashes as \\\\, quotes as \\"). '
                        "Re-emit the tool call with valid JSON."
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": json.dumps({"success": False, "error": hint}),
                        }
                    )
                    continue

            if tool_name == "finish":
                # Verify declared deliverables exist before accepting (once).
                declared = arguments.get("output_files") or []
                missing = [p for p in declared if not Path(str(p)).exists()]
                if missing and finish_rejections < 1:
                    finish_rejections += 1
                    logger.info("python_agent: finish rejected, missing files: %s", missing)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": json.dumps(
                                {
                                    "success": False,
                                    "error": (
                                        "These declared output_files do not exist: "
                                        f"{missing}. Create them (or drop them from "
                                        "output_files), then call finish again. Use "
                                        "list_files to check the workspace."
                                    ),
                                }
                            ),
                        }
                    )
                    continue
                finish_args = arguments
                finished = True
                break

            if tool_name == "plan":
                plan_steps = arguments.get("steps", [])
                plan_role = arguments.get("role", "")
                plan_text = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(plan_steps))
                logger.info("python_agent.plan role=%r steps=%d", plan_role, len(plan_steps))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(
                            {
                                "acknowledged": True,
                                "role": plan_role,
                                "plan": plan_text,
                                "instruction": (
                                    f"Plan accepted. You are acting as: {plan_role}. Begin step 1."
                                ),
                            }
                        ),
                    }
                )
                continue

            if tool_name == "read_file":
                result = _tool_read_file(arguments, workspace, tmp_dir)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(result),
                    }
                )
                continue

            if tool_name == "list_files":
                result = _tool_list_files(arguments, workspace, tmp_dir)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(result),
                    }
                )
                continue

            if tool_name == "write_file":
                result = _tool_write_file(arguments, workspace, tmp_dir)
                logger.info(
                    "python_agent.write_file path=%r success=%s",
                    arguments.get("path"),
                    result.get("success"),
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(result),
                    }
                )
                continue

            if tool_name == "python_execute":
                code = arguments.get("code", "")
                timeout = arguments.get("timeout", 60)
                logger.info(
                    "python_agent.python_execute iteration=%d code_len=%d timeout=%s",
                    iterations,
                    len(code),
                    timeout,
                )
                result = await asyncio.to_thread(
                    python_execute,
                    code=code,
                    timeout=timeout,
                    workdir=str(workspace),
                    max_inline_chars=max_inline_chars,
                )
                last_stdout = result.get("stdout") or last_stdout

                # Hint the agent when large output was auto-saved, so it doesn't retry.
                if result.get("output_file"):
                    result["hint"] = (
                        f"Large output auto-saved to {result['output_file']}. "
                        "If this is the deliverable, include it in finish(output_files=[...])."
                    )

                # Code-level stuck detection: enforce the 3-consecutive-failure rule.
                if not result.get("success", True):
                    consecutive_failures += 1
                    err_sig = (result.get("stderr") or "")[:200]
                    if err_sig and err_sig == last_error_sig and consecutive_failures >= 3:
                        logger.warning(
                            "python_agent: same error repeated %d times, aborting",
                            consecutive_failures,
                        )
                        return {
                            "summary": "",
                            "output_files": _scan_output_files(workspace, loop_started),
                            "final_stdout_tail": _stdout_tail(last_stdout),
                            "iterations": iterations,
                            "success": False,
                            "error": (
                                f"Aborted: same error repeated {consecutive_failures} times. "
                                f"Last error: {err_sig}"
                            ),
                        }
                    last_error_sig = err_sig
                else:
                    consecutive_failures = 0
                    last_error_sig = ""

                # Warn when near-identical code is tried repeatedly.
                code_sig = code[:200]
                code_signatures.append(code_sig)
                if len(code_signatures) >= 3 and len(set(code_signatures[-3:])) == 1:
                    result["stuck_warning"] = (
                        "Your last 3 scripts start identically. "
                        "Try a fundamentally different approach."
                    )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": json.dumps(result),
                    }
                )
                continue

            # Unknown tool.
            logger.warning("python_agent: unknown tool %r requested", tool_name)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(
                        {
                            "success": False,
                            "error": (
                                f"Tool {tool_name!r} is not available. Use plan, python_execute, "
                                "read_file, list_files, write_file, or finish."
                            ),
                        }
                    ),
                }
            )

        if finished:
            break

    if finish_args is None:
        # Hit the iteration cap.
        logger.warning("python_agent: max_iterations (%d) reached without finish", max_iterations)
        return {
            "summary": "",
            "output_files": _scan_output_files(workspace, loop_started),
            "final_stdout_tail": _stdout_tail(last_stdout),
            "iterations": iterations,
            "success": False,
            "error": (
                f"Sub-agent did not call finish within {max_iterations} iterations. "
                "Increase max_iterations or simplify the goal."
            ),
        }

    # Merge sub-agent-declared output_files with anything new in the workspace
    # (so the caller still gets paths even if the sub-agent forgot to list them).
    declared = finish_args.get("output_files") or []
    scanned = _scan_output_files(workspace, loop_started)
    merged: List[str] = []
    for path in list(declared) + scanned:
        if path and path not in merged:
            merged.append(path)

    success = bool(finish_args.get("success", True))
    result: Dict[str, Any] = {
        "summary": finish_args.get("summary", "").strip(),
        "output_files": merged,
        "final_stdout_tail": _stdout_tail(last_stdout),
        "iterations": iterations,
        "success": success,
    }
    error = finish_args.get("error")
    if error or not success:
        result["error"] = error or "Sub-agent reported failure without an error message."

    logger.info(
        "python_agent done: workspace=%s iterations=%d success=%s output_files=%d",
        workspace,
        iterations,
        success,
        len(merged),
    )
    return result
