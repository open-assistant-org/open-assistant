"""Which chat turn the code running right now belongs to.

``handle_message`` binds the conversation and the id of the user message that started
the turn. Tool executions read it when they are written to the audit log, so each
logged action can be tied back to the turn (and the reply) it was part of. Sub-tasks
inherit it through ``asyncio.create_task`` and thread hand-offs, which copy the context.
"""

import contextvars
from typing import NamedTuple, Optional


class Turn(NamedTuple):
    conversation_id: str
    turn_id: str


_current: contextvars.ContextVar[Optional[Turn]] = contextvars.ContextVar("chat_turn", default=None)


def bind_turn(conversation_id: str, turn_id: str) -> None:
    """Make this the current turn for the running task and everything it starts."""
    _current.set(Turn(conversation_id, turn_id))


def get_turn() -> Optional[Turn]:
    return _current.get()
