"""Models for loop tool execution."""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class LoopStep(BaseModel):
    """A single step in a loop pipeline."""

    tool_name: str = Field(
        description=(
            "Name of the tool to call for this step "
            "(e.g. 'google_get_email', 'notion_create_page')."
        )
    )
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Shared arguments for this step that apply to every item. "
            "Per-item fields from the items list are merged in at runtime, "
            "with item fields taking precedence over these defaults. "
            'Example: {"database_id": "abc123"} for a Notion create step.'
        ),
    )


class LoopToolRequest(BaseModel):
    """Request to execute a pipeline of tools for each item in a list.

    Use this when you need to apply multiple sequential steps to every item,
    e.g. fetch an email then create a Notion page for each one.
    The steps run in order for each item; if a step fails the remaining
    steps for that item are skipped but processing continues with the next item.
    """

    steps: List[LoopStep] = Field(
        description=(
            "Ordered list of steps to execute for each item. "
            "Each step specifies its tool and any shared arguments. "
            "Per-item fields are merged into every step at runtime. "
            "Example: ["
            '{"tool_name":"google_get_email","arguments":{}},'
            '{"tool_name":"notion_create_page","arguments":{"database_id":"abc123"}}'
            "]"
        )
    )
    items: List[Dict[str, Any]] = Field(
        default_factory=lambda: [{}],
        description=(
            "Items to iterate over. Each item is a dict of fields that are merged "
            "into every step's arguments (item fields override step defaults). "
            "Omit or pass [{}] to run the pipeline once with no extra fields. "
            'Example for 2 emails: [{"message_id":"msg1"},{"message_id":"msg2"}]'
        ),
    )
