"""
Deploy entrypoint for Google Agent Runtime.

Usage (from backend/):
  adk deploy agent_engine \\
    --project=YOUR_PROJECT \\
    --region=us-central1 \\
    --display_name="ADELE" \\
    adk_deploy/adele_agent
"""

from adk_agent.agent import root_agent

__all__ = ["root_agent"]
