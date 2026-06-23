"""Lightweight JSON repair helpers for LLM tool-call argument parsing."""

import json
import re
from typing import Any, Dict, List, Optional


def try_repair_json(
    raw: str, hint: Optional[json.JSONDecodeError] = None
) -> Optional[Dict[str, Any]]:
    """Attempt lightweight repairs on common LLM JSON serialisation mistakes.

    *hint* is the original ``JSONDecodeError`` from the caller's ``json.loads``
    call.  When provided it is used to gate repairs so that only the repair
    strategy that matches the reported error is attempted, reducing the risk of
    silently producing a valid-but-wrong result from a structurally broken
    payload.

    Returns the parsed dict on success, or *None* if the input cannot be
    repaired.  Never raises.
    """
    if not raw:
        return None

    text = raw.strip()

    # Strip markdown code fences the model sometimes wraps around JSON.
    fence_match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            text = fence_match.group(1)

    # Replace literal (unescaped) control characters inside string values.
    # Only attempt this when the error is specifically about an invalid control
    # character — applying it to structurally-broken JSON risks misreading
    # string boundaries and silently producing wrong values.
    is_control_char_error = hint is not None and "Invalid control character" in hint.msg
    if is_control_char_error:
        try:
            repaired = _escape_unescaped_control_chars(text)
            if repaired != text:
                return json.loads(repaired)
        except (json.JSONDecodeError, ValueError):
            pass

    # Remove trailing comma before the closing brace/bracket.
    trailing_comma = re.sub(r",\s*([}\]])", r"\1", text)
    if trailing_comma != text:
        try:
            return json.loads(trailing_comma)
        except json.JSONDecodeError:
            pass

    # Balance missing closing braces/brackets. LLMs frequently drop the final
    # one or more closers on deeply nested objects (e.g. emitting
    # ``{"properties": {"State": {"select": {"name": "DONE"}}}`` — three opens,
    # two closes). Appending the missing closers only *adds* to the payload; it
    # never alters existing tokens, and the result is validated by re-parsing,
    # so a wrong repair cannot slip through as valid JSON. Tried with and
    # without trailing-comma stripping to cover both mistakes at once.
    for candidate in (text, trailing_comma):
        balanced = _balance_brackets(candidate)
        if balanced is not None:
            try:
                return json.loads(balanced)
            except json.JSONDecodeError:
                pass

    return None


def _balance_brackets(text: str) -> Optional[str]:
    """Return *text* with any missing closing braces/brackets appended, or
    *None* if the brackets are already balanced or are mismatched in a way
    that simple appending cannot fix (e.g. a stray ``}`` with no opener).

    Characters inside JSON string literals are ignored so that braces or
    brackets appearing in string values do not affect the balance.
    """
    stack: List[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if not stack or stack[-1] != "{":
                return None  # unmatched closer — cannot fix by appending
            stack.pop()
        elif ch == "]":
            if not stack or stack[-1] != "[":
                return None
            stack.pop()

    # An unterminated string or already-balanced brackets are out of scope:
    # appending closers would not produce the value the model intended.
    if in_string or not stack:
        return None

    closers = "".join("}" if opener == "{" else "]" for opener in reversed(stack))
    return text + closers


def _escape_unescaped_control_chars(text: str) -> str:
    """Return *text* with bare newlines/carriage-returns/tabs inside JSON
    string literals replaced by their \\n / \\r / \\t escape sequences."""
    result: List[str] = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                # Keep the escape sequence intact (consume next char too).
                result.append(ch)
                i += 1
                if i < len(text):
                    result.append(text[i])
            elif ch == '"':
                in_string = False
                result.append(ch)
            elif ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            else:
                result.append(ch)
        else:
            if ch == '"':
                in_string = True
            result.append(ch)
        i += 1
    return "".join(result)
