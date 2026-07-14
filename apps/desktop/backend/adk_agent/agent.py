"""
ADELE — Google ADK agent definitions.

- ``build_planner_agent``: milestone JSON planner (no tool calls during planning).
- ``build_root_agent``: tool-equipped agent for Agent Runtime deployment.
"""

from __future__ import annotations

from google.adk.agents import Agent
from google.genai import types

from adk_agent.config import adk_action_model, adk_planner_model
from adk_agent.tool_adapters import ADELE_ADK_TOOLS

PLANNER_INSTRUCTION = """You are the milestone planner for ADELE, a Windows desktop AI assistant.

Convert the user's request into a milestone plan as JSON only.
Do NOT call tools. Do NOT use markdown fences. Output a single JSON object.

Each milestone is a GOAL with an observable success_signal.
hint_tools are suggestions only (use names from the Available Tools section).
Use 1 milestone for simple tasks and 2-6 for compound work."""

ROOT_INSTRUCTION = """You are ADELE, a memory-aware Windows desktop assistant built with Google ADK.

You can plan work, call desktop/browser tools, and explain results clearly.
Prefer one step at a time. Ask before risky or destructive actions."""


def build_planner_agent(model: str | None = None) -> Agent:
    return Agent(
        name="adele_milestone_planner",
        model=model or adk_planner_model(),
        description="Milestone planner for ADELE desktop missions.",
        instruction=PLANNER_INSTRUCTION,
        tools=[],
        generate_content_config=types.GenerateContentConfig(temperature=0.15),
    )


def build_root_agent(model: str | None = None) -> Agent:
    return Agent(
        name="adele_root_agent",
        model=model or adk_action_model(),
        description="ADELE desktop agent with local tool access.",
        instruction=ROOT_INSTRUCTION,
        tools=list(ADELE_ADK_TOOLS),
    )


# Default export for `adk deploy agent_engine adele_agent/`
root_agent = build_root_agent()
