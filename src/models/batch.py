"""Models for batch tool execution."""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class BatchToolRequest(BaseModel):
    """Request to execute a tool repeatedly for a list of items.

    Instead of calling a tool N times (one LLM round-trip per item),
    the LLM calls batch_tool once and the backend iterates internally.
    """

    tool_name: str = Field(
        description=(
            "Name of the tool to execute for each item "
            "(e.g. 'google_modify_labels', 'google_trash_email')."
        )
    )
    items: List[Dict[str, Any]] = Field(
        description=(
            "List of argument objects. Each object is a complete set of "
            "arguments for one invocation of the tool. "
            "Example for labelling 3 emails: "
            '[{"message_id":"msg1","add_labels":["Label_1"]},'
            '{"message_id":"msg2","add_labels":["Label_1"]},'
            '{"message_id":"msg3","add_labels":["Label_1"]}]'
        )
    )
