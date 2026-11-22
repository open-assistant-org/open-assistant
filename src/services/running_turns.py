"""Chat turns that run in the background, and the events they have produced so far.

A turn started from the streaming chat endpoint outlives the HTTP connection that
started it: when a client drops (phone locked, tab backgrounded, flaky network) the
turn still finishes and its reply is saved to the conversation. Each turn keeps the
events it emitted, so a client that lost the stream can read what it missed by
polling, and ``/cancel`` can stop a turn on purpose.
"""

import asyncio
from typing import Any, Dict, List, Optional, Set

TERMINAL_EVENTS = ("complete", "error")
# Bounds one turn's log; past it only the closing event is kept.
MAX_EVENTS = 5000
# How long a finished turn's events stay available to a client that comes back for them.
RETAIN_SECONDS = 600


class Run:
    """The events of one turn, in the order they were emitted."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self.finished = False
        self.task: Optional[asyncio.Task] = None

    def record(self, event: Dict[str, Any]) -> None:
        terminal = event.get("type") in TERMINAL_EVENTS
        if terminal:
            self.finished = True
        if terminal or len(self.events) < MAX_EVENTS:
            self.events.append(event)


_by_conversation: Dict[str, Run] = {}
# asyncio only keeps weak references to tasks; nothing awaits these once the client is gone.
_alive: Set[asyncio.Task] = set()


def track(task: asyncio.Task, run: Run, conversation_id: Optional[str] = None) -> None:
    """Keep ``task`` alive until it finishes, and make it findable by conversation."""
    run.task = task
    _alive.add(task)
    if conversation_id:
        _by_conversation[conversation_id] = run

    def _done(done: asyncio.Task) -> None:
        _alive.discard(done)
        run.finished = True
        if not conversation_id:
            return

        def _forget() -> None:
            if _by_conversation.get(conversation_id) is run:
                del _by_conversation[conversation_id]

        asyncio.get_running_loop().call_later(RETAIN_SECONDS, _forget)

    task.add_done_callback(_done)


def get(conversation_id: str) -> Optional[Run]:
    return _by_conversation.get(conversation_id)


def cancel(conversation_id: str) -> bool:
    """Stop the turn running in this conversation. Returns whether one was running."""
    run = _by_conversation.get(conversation_id)
    if run is None or run.task is None or run.task.done():
        return False
    run.task.cancel()
    return True
