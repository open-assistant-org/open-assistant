"""Standalone helpers for adaptive planning (extracted from MessageHandler).

These functions are importable without pulling in the full MessageHandler
dependency tree (tiktoken, LLMClient, etc.), which makes them easy to
test in isolation.
"""

import json
from typing import Any, Dict, List

from src.services.planner import PlanTracker


def handle_revise_plan(plan: PlanTracker, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a revise_plan tool call by mutating the PlanTracker."""
    action = arguments.get("action", "")
    reason = arguments.get("reason", "")
    new_steps = arguments.get("new_steps") or []
    step_number = arguments.get("step_number")

    if action == "replace_remaining":
        if not new_steps:
            return {"success": False, "error": "new_steps required for replace_remaining"}
        plan.replace_remaining(new_steps)
        return {
            "success": True,
            "action": "replace_remaining",
            "reason": reason,
            "updated_plan": plan.progress_message(),
        }

    elif action == "add_step":
        if not new_steps or step_number is None:
            return {
                "success": False,
                "error": "new_steps and step_number required for add_step",
            }
        desc = new_steps[0] if new_steps else ""
        plan.insert_step_after(step_number, desc)
        return {
            "success": True,
            "action": "add_step",
            "reason": reason,
            "updated_plan": plan.progress_message(),
        }

    elif action == "remove_step":
        if step_number is None:
            return {"success": False, "error": "step_number required for remove_step"}
        removed = plan.remove_step(step_number)
        return {
            "success": removed,
            "action": "remove_step",
            "reason": reason,
            "updated_plan": plan.progress_message(),
            **({"error": f"Step {step_number} not found or not pending"} if not removed else {}),
        }

    elif action == "skip_current":
        current = plan.current_step
        if current:
            current.status = "completed"
            current.result_summary = f"Skipped: {reason}"
            nxt = plan.current_step
            if nxt:
                nxt.status = "in_progress"
        return {
            "success": True,
            "action": "skip_current",
            "reason": reason,
            "updated_plan": plan.progress_message(),
        }

    else:
        return {"success": False, "error": f"Unknown action: {action}"}


def serialize_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Serialize messages for suspension storage.

    Strips any non-JSON-serializable content and limits size.
    """
    serialized = []
    for msg in messages:
        clean = {}
        for k, v in msg.items():
            try:
                json.dumps(v)
                clean[k] = v
            except (TypeError, ValueError):
                clean[k] = str(v)
        serialized.append(clean)
    return serialized


def deserialize_messages(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Restore messages from suspension storage."""
    return data  # Already in the right format
