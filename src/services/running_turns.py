"""Chat turns that run in the background.

A turn started from the streaming chat endpoint outlives the HTTP connection that
started it: when a client drops (phone locked, tab backgrounded, flaky network) the
turn still finishes and its reply is saved to the conversation. Turns are tracked here
by conversation so that ``/cancel`` can stop one on purpose and clients can ask whether
one is still running.
"""

import asyncio
from typing import Dict, Optional, Set

_by_conversation: Dict[str, asyncio.Task] = {}
# asyncio only keeps weak references to tasks; nothing awaits these once the client is gone.
_alive: Set[asyncio.Task] = set()


def track(task: asyncio.Task, conversation_id: Optional[str] = None) -> None:
    """Keep ``task`` alive until it finishes, and make it findable by conversation."""
    _alive.add(task)
    if conversation_id:
        _by_conversation[conversation_id] = task

    def _forget(done: asyncio.Task) -> None:
        _alive.discard(done)
        if conversation_id and _by_conversation.get(conversation_id) is done:
            del _by_conversation[conversation_id]

    task.add_done_callback(_forget)


def is_running(conversation_id: str) -> bool:
    task = _by_conversation.get(conversation_id)
    return task is not None and not task.done()


def cancel(conversation_id: str) -> bool:
    """Stop the turn running in this conversation. Returns whether one was running."""
    task = _by_conversation.get(conversation_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True
