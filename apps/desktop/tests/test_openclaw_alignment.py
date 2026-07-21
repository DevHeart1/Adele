"""
OpenClaw-aligned planner regression tests.
"""

import asyncio
import json
import os
import sys


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

from agent.core_v2 import AdeleAgentV2
from agent.perception import ContextSnapshot
from agent.planner import Milestone, MilestonePlan, MilestoneStatus
from agent.task_planner import TaskPlanner
from agent.verifier import ToolVerifier
from agent.world_state import IntentParser, WorldState
from providers.base import LLMResponse
from providers.router import ModelRouter
from runtime_state import RuntimeStateStore
from tools import registry as tool_registry
from tools import mac_tools
from tools.mac_tools import _candidate_app_names, _match_installed_app_name
from tools.selector import ToolSelector


COMPOUND_MEDIA_REQUEST = (
    "can you help me edit my capcut video, "
    "i want to edit the latest video in my downloads folder"
)


def test_task_graph_extracts_compound_local_media_entities():
    parser = IntentParser()

    graph = parser.extract_task_graph(COMPOUND_MEDIA_REQUEST)

    assert graph.primary_action == "modify"
    assert {"app", "folder", "content"}.issubset(graph.entity_types())
    assert any(entity.type == "app" and entity.value == "CapCut" for entity in graph.entities)
    assert any(entity.type == "folder" and entity.value == "Downloads" for entity in graph.entities)
    assert any(entity.type == "content" and entity.value == "video" for entity in graph.entities)
    assert "latest" in graph.selectors
    assert "specific_edit_instructions" in graph.unresolved_slots
    assert graph.complexity_score >= 3.0


def test_compound_task_bypasses_template_shortcuts():
    planner = TaskPlanner(provider=None, tool_registry=tool_registry)
    graph = planner.intent_parser.extract_task_graph(COMPOUND_MEDIA_REQUEST)

    assert planner._should_bypass_template_shortcuts(COMPOUND_MEDIA_REQUEST, graph) is True


def test_should_use_milestones_for_compound_app_file_task():
    planner = TaskPlanner(provider=None, tool_registry=tool_registry)
    graph = planner.intent_parser.extract_task_graph(COMPOUND_MEDIA_REQUEST)

    assert planner.should_use_milestones(COMPOUND_MEDIA_REQUEST, task_graph=graph) is True


def test_tool_selector_retains_file_system_for_capcut_downloads_request():
    selector = ToolSelector()

    tools = selector.select(
        COMPOUND_MEDIA_REQUEST,
        context_app="Google Chrome",
        context_url="",
    )

    assert "open_app" in tools
    assert "list_directory" in tools
    assert "run_shell" in tools


def test_router_fast_path_detects_trivial_request():
    router = ModelRouter()

    assert router._looks_trivial_fast_request("open spotify") is True
    assert router._looks_trivial_fast_request(COMPOUND_MEDIA_REQUEST) is False
    assert router._looks_trivial_fast_request("proceed") is False


def test_simple_open_app_plan_is_not_gated():
    agent = AdeleAgentV2(use_planning=True, persist=False)
    simple_plan = MilestonePlan(
        task_summary="Open Spotify",
        milestones=[
            Milestone(
                id=1,
                goal="Open Spotify",
                success_signal="Spotify is open",
                hint_tools=["open_app"],
            )
        ],
    )

    assert agent._should_gate_plan(simple_plan) is False


def test_explicit_text_entry_uses_a_gated_single_action_plan():
    request = 'Type "Hello from ADELE" into the active field.'
    planner = TaskPlanner(provider=None, tool_registry=tool_registry)
    world_state = WorldState(active_app="Google Chrome")
    world_state.intent = IntentParser().parse(request, world_state)
    world_state.task_graph = planner.intent_parser.extract_task_graph(request, world_state)

    plan = planner.build_direct_action_plan(
        user_request=request,
        world_state=world_state,
        available_tools=["type_text"],
    )

    assert plan is not None
    assert plan.source == "milestone_direct_text_entry"
    assert plan.milestones[0].hint_tools == ["type_text"]
    assert "Hello from ADELE" in plan.milestones[0].goal
    assert plan.milestones[0].direct_tool == "type_text"
    assert plan.milestones[0].direct_tool_args == {
        "text": "Hello from ADELE",
        "app_name": "Google Chrome",
    }
    assert AdeleAgentV2(persist=False)._should_gate_plan(plan) is True
    assert planner._extract_explicit_text_entry("type it") == ""


def test_type_text_refocuses_the_requested_app_before_pasting():
    original_activate = mac_tools._activate_target_app
    original_paste = mac_tools._windows_paste_text
    calls = []

    async def _fake_activate(app_name):
        calls.append(("activate", app_name))
        return True

    def _fake_paste(text):
        calls.append(("paste", text))

    try:
        mac_tools._activate_target_app = _fake_activate
        mac_tools._windows_paste_text = _fake_paste
        result = asyncio.run(mac_tools.type_text("Hello from ADELE", app_name="Google Chrome"))
    finally:
        mac_tools._activate_target_app = original_activate
        mac_tools._windows_paste_text = original_paste

    assert result == "Pasted 16 characters into the active field."
    assert calls == [("activate", "Google Chrome"), ("paste", "Hello from ADELE")]


def test_simple_screen_question_uses_direct_read_only_plan():
    planner = TaskPlanner(provider=None, tool_registry=tool_registry)
    request = "What is on my screen right now?"
    world_state = WorldState(intent=IntentParser().parse(request))

    plan = planner.build_direct_action_plan(
        user_request=request,
        world_state=world_state,
        available_tools=["read_screen"],
    )

    assert plan is not None
    assert plan.source == "milestone_direct_screen"
    assert plan.milestones[0].hint_tools == ["read_screen"]


def test_planner_unavailable_message_hides_internal_milestone_error():
    unclear = IntentParser().parse("it's also")
    message = AdeleAgentV2._planner_unavailable_message(unclear)

    assert "milestone" not in message.lower()
    assert "short request" in message.lower()


def test_contextual_guidance_unwraps_vault_context_and_skips_planning():
    class Provider:
        def __init__(self):
            self.calls = []

        async def generate(self, **kwargs):
            self.calls.append(kwargs)
            return LLMResponse(text="Start with the highlighted setup step, then I can help with the next one.")

    class Router:
        def __init__(self, provider):
            self.fast = provider

        async def initialize(self):
            return None

    wrapped_request = (
        "[Relevant Knowledge — retrieved from your permanent memory vault]\n"
        "[notes] Example saved context\n\n---\n"
        "User:\nWhat should I do next in this app?"
    )
    agent = AdeleAgentV2(persist=False)
    provider = Provider()
    agent.router = Router(provider)
    agent.conversation.add_user(wrapped_request)

    assert agent._is_conversational(wrapped_request) == "contextual_guidance"
    assert agent._is_conversational("Why can't you do that?") == "contextual_guidance"
    assert agent._is_conversational("What can you see?") is None
    assert agent._is_conversational("Can you open Spotify?") is None

    response, awaiting = asyncio.run(
        agent._try_conversational_fast_path(
            wrapped_request,
            ContextSnapshot(active_app="Google Chrome", window_title="Product documentation"),
        )
    )

    assert awaiting is False
    assert response.startswith("Start with the highlighted")
    assert len(provider.calls) == 1
    prompt = provider.calls[0]["messages"][0]["parts"][0]["text"]
    assert "What should I do next in this app?" in prompt
    assert "Relevant Knowledge" not in prompt
    assert provider.calls[0]["tools"] == []
    assert provider.calls[0]["thinking_level"] == "LOW"


def test_creative_writing_request_uses_no_tools_chat_path_despite_desktop_context():
    class Provider:
        def __init__(self):
            self.calls = []

        async def generate(self, **kwargs):
            self.calls.append(kwargs)
            return LLMResponse(text="Here is a short story premise about a well-meaning AI that learns the wrong lesson.")

    class Router:
        def __init__(self, provider):
            self.fast = provider

        async def initialize(self):
            return None

    request = (
        "I'm working on Google Docs. Help me write a story based on a theory "
        "about how AI could end the world."
    )
    agent = AdeleAgentV2(persist=False)
    provider = Provider()
    agent.router = Router(provider)

    assert agent._is_conversational(request) == "creative_content"
    assert agent._is_conversational("Type a story into my Google Docs document") is None

    response, awaiting = asyncio.run(
        agent._try_conversational_fast_path(
            request,
            ContextSnapshot(active_app="Google Chrome", window_title="Google Docs"),
        )
    )

    assert awaiting is False
    assert response.startswith("Here is a short story premise")
    assert len(provider.calls) == 1
    assert provider.calls[0]["tools"] == []
    assert provider.calls[0]["thinking_level"] == "LOW"
    assert "up to 250 words" in provider.calls[0]["system_prompt"]


def test_vault_envelope_separates_saved_context_from_the_user_command():
    wrapped_request = (
        "[Relevant Knowledge — retrieved from your permanent memory vault]\n"
        "[notes] User's area is Enugu, Nigeria\n\n---\n"
        "User:\nPlease can you open Chrome?"
    )
    agent = AdeleAgentV2(persist=False)

    assert agent._visible_user_request(wrapped_request) == "Please can you open Chrome?"
    assert "Enugu, Nigeria" in agent._vault_retrieval_context(wrapped_request)
    intent = IntentParser().parse(agent._visible_user_request(wrapped_request))
    assert intent.action.value == "open"
    assert intent.target_value.lower().endswith("chrome")


def test_new_request_clears_only_the_previous_request_cancellation_state():
    state = RuntimeStateStore()
    state.start_request(request_id="old-request", query="old task")
    assert state.cancel_request(request_id="old-request") is True
    assert state.is_request_cancelled("old-request") is True

    state.start_request(request_id="new-request", query="new task")

    assert state.is_request_cancelled("new-request") is False
    assert state.cancel_request(request_id="old-request") is False


def test_milestone_failure_message_hides_internal_goal_and_cancellation_detail():
    failed = [
        Milestone(
            id=1,
            goal="Summarize the confidential judging rubric and explain every section",
            status=MilestoneStatus.FAILED,
            error="Cancelled by user.",
        )
    ]

    message = AdeleAgentV2._milestone_failure_message(failed, [])

    assert message == "That request was stopped before it finished, so I couldn't verify the result."
    assert "summarize" not in message.lower()
    assert "cancelled" not in message.lower()


def test_milestone_failure_message_does_not_expose_raw_goal_for_failed_task():
    failed = [
        Milestone(
            id=1,
            goal="Open a private document from C:\\Users\\Example\\Secret",
            status=MilestoneStatus.FAILED,
            error="Tool execution failed.",
        )
    ]

    message = AdeleAgentV2._milestone_failure_message(failed, [])

    assert message == "I couldn't complete that request or verify a successful result."
    assert "private document" not in message.lower()
    assert "C:\\Users" not in message


def test_candidate_app_names_include_alias_resolution():
    candidates = _candidate_app_names("chrome")

    assert "Google Chrome" in candidates


def test_match_installed_app_name_uses_local_application_listing(monkeypatch):
    monkeypatch.setattr("tools.mac_tools.os.path.isdir", lambda path: path == "/Applications")
    monkeypatch.setattr(
        "tools.mac_tools.os.listdir",
        lambda path: ["Spotify.app", "Google Chrome.app"] if path == "/Applications" else [],
    )

    matched = asyncio.run(_match_installed_app_name("spotify"))

    assert matched == "Spotify"


def test_verify_open_app_accepts_launched_when_state_matches():
    verifier = ToolVerifier()

    async def get_state():
        return {"active_app": "CapCut"}

    result = asyncio.run(
        verifier._verify_open_app(
            {"app_name": "CapCut"},
            "Launched CapCut. It may already have been open — use Cmd+Tab if it's not visible.",
            "",
            get_state,
        )
    )

    assert result.success is True


def test_verify_open_app_rejects_missing_native_app():
    verifier = ToolVerifier()

    result = asyncio.run(
        verifier._verify_open_app(
            {"app_name": "Spotify"},
            "Couldn't find 'Spotify' as an installed app",
            "",
            None,
        )
    )

    assert result.success is False


def test_template_registry_surfaces_skill_context_for_research_request():
    planner = TaskPlanner(provider=None, tool_registry=tool_registry)

    intent = planner.intent_parser.parse(
        "research all UK housing and create a detailed google document about it"
    )
    candidates = planner.template_registry.get_skill_candidates(
        user_request="research all UK housing and create a detailed google document about it",
        intent=intent,
        world_state=WorldState(active_app="Google Chrome"),
        available_tools=None,
    )
    context = planner.template_registry.format_skill_context(candidates)

    assert candidates
    assert "research_to_document_skill" in context
    assert "Suggested tools" in context


def test_compound_request_uses_skill_overlay_not_direct_pack():
    class _FakeProvider:
        async def generate(self, messages, system_prompt, tools, temperature=0.1):
            return type(
                "Resp",
                (),
                {
                    "text": json.dumps(
                        {
                            "task_summary": "Research and document UK housing",
                            "needs_clarification": False,
                            "clarification_prompt": "",
                            "milestones": [
                                {
                                    "id": 1,
                                    "goal": "Gather reliable research on UK housing systems",
                                    "success_signal": "Relevant source pages and notes collected",
                                    "hint_tools": ["web_search", "browser_read_page"],
                                    "depends_on": [],
                                    "deliverable_key": "research_notes",
                                },
                                {
                                    "id": 2,
                                    "goal": "Create a Google document with the findings",
                                    "success_signal": "Document URL returned",
                                    "hint_tools": ["gdocs_create"],
                                    "depends_on": [1],
                                    "deliverable_key": "doc_url",
                                },
                            ],
                            "final_response": "Done",
                        }
                    )
                },
            )()

    planner = TaskPlanner(provider=_FakeProvider(), tool_registry=tool_registry)
    plan = asyncio.run(
        planner.create_plan(
            "research all UK housing and create a detailed google document about it",
            WorldState(active_app="Google Chrome"),
            available_tools=["web_search", "browser_read_page", "gdocs_create"],
        )
    )

    assert plan.source == "milestone_planner"
    assert len(plan.milestones) == 2
    assert "research_to_document_skill" in plan.skill_context
