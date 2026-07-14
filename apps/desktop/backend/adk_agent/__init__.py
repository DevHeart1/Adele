"""
ADELE — Google ADK (Agent Development Kit) integration.

Provides ADK agents and a milestone planner front-end for core_v2.
"""

from adk_agent.config import adk_planner_enabled

try:
    from adk_agent.planner import AdkMilestonePlanner, get_adk_milestone_planner
except ImportError:
    AdkMilestonePlanner = None

    def get_adk_milestone_planner():
        raise ImportError("google-adk is required for ADK milestone planning.")

__all__ = [
    "AdkMilestonePlanner",
    "adk_planner_enabled",
    "get_adk_milestone_planner",
]
