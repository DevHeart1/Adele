"""
ADELE agent package.

Exports are resolved lazily so lightweight submodules such as
``agent.browser_intent_utils`` can be imported without pulling in the full
runtime and creating circular imports.
"""

_EXPORTS = {
    "AdeleAgentV2": ("agent.core_v2", "AdeleAgentV2"),
    "create_agent": ("agent.core_v2", "create_agent"),
    "WorldState": ("agent.world_state", "WorldState"),
    "UserIntent": ("agent.world_state", "UserIntent"),
    "IntentParser": ("agent.world_state", "IntentParser"),
    "IntentAction": ("agent.world_state", "IntentAction"),
    "TargetType": ("agent.world_state", "TargetType"),
    "Milestone": ("agent.planner", "Milestone"),
    "MilestonePlan": ("agent.planner", "MilestonePlan"),
    "MilestoneStatus": ("agent.planner", "MilestoneStatus"),
    "TaskPlanner": ("agent.task_planner", "TaskPlanner"),
    "ToolVerifier": ("agent.verifier", "ToolVerifier"),
    "VerificationResult": ("agent.verifier", "VerificationResult"),
    "get_verifier": ("agent.verifier", "get_verifier"),
    "ConversationMemory": ("agent.memory", "ConversationMemory"),
    "TaskStore": ("agent.memory", "TaskStore"),
    "UserPreferences": ("agent.memory", "UserPreferences"),
    "UserProfile": ("agent.memory", "UserProfile"),
    "WorkingMemory": ("agent.memory", "WorkingMemory"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    from importlib import import_module

    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
