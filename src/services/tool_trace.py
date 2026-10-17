"""Persist and replay the tool calls of a turn so follow-ups don't re-fetch data.

A turn's tool exchange (assistant ``tool_calls`` + ``tool`` results) lives only in
the in-memory message list of ``MessageHandler._execute_conversation_loop``.
Without this module just the final assistant text survives, so on the next turn
the model has lost the email body / IDs it fetched and calls the tool again.

``build_tool_trace`` condenses the exchange into compact, self-contained entries
stored in the final assistant message's metadata (``metadata["tool_trace"]``).
``expand_history`` re-inserts them when the next prompt is built:

* **full tier** - the most recent traced turn(s) are replayed as real
  ``tool_calls`` / ``tool`` messages, within a character budget;
* **digest tier** - slightly older turns get a one-line-per-call summary
  appended to the assistant text, plus a ``recall_tool_result`` tool that
  returns the stored result on demand;
* anything older is plain text, exactly as before.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

TRACE_KEY = "tool_trace"
RECALL_TOOL_NAME = "recall_tool_result"

MAX_TRACE_ENTRIES = 40
MAX_ARGUMENT_CHARS = 2000
# Only recent assistant turns are candidates: a trace from 20 turns ago is stale.
FULL_WINDOW_TURNS = 4
DIGEST_WINDOW_TURNS = 8
# Per-entry overhead (ids, role/keys) when estimating the replay size.
_ENTRY_OVERHEAD_CHARS = 120

# Orchestration tools carry no reusable data, and recalling a stored result must not
# store it a second time; replaying either is just noise.
ORCHESTRATION_TOOLS = frozenset(
    {
        "ask_user",
        "revise_plan",
        "dispatch_task",
        "get_task_result",
        "wait_for_tasks",
        RECALL_TOOL_NAME,
    }
)

RECALL_TOOL_DEF: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": RECALL_TOOL_NAME,
        "description": (
            "Return the stored result of a tool call made earlier in this conversation. "
            "Earlier tool calls are listed as '[tool name(args) -> ref=<ref> ...]' in the "
            "history. Use this instead of calling the original tool again when you only "
            "need the data it already returned."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "The ref shown in the earlier tool-call note.",
                }
            },
            "required": ["ref"],
        },
    },
}


def _cap(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}…[truncated, {len(text)} chars]"


def _tool_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content)
    except (TypeError, ValueError):
        return str(content)


def build_tool_trace(
    messages: List[Dict[str, Any]], start_idx: int, max_result_chars: int
) -> List[Dict[str, Any]]:
    """Condense the tool exchange in ``messages[start_idx:]`` into trace entries.

    Each entry is a self-contained call/result pair, so a replayed trace can never
    contain an orphaned ``tool_call`` (which providers reject).
    """
    entries: List[Dict[str, Any]] = []
    step = 0
    pending: Dict[str, Dict[str, Any]] = {}

    for msg in messages[start_idx:]:
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            step += 1
            for tc in msg["tool_calls"]:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                tc_id = tc.get("id") or ""
                if not name or not tc_id or name in ORCHESTRATION_TOOLS:
                    continue
                args = fn.get("arguments") or "{}"
                if not isinstance(args, str):
                    args = json.dumps(args)
                if len(args) > MAX_ARGUMENT_CHARS:
                    args = json.dumps({"_truncated_arguments": args[:500]})
                pending[tc_id] = {"step": step, "name": name, "arguments": args}
        elif role == "tool" and msg.get("tool_call_id") in pending:
            entry = pending.pop(msg["tool_call_id"])
            text = _tool_content_to_text(msg.get("content", ""))
            entry["result"] = _cap(text, max_result_chars)
            entry["chars"] = len(text)
            entries.append(entry)

    return entries[-MAX_TRACE_ENTRIES:]


def _entry_cost(entry: Dict[str, Any]) -> int:
    return len(entry.get("arguments", "")) + len(entry.get("result", "")) + _ENTRY_OVERHEAD_CHARS


def _trace_cost(trace: List[Dict[str, Any]]) -> int:
    return sum(_entry_cost(e) for e in trace)


def _valid_trace(raw: Any) -> Optional[List[Dict[str, Any]]]:
    if not isinstance(raw, list) or not raw:
        return None
    for e in raw:
        if not (
            isinstance(e, dict)
            and isinstance(e.get("name"), str)
            and isinstance(e.get("arguments"), str)
            and isinstance(e.get("result"), str)
            and isinstance(e.get("step"), int)
        ):
            return None
    return raw


def _trace_to_messages(trace: List[Dict[str, Any]], id_prefix: str) -> List[Dict[str, Any]]:
    """Rebuild ``assistant{tool_calls}`` + ``tool`` messages, grouped by loop step."""
    out: List[Dict[str, Any]] = []
    steps: List[int] = []
    for e in trace:
        if e["step"] not in steps:
            steps.append(e["step"])
    n = 0
    for step in steps:
        calls, results = [], []
        for e in trace:
            if e["step"] != step:
                continue
            n += 1
            call_id = f"hist_{id_prefix}_{n}"
            calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": e["name"], "arguments": e["arguments"]},
                }
            )
            results.append({"role": "tool", "tool_call_id": call_id, "content": e["result"]})
        out.append({"role": "assistant", "content": "", "tool_calls": calls})
        out.extend(results)
    return out


def _short_args(arguments: str, limit: int = 60) -> str:
    try:
        parsed = json.loads(arguments)
    except (TypeError, ValueError):
        return arguments[:limit]
    if not isinstance(parsed, dict):
        return str(parsed)[:limit]
    parts = []
    for k, v in list(parsed.items())[:3]:
        v_text = v if isinstance(v, str) else json.dumps(v)
        parts.append(f"{k}={_cap(v_text, limit)}")
    return ", ".join(parts)


def _digest_text(trace: List[Dict[str, Any]], ref_prefix: str) -> Tuple[str, Dict[str, str]]:
    lines, index = [], {}
    for i, e in enumerate(trace, start=1):
        ref = f"{ref_prefix}.{i}"
        index[ref] = e["result"]
        call = f"{e['name']}({_short_args(e['arguments'])})"
        lines.append(f"- {call} -> ref={ref}, {e['chars']} chars")
    text = (
        "[Tool calls made while answering this (results omitted; use recall_tool_result "
        "with a ref to read one):\n" + "\n".join(lines) + "]"
    )
    return text, index


def expand_history(
    history: List[Dict[str, Any]],
    *,
    full_turns: int,
    trace_budget_chars: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, int]]:
    """Turn stored history into LLM messages, re-inserting tool traces.

    ``history`` holds dicts with ``role``, ``content`` and (optionally)
    ``message_id`` / ``metadata``. Returns ``(messages, recall_index, stats)``
    where ``recall_index`` maps digest refs to stored results (non-empty means the
    ``recall_tool_result`` tool should be offered) and ``stats`` reports how many
    turns were replayed in full / as digests and the replayed character count.
    """
    kept = [m for m in history if m.get("role") in ("user", "assistant") and m.get("content")]

    assistant_idx = [i for i, m in enumerate(kept) if m["role"] == "assistant"]
    distance = {i: len(assistant_idx) - 1 - pos for pos, i in enumerate(assistant_idx)}

    mode: Dict[int, str] = {}
    traces: Dict[int, List[Dict[str, Any]]] = {}
    digests: Dict[int, Tuple[str, Dict[str, str]]] = {}
    remaining = max(0, trace_budget_chars)
    full_used = 0
    stats = {"full_turns": 0, "digest_turns": 0, "chars": 0}

    for i in reversed(assistant_idx):  # newest first, so recent turns get the budget
        meta = kept[i].get("metadata")
        trace = _valid_trace(meta.get(TRACE_KEY)) if isinstance(meta, dict) else None
        if trace is None or distance[i] >= DIGEST_WINDOW_TURNS:
            continue
        cost = _trace_cost(trace)
        if full_used < full_turns and distance[i] < FULL_WINDOW_TURNS and cost <= remaining:
            mode[i] = "full"
            traces[i] = trace
            full_used += 1
            remaining -= cost
            stats["full_turns"] += 1
            stats["chars"] += cost
            continue
        digest = _digest_text(trace, f"t{i}")
        if len(digest[0]) <= remaining:
            mode[i] = "digest"
            digests[i] = digest
            remaining -= len(digest[0])
            stats["digest_turns"] += 1
            stats["chars"] += len(digest[0])

    out: List[Dict[str, Any]] = []
    recall_index: Dict[str, str] = {}
    for i, msg in enumerate(kept):
        content = msg["content"]
        if mode.get(i) == "full":
            out.extend(_trace_to_messages(traces[i], f"t{i}"))
        elif mode.get(i) == "digest":
            digest_text, index = digests[i]
            recall_index.update(index)
            content = f"{content}\n\n{digest_text}"
        out.append({"role": msg["role"], "content": content})

    return out, recall_index, stats
