"""Planner service for multi-step request planning and progress tracking."""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.llm_client import LLMClient
from src.models.skill import Skill
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PlanStep:
    """A single step in an execution plan."""

    number: int
    description: str
    status: str = "pending"  # pending | in_progress | completed | failed
    requires_iteration: bool = False  # Step needs multiple tool calls (e.g., per-item)
    result_summary: str = ""  # Brief summary of what this step produced

    def to_dict(self) -> Dict[str, Any]:
        """Serialize step to a dictionary."""
        return {
            "number": self.number,
            "description": self.description,
            "status": self.status,
            "requires_iteration": self.requires_iteration,
            "result_summary": self.result_summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanStep":
        """Deserialize step from a dictionary."""
        return cls(
            number=data["number"],
            description=data["description"],
            status=data.get("status", "pending"),
            requires_iteration=data.get("requires_iteration", False),
            result_summary=data.get("result_summary", ""),
        )


@dataclass
class PlanTracker:
    """Tracks progress through a multi-step plan."""

    steps: List[PlanStep] = field(default_factory=list)
    raw_plan: str = ""
    variables: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_llm_output(cls, plan_text: str) -> "PlanTracker":
        """Parse a numbered plan from LLM output into tracked steps."""
        steps = []
        # Match lines like "1. Do something" or "1) Do something"
        pattern = re.compile(r"^\s*(\d+)[.)]\s+(.+)$", re.MULTILINE)
        for match in pattern.finditer(plan_text):
            description = match.group(2).strip()

            # Detect iterative steps via [repeat] marker or "for each" language
            requires_iteration = False
            if "[repeat]" in description.lower():
                requires_iteration = True
                description = re.sub(
                    r"\s*\[repeat\]\s*", " ", description, flags=re.IGNORECASE
                ).strip()
            elif re.search(
                r"\b(for each|for every|for all|each of the|all of the)\b",
                description,
                re.IGNORECASE,
            ):
                requires_iteration = True

            steps.append(
                PlanStep(
                    number=int(match.group(1)),
                    description=description,
                    requires_iteration=requires_iteration,
                )
            )
        if not steps:
            # Fallback: treat whole text as single step
            steps.append(PlanStep(number=1, description=plan_text.strip()))
        return cls(steps=steps, raw_plan=plan_text)

    @property
    def total(self) -> int:
        return len(self.steps)

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == "completed")

    @property
    def current_step(self) -> Optional[PlanStep]:
        for s in self.steps:
            if s.status in ("pending", "in_progress"):
                return s
        return None

    @property
    def has_iterative_steps(self) -> bool:
        """True if any step in the plan requires iteration."""
        return any(s.requires_iteration for s in self.steps)

    def advance(self) -> Optional[PlanStep]:
        """Mark current step completed and return the next one.

        For iterative steps, this is a no-op — the step stays in_progress
        because the LLM needs multiple tool-call rounds to finish it.
        Use ``complete_current()`` to force-complete an iterative step.
        """
        current = self.current_step
        if current and current.status == "in_progress":
            if current.requires_iteration:
                # Don't auto-advance; the loop will complete it explicitly
                return current
            current.status = "completed"
        nxt = self.current_step
        if nxt:
            nxt.status = "in_progress"
        return nxt

    def complete_current(self) -> Optional[PlanStep]:
        """Force-complete the current step (even if iterative) and move on."""
        for s in self.steps:
            if s.status == "in_progress":
                s.status = "completed"
                break
        nxt = self.current_step
        if nxt:
            nxt.status = "in_progress"
        return nxt

    def start(self) -> Optional[PlanStep]:
        """Mark the first pending step as in_progress."""
        nxt = self.current_step
        if nxt:
            nxt.status = "in_progress"
        return nxt

    def mark_failed(self, reason: str = "") -> Optional[PlanStep]:
        """Mark the current step as failed and return it.

        The plan does NOT auto-advance — the reflection logic decides
        whether to skip, retry, or revise.
        """
        current = self.current_step
        if current and current.status == "in_progress":
            current.status = "failed"
            current.result_summary = reason or "Step failed"
            logger.info(f"Plan step {current.number} marked as failed: {reason}")
        return current

    def insert_step_after(
        self, after_number: int, description: str, requires_iteration: bool = False
    ) -> PlanStep:
        """Insert a new step after the given step number.

        Renumbers all subsequent steps to keep ordering consistent.
        """
        insert_idx = None
        for i, s in enumerate(self.steps):
            if s.number == after_number:
                insert_idx = i + 1
                break
        if insert_idx is None:
            insert_idx = len(self.steps)

        new_step = PlanStep(
            number=after_number + 1,
            description=description,
            requires_iteration=requires_iteration,
        )
        self.steps.insert(insert_idx, new_step)
        self._renumber()
        return new_step

    def remove_step(self, step_number: int) -> bool:
        """Remove a pending step by number. Cannot remove completed/in-progress steps."""
        for i, s in enumerate(self.steps):
            if s.number == step_number and s.status == "pending":
                self.steps.pop(i)
                self._renumber()
                return True
        return False

    def replace_remaining(self, new_steps: List[str]) -> None:
        """Replace all pending steps with a new set of descriptions.

        Completed and in-progress steps are preserved.
        """
        kept = [s for s in self.steps if s.status in ("completed", "in_progress", "failed")]
        next_number = (kept[-1].number + 1) if kept else 1
        for desc in new_steps:
            requires_iteration = bool(
                re.search(
                    r"\b(for each|for every|for all|each of the|all of the)\b",
                    desc,
                    re.IGNORECASE,
                )
            )
            kept.append(
                PlanStep(
                    number=next_number,
                    description=desc,
                    requires_iteration=requires_iteration,
                )
            )
            next_number += 1
        self.steps = kept
        self._renumber()
        # Update raw_plan to reflect the revision
        self.raw_plan = "\n".join(f"{s.number}. {s.description}" for s in self.steps)

    def _renumber(self) -> None:
        """Re-assign sequential step numbers after mutations."""
        for i, s in enumerate(self.steps):
            s.number = i + 1

    def progress_message(self) -> str:
        """Generate a progress status string for injection into the conversation."""
        parts = []
        for s in self.steps:
            if s.status == "completed":
                mark = "[done]"
            elif s.status == "in_progress":
                mark = "[current]"
            elif s.status == "failed":
                mark = "[FAILED]"
            else:
                mark = "[pending]"
            parts.append(f"  {s.number}. {mark} {s.description}")
        header = f"Plan progress ({self.completed_count}/{self.total} steps completed):"
        return header + "\n" + "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the full tracker to a dictionary for suspension."""
        return {
            "steps": [s.to_dict() for s in self.steps],
            "raw_plan": self.raw_plan,
            "variables": self.variables,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanTracker":
        """Restore a tracker from a serialized dictionary."""
        steps = [PlanStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            steps=steps, raw_plan=data.get("raw_plan", ""), variables=data.get("variables", {})
        )


class Planner:
    """Decides whether a request needs planning and generates execution plans."""

    @staticmethod
    def should_plan(message: str, selected_skills: List[Skill]) -> bool:
        """
        Heuristic to decide whether the request benefits from an explicit
        planning phase before tool execution.

        Returns True when the message appears to involve multiple sequential
        steps, cross-integration work, or explicit sequencing language.
        """
        # 0. Short / simple messages never need planning
        if len(message.strip()) < 80:
            return False

        # 1. Explicit sequencing language
        sequencing_patterns = [
            r"\b(first|then|after that|next|finally|step \d|and then)\b",
            r"\b(before|once .+ is done|when .+ finishes)\b",
            r"\b(plan|steps|workflow|sequence|procedure)\b",
        ]
        sequencing_hits = sum(
            1 for p in sequencing_patterns if re.search(p, message, re.IGNORECASE)
        )
        if sequencing_hits >= 2:
            return True

        # 2. Multiple distinct skill categories involved (only for non-trivial messages)
        if len(message) > 80:
            unique_services = set()
            for skill in selected_skills:
                for tool_name in skill.tools:
                    # Derive service from tool name prefix
                    prefix = tool_name.split("_")[0]
                    unique_services.add(prefix)
            if len(unique_services) >= 3:
                return True

        # 3. Long messages with multiple verbs / requests
        if len(message) > 300:
            # Count imperative-style verbs as a rough proxy
            action_verbs = re.findall(
                r"\b(search|find|send|create|check|read|write|browse|get|update|"
                r"delete|schedule|list|upload|download|compose|navigate|open|go to)\b",
                message,
                re.IGNORECASE,
            )
            if len(action_verbs) >= 3:
                return True

        return False

    # Keywords in tool results that suggest the step outcome deserves reflection.
    REFLECTION_TRIGGERS = [
        "error",
        "failed",
        "not found",
        "no results",
        "denied",
        "unauthorized",
        "ambiguous",
        "multiple matches",
        "did you mean",
        "could not",
        "unable to",
        "timeout",
        "rate limit",
        "0 results",
        "empty",
    ]

    @staticmethod
    def should_reflect(tool_results: List[Dict[str, Any]], plan: "PlanTracker") -> bool:
        """Decide whether the LLM should reflect on the plan after the latest step.

        Reflection is triggered when:
        - Any tool result contains keywords suggesting failure / ambiguity
        - The current step was marked as failed
        - We've just passed the halfway point of the plan (sanity check)
        """
        if not plan or plan.total <= 1:
            return False

        # Check if any step recently failed (not yet superseded by a new plan)
        if any(s.status == "failed" for s in plan.steps):
            return True

        # Check for concerning patterns in tool results
        for result in tool_results:
            content = result.get("content", "")

            # If the result is JSON with an explicit success indicator, skip
            # keyword scanning — the tool is reporting success and keywords
            # like "error_count" or "empty" are data, not failures.
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict) and (
                    parsed.get("success") is True or parsed.get("status") == "success"
                ):
                    continue
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

            content_lower = content.lower()
            for trigger in Planner.REFLECTION_TRIGGERS:
                if trigger in content_lower:
                    logger.debug(f"Reflection triggered by keyword '{trigger}' in tool result")
                    return True

        # Reflect at the halfway mark as a sanity checkpoint
        if plan.completed_count > 0 and plan.completed_count == plan.total // 2:
            logger.debug("Reflection triggered at plan halfway point")
            return True

        return False

    @staticmethod
    def build_reflection_prompt(
        plan: "PlanTracker", latest_tool_results: List[Dict[str, Any]]
    ) -> str:
        """Build a reflection prompt for the LLM to evaluate and optionally revise the plan.

        This is injected as a user message into the conversation so the LLM
        can decide whether to continue as-is, call ``revise_plan`` to adjust,
        or call ``ask_user`` to request clarification.
        """
        progress = plan.progress_message()

        # Summarize latest results (truncate to avoid blowing up context)
        result_summaries = []
        for r in latest_tool_results[-3:]:  # last 3 results max
            content = r.get("content", "")
            if len(content) > 500:
                content = content[:500] + "..."
            result_summaries.append(content)
        results_text = "\n".join(result_summaries) if result_summaries else "(no results)"

        return (
            "[Plan checkpoint] Review the plan and latest results before continuing.\n\n"
            f"{progress}\n\n"
            f"Latest tool results:\n{results_text}\n\n"
            "Based on these results, decide your next action:\n"
            "- If the plan is still valid, continue executing the next step.\n"
            "- If the plan needs adjustment, call the revise_plan tool to modify remaining steps.\n"
            "- If you need clarification from the user, call the ask_user tool.\n"
            "- If a step failed and should be retried differently, revise the plan accordingly.\n"
            "Do NOT repeat this checkpoint text in your response."
        )

    @staticmethod
    def _build_skills_context(skills: List[Skill]) -> str:
        """Build a concise summary of available skills and their tools for the planner.

        Groups tools by skill so the planner understands which capabilities belong
        together and can reference the right tools for each step.
        """
        if not skills:
            return ""

        parts = []
        for skill in skills:
            tool_list = ", ".join(skill.tools) if skill.tools else "(no tools)"
            parts.append(f"- {skill.display_name}: {skill.description}\n" f"  Tools: {tool_list}")
        return "\n".join(parts)

    @staticmethod
    async def generate_plan(
        llm_client: LLMClient,
        user_message: str,
        tools: List[Dict[str, Any]],
        skills: Optional[List[Skill]] = None,
    ) -> PlanTracker:
        """
        Ask the LLM to produce a numbered step plan before executing tools.

        When *skills* are provided the planning prompt includes each skill's
        description and tool list so the planner can make informed decisions
        about which tools to use for each step.

        Uses a dedicated planning prompt with lower temperature.
        """
        tool_names = [t["function"]["name"] for t in tools]

        # Build skill-aware context when skills are available
        skills_section = ""
        if skills:
            skills_context = Planner._build_skills_context(skills)
            skills_section = (
                "\nAvailable skills and their tools:\n"
                f"{skills_context}\n\n"
                "When planning, leverage the right skill's tools for each step. "
                "For example, use research tools for information retrieval, "
                "communication tools for sending messages, etc.\n"
            )

        planning_prompt = (
            "You are a planning assistant. The user has made a request that requires "
            "multiple steps. Analyze the request and produce a concise numbered plan "
            "(1-10 steps). Each step should be a single clear action.\n\n"
            f"{skills_section}"
            "Rules:\n"
            "- Only include steps that are actually needed\n"
            "- Reference the specific tools you would use (available: "
            f"{', '.join(tool_names)})\n"
            "- If a step needs to be repeated for multiple items (e.g. label each "
            "email, trash several messages, move many files), prefix it with [repeat] "
            "and mention using batch_tool for efficiency\n"
            "- Output ONLY the numbered list, nothing else\n"
        )

        messages = [
            {"role": "system", "content": planning_prompt},
            {"role": "user", "content": user_message},
        ]

        response = llm_client.complete(
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
        )

        plan_text = response.choices[0].message.content or ""
        logger.info(f"Generated plan:\n{plan_text}")

        return PlanTracker.from_llm_output(plan_text)
