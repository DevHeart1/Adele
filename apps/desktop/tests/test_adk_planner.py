"""
Tests for Google ADK milestone planner integration.
"""
import json
import os
import sys

import pytest

backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, backend_path)

from agent.planner import MilestonePlan
from agent.task_planner import TaskPlanner
from agent.world_state import WorldState
from adk_agent.config import adk_planner_enabled


def test_adk_planner_enabled_respects_env(monkeypatch):
    monkeypatch.setenv("ADELE_USE_ADK_PLANNER", "0")
    assert adk_planner_enabled() is False

    monkeypatch.delenv("ADELE_USE_ADK_PLANNER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    assert adk_planner_enabled() is False

    monkeypatch.setenv("ADELE_USE_ADK_PLANNER", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert adk_planner_enabled() is True


def test_task_planner_adk_flag_override():
    planner = TaskPlanner(provider=None, use_adk=False)
    assert planner._adk_planning_enabled() is False

    planner = TaskPlanner(provider=None, use_adk=True)
    assert planner._adk_planning_enabled() is True


@pytest.mark.asyncio
async def test_create_milestone_plan_uses_adk_when_mocked(monkeypatch):
    sample = {
        "task_summary": "Open browser",
        "needs_clarification": False,
        "milestones": [
            {
                "id": 1,
                "goal": "Open example.com",
                "success_signal": "Browser shows example.com",
                "hint_tools": ["open_url"],
                "depends_on": [],
                "deliverable_key": "opened_url",
            }
        ],
        "final_response": "Done",
    }

    class _FakeAdkPlanner:
        async def plan(self, **kwargs):
            parse_fn = kwargs["parse_fn"]
            plan = parse_fn(json.dumps(sample), kwargs["user_request"])
            plan.source = "adk_milestone_planner"
            return plan

    monkeypatch.setattr(
        "adk_agent.planner.get_adk_milestone_planner",
        lambda: _FakeAdkPlanner(),
    )

    planner = TaskPlanner(provider=None, use_adk=True)
    world = WorldState()
    plan = await planner.create_milestone_plan(
        user_request="open example.com",
        world_state=world,
        available_tools=["open_url"],
    )

    assert isinstance(plan, MilestonePlan)
    assert plan.source == "adk_milestone_planner"
    assert len(plan.milestones) == 1
    assert plan.milestones[0].goal == "Open example.com"


@pytest.mark.asyncio
async def test_create_milestone_plan_falls_back_to_provider(monkeypatch):
    class _FailingAdkPlanner:
        async def plan(self, **kwargs):
            return None

    class _FakeProvider:
        name = "fake"

        async def generate(self, **kwargs):
            payload = {
                "task_summary": "fallback",
                "milestones": [{"id": 1, "goal": "do it"}],
                "final_response": "ok",
            }

            class _Resp:
                text = json.dumps(payload)

            return _Resp()

    monkeypatch.setattr(
        "adk_agent.planner.get_adk_milestone_planner",
        lambda: _FailingAdkPlanner(),
    )

    planner = TaskPlanner(provider=_FakeProvider(), use_adk=True)
    world = WorldState()
    plan = await planner.create_milestone_plan(
        user_request="do something",
        world_state=world,
    )

    assert plan is not None
    assert plan.milestones[0].goal == "do it"
    assert plan.source == "milestone_planner"
