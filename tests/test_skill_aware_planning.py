"""Tests for skill-aware planning and backstory injection improvements.

Covers:
1. Planner._build_skills_context() — skills context for the planning prompt
2. Planner.generate_plan() — accepts a skills parameter
3. MessageHandler._expand_skills_for_plan() — expands skills after plan generation
"""

import inspect
from unittest.mock import MagicMock, patch

import pytest

from src.models.skill import Skill
from src.services.planner import Planner, PlanTracker, PlanStep

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_skill(
    name: str,
    display_name: str = "",
    description: str = "test skill",
    context_prompt: str = "test context",
    tools: list = None,
) -> Skill:
    return Skill(
        id=1,
        name=name,
        display_name=display_name or name.replace("_", " ").title(),
        category="test",
        description=description,
        context_prompt=context_prompt,
        tools=tools or [],
    )


# ---------------------------------------------------------------------------
# Planner._build_skills_context
# ---------------------------------------------------------------------------


class TestBuildSkillsContext:
    """Test the planner's skill context builder."""

    def test_groups_tools_by_skill(self):
        skills = [
            _make_skill(
                "research",
                "Research Agent",
                description="Find information from various sources",
                tools=["web_search", "google_search_emails"],
            ),
            _make_skill(
                "communication",
                "Communication Agent",
                description="Send messages and manage emails",
                tools=["google_send_email", "whatsapp_send_message"],
            ),
        ]
        context = Planner._build_skills_context(skills)

        # Each skill's name, description, and tools should be present
        assert "Research Agent" in context
        assert "Find information from various sources" in context
        assert "web_search" in context
        assert "google_search_emails" in context
        assert "Communication Agent" in context
        assert "google_send_email" in context
        assert "whatsapp_send_message" in context

    def test_empty_skills_returns_empty_string(self):
        assert Planner._build_skills_context([]) == ""

    def test_skill_with_no_tools(self):
        skills = [_make_skill("empty", tools=[])]
        context = Planner._build_skills_context(skills)
        assert "(no tools)" in context

    def test_single_skill(self):
        skills = [
            _make_skill("nav", "Navigator", description="Find places", tools=["search_places"]),
        ]
        context = Planner._build_skills_context(skills)
        assert "Navigator" in context
        assert "Find places" in context
        assert "search_places" in context


# ---------------------------------------------------------------------------
# Planner.generate_plan — signature and backward compatibility
# ---------------------------------------------------------------------------


class TestGeneratePlanSignature:
    """Verify generate_plan accepts the skills parameter."""

    def test_skills_parameter_exists(self):
        sig = inspect.signature(Planner.generate_plan)
        assert "skills" in sig.parameters

    def test_skills_defaults_to_none(self):
        """Backward compatible: skills is optional, defaults to None."""
        sig = inspect.signature(Planner.generate_plan)
        assert sig.parameters["skills"].default is None

    def test_existing_parameters_unchanged(self):
        sig = inspect.signature(Planner.generate_plan)
        param_names = list(sig.parameters.keys())
        assert "llm_client" in param_names
        assert "user_message" in param_names
        assert "tools" in param_names


# ---------------------------------------------------------------------------
# MessageHandler._expand_skills_for_plan
# ---------------------------------------------------------------------------


class TestExpandSkillsForPlan:
    """Test skill expansion after plan generation."""

    def _make_handler(self, enabled_skills):
        """Create a minimal MessageHandler-like object for testing."""
        from src.services.message_handler import MessageHandler

        handler = object.__new__(MessageHandler)

        # Mock dependencies
        handler.skill_repo = MagicMock()
        handler.skill_repo.get_enabled_skills.return_value = enabled_skills
        handler.settings_service = MagicMock()
        handler.settings_service.get_config_with_fallback = MagicMock(
            side_effect=lambda key, default="": default
        )
        handler.tool_registry = MagicMock()
        handler.tool_registry.get_openai_tools.return_value = [
            {"type": "function", "function": {"name": t}}
            for skill in enabled_skills
            for t in skill.tools
        ]

        return handler

    def test_expands_to_include_all_enabled_skills(self):
        research = _make_skill("research", tools=["web_search"])
        communication = _make_skill("communication", tools=["google_send_email"])
        planner_skill = _make_skill("planner", tools=["google_list_events"])

        handler = self._make_handler([research, communication, planner_skill])

        # Only research was selected by keyword matching
        already_selected = [research]
        plan = PlanTracker(
            steps=[
                PlanStep(number=1, description="Search"),
                PlanStep(number=2, description="Send"),
            ],
            raw_plan="1. Search\n2. Send",
        )

        expanded_skills, new_prompt, new_tools = handler._expand_skills_for_plan(
            plan, already_selected, context={}
        )

        # Should now include all 3 skills
        expanded_names = {s.name for s in expanded_skills}
        assert "research" in expanded_names
        assert "communication" in expanded_names
        assert "planner" in expanded_names

    def test_preserves_keyword_selected_skills_first(self):
        research = _make_skill("research", tools=["web_search"])
        communication = _make_skill("communication", tools=["google_send_email"])
        planner_skill = _make_skill("planner", tools=["google_list_events"])

        handler = self._make_handler([research, communication, planner_skill])

        already_selected = [communication, research]  # keyword-matched in this order
        plan = PlanTracker(
            steps=[PlanStep(number=1, description="test")],
            raw_plan="1. test",
        )

        expanded_skills, _, _ = handler._expand_skills_for_plan(plan, already_selected, context={})

        # Keyword-selected skills should come first, in their original order
        assert expanded_skills[0].name == "communication"
        assert expanded_skills[1].name == "research"
        # Additional skills appended after
        assert expanded_skills[2].name == "planner"

    def test_no_duplicates_when_all_already_selected(self):
        research = _make_skill("research", tools=["web_search"])
        communication = _make_skill("communication", tools=["google_send_email"])

        handler = self._make_handler([research, communication])

        already_selected = [research, communication]
        plan = PlanTracker(
            steps=[PlanStep(number=1, description="test")],
            raw_plan="1. test",
        )

        expanded_skills, _, _ = handler._expand_skills_for_plan(plan, already_selected, context={})

        assert len(expanded_skills) == 2
        names = [s.name for s in expanded_skills]
        assert len(set(names)) == len(names)  # no duplicates

    def test_rebuilds_system_prompt_with_all_backstories(self):
        research = _make_skill(
            "research",
            context_prompt="Research instructions here",
            tools=["web_search"],
        )
        communication = _make_skill(
            "communication",
            context_prompt="Communication instructions here",
            tools=["google_send_email"],
        )

        handler = self._make_handler([research, communication])

        plan = PlanTracker(
            steps=[PlanStep(number=1, description="test")],
            raw_plan="1. test",
        )

        # Only research selected by keywords
        _, new_prompt, _ = handler._expand_skills_for_plan(plan, [research], context={})

        # Both backstories should now be in the system prompt
        assert "Research instructions here" in new_prompt
        assert "Communication instructions here" in new_prompt
