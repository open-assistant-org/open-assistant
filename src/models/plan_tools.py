"""Models for adaptive planning tools (revise_plan, ask_user, dispatch_task, get_task_result)."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class RevisePlanRequest(BaseModel):
    """Request to revise the remaining steps in the current execution plan.

    Called by the LLM during a plan checkpoint when it determines
    the original plan needs adjustment based on intermediate results.
    """

    action: Literal["replace_remaining", "add_step", "remove_step", "skip_current"] = Field(
        description=(
            "The revision action to perform. One of: "
            "'replace_remaining' (replace all pending steps with new ones), "
            "'add_step' (insert one step after a given step number), "
            "'remove_step' (remove a pending step by number), "
            "'skip_current' (mark current step as skipped and move on)."
        )
    )
    new_steps: Optional[List[str]] = Field(
        default=None,
        description=(
            "For 'replace_remaining': list of new step descriptions to replace "
            "all pending steps. For 'add_step': a single-item list with the "
            "new step description."
        ),
    )
    step_number: Optional[int] = Field(
        default=None,
        description=(
            "For 'add_step': the step number after which to insert. "
            "For 'remove_step': the step number to remove."
        ),
    )
    reason: str = Field(description="Brief explanation of why the plan is being revised.")


class AskUserRequest(BaseModel):
    """Request to pause execution and ask the user a question.

    The LLM calls this tool when it needs clarification or a decision
    from the user before it can proceed with the plan.  Execution is
    suspended and the question is returned to the client.
    """

    question: str = Field(description="The question to ask the user. Should be clear and specific.")
    options: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional list of suggested answer choices. "
            "The user can still provide a free-form answer."
        ),
    )
    context: Optional[str] = Field(
        default=None,
        description=(
            "Brief context about why this question is being asked, "
            "so the user understands what the assistant is working on."
        ),
    )


class DispatchTaskRequest(BaseModel):
    """Request to dispatch an async sub-task.

    The sub-task runs independently with its own planning loop and tool
    access.  The caller receives a task_id immediately and can poll with
    get_task_result to retrieve the outcome.
    """

    description: str = Field(
        description=(
            "Self-contained instruction for the sub-task. Include what data sources "
            "to query, which tools to use, and what output is expected. The sub-task "
            "has no access to the parent conversation history, so be explicit."
        )
    )
    context: str = Field(
        default="",
        description=(
            "Optional context from the current conversation to pass to the sub-task "
            "(e.g. user preferences, intermediate results that inform this work)."
        ),
    )


class GetTaskResultRequest(BaseModel):
    """Request to retrieve the status and result of a dispatched sub-task."""

    task_id: str = Field(description="The task ID returned by dispatch_task.")


class WaitForTasksRequest(BaseModel):
    """Request to block until a set of dispatched sub-tasks have finished.

    Sends a progress notification back to the originating channel (WhatsApp
    or Slack) when the wait starts and a completion summary when all tasks
    have resolved.  No external notification is sent for webui requests —
    the user is watching the UI synchronously.
    """

    task_ids: Optional[List[str]] = Field(
        default=None,
        description=(
            "List of task IDs to wait for.  Omit (or pass an empty list) to "
            "wait for ALL currently-running sub-tasks."
        ),
    )
    timeout_seconds: int = Field(
        default=300,
        description=(
            "Maximum seconds to wait before returning.  Tasks still running "
            "at timeout will be reported with status 'running'."
        ),
    )
    progress_message: str = Field(
        default="Working on background tasks, please wait…",
        description=(
            "Human-readable message sent back to the originating channel when "
            "the wait begins, so the user knows the assistant is still working."
        ),
    )
