"""
ADELE — ADK milestone planner service.

Runs the planning prompt through a Google ADK Runner and parses the JSON
milestone plan using the existing TaskPlanner parser.
"""

from __future__ import annotations

import uuid
from functools import partial
from typing import Callable, Optional

print = partial(print, flush=True)

from google.genai import types

try:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
except ImportError:
    Runner = None
    InMemorySessionService = None

from adk_agent.config import adk_planner_enabled
from agent.planner import MilestonePlan

try:
    from adk_agent.agent import build_planner_agent
except ImportError:
    build_planner_agent = None

_APP_NAME = "adele_desktop"
_USER_ID = "adele_user"


class AdkMilestonePlanner:
    """ADK-backed milestone planner (singleton-friendly)."""

    def __init__(self) -> None:
        if InMemorySessionService is None:
            self._session_service = None
            self._runner = None
            return
        self._session_service = InMemorySessionService()
        self._runner: Optional[Runner] = None

    def _runner_for(self, model: str | None = None) -> Runner:
        if Runner is None or self._session_service is None or build_planner_agent is None:
            raise ImportError("google-adk is required for ADK milestone planning.")
        agent = build_planner_agent(model=model)
        return Runner(
            app_name=_APP_NAME,
            agent=agent,
            session_service=self._session_service,
        )

    async def plan(
        self,
        *,
        user_prompt: str,
        parse_fn: Callable[[str, str], MilestonePlan],
        user_request: str,
        model: str | None = None,
    ) -> Optional[MilestonePlan]:
        if not adk_planner_enabled():
            return None

        session_id = f"plan_{uuid.uuid4().hex[:12]}"
        runner = self._runner_for(model=model)
        await self._session_service.create_session(
            app_name=_APP_NAME,
            user_id=_USER_ID,
            session_id=session_id,
        )

        message = types.Content(
            role="user",
            parts=[types.Part(text=user_prompt)],
        )

        final_text = ""
        try:
            async for event in runner.run_async(
                user_id=_USER_ID,
                session_id=session_id,
                new_message=message,
            ):
                if not event.is_final_response() or not event.content:
                    continue
                for part in event.content.parts or []:
                    if getattr(part, "text", None):
                        final_text = part.text.strip()
        except Exception as exc:
            print(f"[ADK Planner] run failed: {exc}")
            return None

        if not final_text:
            print("[ADK Planner] empty response")
            return None

        try:
            plan = parse_fn(final_text, user_request)
            plan.source = "adk_milestone_planner"
            print(f"[ADK Planner] plan ready ({len(plan.milestones)} milestones)")
            return plan
        except Exception as exc:
            print(f"[ADK Planner] parse failed: {exc}")
            return None


_default_planner: Optional[AdkMilestonePlanner] = None


def get_adk_milestone_planner() -> AdkMilestonePlanner:
    global _default_planner
    if _default_planner is None:
        _default_planner = AdkMilestonePlanner()
    return _default_planner
