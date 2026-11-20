"""Per-tool-call event emitter, so long-running tools can report progress.

The message handler binds an emitter (an async ``emit(event: dict)`` callable
that already carries the SSE ``event_callback`` and the tool's ``call_id``)
around ``execute_tool``. Tools read it with :func:`get_emitter` on the event
loop thread and may post ``tool_progress`` events while they work.
"""

from __future__ import annotations

import contextvars
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from typing import Optional

ToolEmitter = Callable[[dict], Awaitable[None]]

_emitter: contextvars.ContextVar[Optional[ToolEmitter]] = contextvars.ContextVar(
    "tool_event_emitter", default=None
)


def get_emitter() -> Optional[ToolEmitter]:
    """Return the emitter bound for the current tool call, if any."""
    return _emitter.get()


@contextmanager
def bind_emitter(emitter: Optional[ToolEmitter]):
    """Bind *emitter* for the duration of the ``with`` block."""
    token = _emitter.set(emitter)
    try:
        yield
    finally:
        _emitter.reset(token)
