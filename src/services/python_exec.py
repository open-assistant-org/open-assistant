"""Python code execution service."""

import contextlib
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Stdout larger than this is saved to TMP_DIR instead of being returned inline.
# Sized for a 200 K-token context window (~25 000 tokens at ~4 chars/token).
_MAX_INLINE_STDOUT_CHARS = 100_000


def _save_large_output(content: str, tmp_dir: Path) -> str:
    """Write *content* to a uniquely-named file in *tmp_dir* and return its path."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    # Detect HTML so the browser can open it directly.
    preview = content.lstrip()[:200].lower()
    ext = ".html" if ("<html" in preview or "<!doctype" in preview) else ".txt"
    filename = f"python_output_{uuid.uuid4().hex[:8]}{ext}"
    out_path = tmp_dir / filename
    out_path.write_text(content, encoding="utf-8")
    return str(out_path)


def python_execute(
    code: str,
    timeout: Optional[int] = 60,
    workdir: Optional[str] = None,
    max_inline_chars: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Execute Python code in a subprocess and return the output.

    The code runs with the same Python interpreter as the main process,
    so installed packages (requests, etc.) are available. stdout and stderr
    are captured separately. Execution is time-bounded by `timeout`.

    The subprocess receives no environment variables and runs in a temporary
    directory, so it cannot access the application database or any secrets.

    Large stdout (> ``max_inline_chars``) is automatically saved to TMP_DIR
    and the returned ``stdout`` field contains only the file path, preventing
    truncation of the tool result by the LLM's context window.

    Args:
        code: Python source code to execute.
        timeout: Maximum wall-clock seconds to allow (default 60, max 120).
        workdir: Optional persistent working directory. When provided, the
            subprocess runs with this as its CWD and files written with
            relative paths persist across calls (used by ``python_agent`` to
            give the sub-agent a stable workspace). When ``None`` (the default,
            used by direct ``python_execute`` calls), an ephemeral temporary
            directory is used and any non-source files it produces are moved
            into TMP_DIR so they survive.
        max_inline_chars: Threshold above which stdout is offloaded to a file.
            Defaults to ``_MAX_INLINE_STDOUT_CHARS`` when ``None``; callers
            holding a settings_service pass ``llm.tool_output_max_chars`` here
            so the limit matches the rest of the system and is user-configurable.

    Returns:
        Dict with keys: stdout, stderr, exit_code, success, output_file (when
        stdout was offloaded), error (on timeout/OS error).
    """
    timeout = min(int(timeout or 60), 120)
    inline_limit = int(max_inline_chars) if max_inline_chars else _MAX_INLINE_STDOUT_CHARS

    logger.info(f"Executing Python code (timeout={timeout}s), length={len(code)} chars")

    try:
        from src.utils.tmp import get_tmp_dir

        _tmp_dir = get_tmp_dir()
        persistent = workdir is not None
        if persistent:
            exec_cwd = workdir
            Path(exec_cwd).mkdir(parents=True, exist_ok=True)
            cwd_ctx = contextlib.nullcontext(exec_cwd)
        else:
            cwd_ctx = tempfile.TemporaryDirectory(prefix="oa_exec_cwd_")

        with cwd_ctx as exec_cwd:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                prefix="oa_exec_",
                delete=False,
                encoding="utf-8",
                dir=exec_cwd,
            ) as tmp:
                tmp.write(code)
                tmp_path = tmp.name

            # Build a minimal, safe environment for the subprocess.
            # Keep PATH so the interpreter and packages resolve, HOME so
            # libraries (matplotlib, etc.) can write caches, and TMP_DIR so
            # the sub-agent can find offloaded data files. WORKSPACE points at
            # the persistent working directory when one is in use.
            safe_env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
                "TMPDIR": tempfile.gettempdir(),
                "TMP_DIR": str(_tmp_dir),
            }
            if persistent:
                safe_env["WORKSPACE"] = str(exec_cwd)
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=safe_env,
                cwd=exec_cwd,
            )

            # Clean up the script we wrote, then (ephemeral mode only) move any
            # deliverable files the script produced into TMP_DIR so they survive
            # the TemporaryDirectory cleanup. In persistent mode files stay in
            # the workspace and accumulate across calls.
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            if not persistent:
                for f in Path(exec_cwd).iterdir():
                    if f.is_file() and f.suffix not in (".py", ".pyc"):
                        dest = _tmp_dir / f.name
                        f.replace(dest)
                        logger.debug("Moved CWD output to TMP_DIR: %s", dest)

        stdout = proc.stdout
        output_file: Optional[str] = None

        if len(stdout) > inline_limit:
            output_file = _save_large_output(stdout, _tmp_dir)
            logger.info(f"stdout too large ({len(stdout)} chars), saved to {output_file}")
            stdout = (
                f"[Output too large to return inline ({len(stdout):,} chars). "
                f"Saved to: {output_file}]"
            )

        result: Dict[str, Any] = {
            "stdout": stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "success": proc.returncode == 0,
        }
        if output_file:
            result["output_file"] = output_file

        if proc.returncode != 0:
            logger.warning(f"Python execution exited with code {proc.returncode}")
        else:
            logger.info("Python execution completed successfully")

        return result

    except subprocess.TimeoutExpired:
        logger.warning(f"Python execution timed out after {timeout}s")
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "success": False,
            "error": f"Execution timed out after {timeout} seconds.",
        }
    except Exception as e:
        logger.error(f"Python execution error: {e}", exc_info=True)
        return {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "success": False,
            "error": str(e),
        }
