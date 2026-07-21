"""
Test Stage 4: Milestone planning prompts and detection.
"""
import sys
import os
import json
import pytest

backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, backend_path)

from agent.task_planner import TaskPlanner
from agent.core_v2 import AdeleAgentV2
from agent.plan_journal import journal_request_trace
from agent.planner import MilestonePlan, Milestone, MilestoneStatus
from agent.perception import ContextSnapshot
from agent.world_state import WorldState
from tools.selector import ToolSelector
from providers.base import LLMResponse


def test_should_use_milestones_research():
    planner = TaskPlanner()
    assert planner.should_use_milestones("research UK rental market and create a document")
    assert planner.should_use_milestones("investigate the best laptops and write a report")
    assert planner.should_use_milestones("analyze competitor pricing and create a brief")


def test_should_use_milestones_comparison():
    planner = TaskPlanner()
    assert planner.should_use_milestones("compare MacBook Pro vs Dell XPS")
    assert planner.should_use_milestones("what's the difference between React and Vue")


def test_should_use_milestones_simple():
    planner = TaskPlanner()
    assert not planner.should_use_milestones("open spotify")
    assert not planner.should_use_milestones("set volume to 50")
    assert not planner.should_use_milestones("read the file server.py")


def test_direct_action_plan_skips_model_planning_for_safe_single_action():
    planner = TaskPlanner()
    state = WorldState()
    state.intent = planner.intent_parser.parse("open Spotify", state)
    state.task_graph = planner.intent_parser.extract_task_graph("open Spotify", state)

    plan = planner.build_direct_action_plan(
        "open Spotify",
        state,
        available_tools=["open_app"],
    )

    assert plan is not None
    assert plan.source == "milestone_direct_action"
    assert [milestone.hint_tools for milestone in plan.milestones] == [["open_app"]]
    assert plan.milestones[0].direct_tool == "open_app"
    assert plan.milestones[0].direct_tool_args == {"app_name": "Spotify"}


def test_local_direct_plans_do_not_require_chatgpt_startup():
    local_plan = MilestonePlan(
        task_summary="Open Spotify",
        milestones=[
            Milestone(
                id=1,
                goal="Open Spotify",
                hint_tools=["open_app"],
                direct_tool="open_app",
                direct_tool_args={"app_name": "Spotify"},
            )
        ],
    )
    web_plan = MilestonePlan(
        task_summary="Look up current information",
        milestones=[
            Milestone(
                id=1,
                goal="Retrieve current information",
                hint_tools=["get_web_information"],
                direct_tool="get_web_information",
            )
        ],
    )

    assert not AdeleAgentV2._plan_requires_provider(local_plan)
    assert AdeleAgentV2._plan_requires_provider(web_plan)


@pytest.mark.asyncio
async def test_open_app_uses_direct_local_path_without_routing_to_chatgpt():
    agent = AdeleAgentV2(persist=False)
    observed = {}

    async def unexpected_route(*_args, **_kwargs):
        raise AssertionError("a direct local action must not start ChatGPT routing")

    async def fake_execute(**kwargs):
        observed.update(kwargs)
        return ("Opened Spotify.", False)

    agent.router.route = unexpected_route
    agent._execute_milestone_plan = fake_execute

    response, awaiting = await agent._run_impl(
        "open Spotify",
        ContextSnapshot(active_app="Explorer", window_title="Files"),
    )

    assert (response, awaiting) == ("Opened Spotify.", False)
    assert observed["provider"] is None
    assert observed["plan"].milestones[0].direct_tool == "open_app"


@pytest.mark.asyncio
async def test_small_talk_responds_before_chatgpt_initialization():
    agent = AdeleAgentV2(persist=False)

    class FailingRouter:
        async def initialize(self):
            raise AssertionError("small talk must not initialize ChatGPT")

    agent.router = FailingRouter()
    response = await agent._try_conversational_fast_path(
        "How are you?",
        ContextSnapshot(),
    )

    assert response is not None
    assert response[1] is False
    assert "help" in response[0].lower() or "good" in response[0].lower()


@pytest.mark.asyncio
async def test_direct_executor_completes_local_tool_without_a_provider():
    agent = AdeleAgentV2(persist=False)
    plan = MilestonePlan(
        task_summary="Open Spotify",
        final_response="Opened Spotify.",
        milestones=[
            Milestone(
                id=1,
                goal="Open Spotify",
                hint_tools=["open_app"],
                direct_tool="open_app",
                direct_tool_args={"app_name": "Spotify"},
                deliverable_key="app_opened",
            )
        ],
    )

    async def fake_execute_step(step, *_args, **_kwargs):
        assert step.tool == "open_app"
        assert step.args == {"app_name": "Spotify"}
        step.result = "Opened Spotify."
        return True

    agent._execute_step = fake_execute_step
    response, awaiting = await agent._execute_milestone_plan(
        plan=plan,
        world_state=WorldState(),
        provider=None,
        context=ContextSnapshot(),
        user_text="open Spotify",
        llm_tool_declarations=[],
        ws_callback=None,
        show_milestone_progress=False,
    )

    assert (response, awaiting) == ("Opened Spotify.", False)


def test_direct_action_plan_keeps_compound_work_on_milestone_path():
    planner = TaskPlanner()
    request = "open Spotify and play my workout playlist"
    state = WorldState()
    state.intent = planner.intent_parser.parse(request, state)
    state.task_graph = planner.intent_parser.extract_task_graph(request, state)

    assert planner.build_direct_action_plan(request, state, ["open_app", "play_media"]) is None


def test_direct_action_plan_reads_a_file_without_invalid_intent_access():
    planner = TaskPlanner()
    state = WorldState()
    state.intent = planner.intent_parser.parse("read the file server.py", state)
    state.task_graph = planner.intent_parser.extract_task_graph("read the file server.py", state)

    plan = planner.build_direct_action_plan(
        "read the file server.py",
        state,
        available_tools=["read_file"],
    )

    assert plan is not None
    assert plan.milestones[0].hint_tools == ["read_file"]


def test_browser_tab_query_uses_read_only_direct_plan_without_opening_chrome():
    request = "Tell me how many open tabs I have in Chrome"
    planner = TaskPlanner()
    state = WorldState()
    state.intent = planner.intent_parser.parse(request, state)
    state.task_graph = planner.intent_parser.extract_task_graph(request, state)

    plan = planner.build_direct_action_plan(
        request,
        state,
        available_tools=["browser_list_tabs", "open_app"],
    )

    assert plan is not None
    assert plan.source == "milestone_browser_tab_query"
    assert plan.milestones[0].hint_tools == ["browser_list_tabs"]
    assert plan.milestones[0].direct_tool == "browser_list_tabs"
    assert plan.milestones[0].direct_tool_args == {"summary_only": True}
    assert "open_app" not in plan.milestones[0].hint_tools


def test_browser_tab_query_tool_scope_excludes_open_app():
    class FakeRegistry:
        def list_names(self):
            return ["send_response", "await_reply", "browser_list_tabs", "open_app"]

    selected = ToolSelector(FakeRegistry()).select(
        "How many tabs do I have in Chrome?",
        intent_action="query",
        intent_target_type="app",
        intent_target_value="chrome",
    )

    assert selected == ["send_response", "await_reply", "browser_list_tabs"]


def test_time_sensitive_world_cup_question_selects_verified_web_research():
    selected = ToolSelector().select(
        "Give me the list of players who played for Spain in the 2026 World Cup that ended yesterday",
        intent_action="query",
        intent_target_type="unknown",
    )

    assert "get_web_information" in selected
    assert "quit_app" not in selected


def test_time_sensitive_world_cup_question_uses_low_effort_direct_lookup_plan():
    request = "Give me the list of players who played for Spain in the 2026 World Cup that ended yesterday"
    planner = TaskPlanner()
    state = WorldState()
    state.intent = planner.intent_parser.parse(request, state)
    state.task_graph = planner.intent_parser.extract_task_graph(request, state)

    plan = planner.build_direct_action_plan(
        request,
        state,
        available_tools=["get_web_information", "send_response"],
    )

    assert plan is not None
    assert plan.source == "milestone_current_information"
    assert plan.milestones[0].direct_tool == "get_web_information"
    assert plan.milestones[0].direct_tool_args["target_type"] == "page_summary"
    assert not planner.should_use_milestones(request, task_graph=state.task_graph)


def test_request_trace_keeps_only_safe_diagnostic_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("ADELE_DATA_DIR", str(tmp_path))
    journal_request_trace(
        trace_id="trace_123",
        phase="routing",
        intent="query",
        target_type="unknown",
        route="web research",
        tool_names=["get_web_information", r"C:\\private\\screen.png"],
        status="selected",
        error_code="",
    )

    trace_path = tmp_path / "traces" / "request_trace.json"
    entries = json.loads(trace_path.read_text(encoding="utf-8"))
    assert entries[-1] == {
        "saved_at": entries[-1]["saved_at"],
        "trace_id": "trace_123",
        "phase": "routing",
        "intent": "query",
        "target_type": "unknown",
        "route": "web_research",
        "tool_names": ["get_web_information"],
        "status": "selected",
        "error_code": "unknown",
    }
    assert "private" not in trace_path.read_text(encoding="utf-8").lower()


@pytest.mark.asyncio
async def test_current_information_summary_uses_source_text_not_gateway_url():
    class FakeProvider:
        def __init__(self):
            self.prompt = ""

        async def generate(self, **kwargs):
            self.prompt = kwargs["messages"][0]["parts"][0]["text"]
            return LLMResponse(text="Spain's current squad is listed in the source material.")

    provider = FakeProvider()
    agent = object.__new__(AdeleAgentV2)
    answer = await agent._summarize_current_information(
        provider=provider,
        user_text="List Spain's current World Cup players",
        gateway_result=json.dumps({
            "ok": True,
            "url": "https://private.example/roster",
            "title": "Spain roster",
            "content": "Verified roster data.",
        }),
    )

    assert answer == "Spain's current squad is listed in the source material."
    assert "Verified roster data." in provider.prompt
    assert "private.example" not in provider.prompt


def test_browser_tab_query_response_is_count_only_and_reports_bridge_status():
    answer, status = AdeleAgentV2._browser_tab_query_response(
        '{"status":"ok","count":3,"tabs":[{"url":"https://private.example"}]}'
    )
    assert (answer, status) == ("You have 3 open Chrome tabs.", "ok")
    assert "private.example" not in answer

    unavailable, unavailable_status = AdeleAgentV2._browser_tab_query_response(
        '{"status":"browser_bridge_unavailable","count":0}'
    )
    assert unavailable_status == "bridge_unavailable"
    assert "did not open Chrome" in unavailable


def test_parse_milestone_response():
    planner = TaskPlanner()
    raw = json.dumps({
        "task_summary": "Research UK rentals",
        "needs_clarification": False,
        "milestones": [
            {
                "id": 1,
                "goal": "Search for UK rental data",
                "success_signal": "3+ sources found",
                "hint_tools": ["web_search", "read_page_content"],
                "depends_on": [],
                "deliverable_key": "research_data",
            },
            {
                "id": 2,
                "goal": "Create Google Doc",
                "success_signal": "Doc URL returned",
                "hint_tools": ["gdocs_create"],
                "depends_on": [1],
                "deliverable_key": "doc_url",
            },
        ],
        "final_response": "Done!",
    })
    plan = planner._parse_milestone_response(raw, "research UK rentals")
    assert isinstance(plan, MilestonePlan)
    assert len(plan.milestones) == 2
    assert plan.milestones[0].goal == "Search for UK rental data"
    assert plan.milestones[1].depends_on == [1]
    assert plan.milestones[0].deliverable_key == "research_data"


def test_parse_milestone_response_code_fenced():
    planner = TaskPlanner()
    raw = '```json\n{"task_summary":"test","milestones":[{"id":1,"goal":"do it"}],"final_response":"ok"}\n```'
    plan = planner._parse_milestone_response(raw, "test")
    assert len(plan.milestones) == 1
    assert plan.milestones[0].goal == "do it"


def test_parse_milestone_response_clarification():
    planner = TaskPlanner()
    raw = json.dumps({
        "task_summary": "unclear",
        "needs_clarification": True,
        "clarification_prompt": "What do you want?",
        "milestones": [],
        "final_response": "",
    })
    plan = planner._parse_milestone_response(raw, "do it")
    assert plan.needs_clarification
    assert plan.clarification_prompt == "What do you want?"


def test_tool_category_summary(monkeypatch):
    class EmptySelector:
        def format_planning_tool_summary(self, _tool_names=None):
            return "(no tools available)"

    monkeypatch.setattr("agent.task_planner.get_tool_selector", lambda *_args, **_kwargs: EmptySelector())
    planner = TaskPlanner()
    summary = planner._get_tool_category_summary()
    assert "Browser/Web" in summary
    assert "find_and_act" in summary
    assert "Google Workspace" in summary
    assert "gdocs_create" in summary


@pytest.mark.asyncio
async def test_invalid_plan_response_gets_one_json_repair_retry():
    valid_plan = json.dumps({
        "task_summary": "Open calculator",
        "needs_clarification": False,
        "milestones": [{
            "id": 1,
            "goal": "Open Calculator",
            "success_signal": "Calculator is visible",
            "hint_tools": ["open_app"],
            "depends_on": [],
            "deliverable_key": "calculator_open",
        }],
        "final_response": "Calculator is open.",
    })

    class FakeProvider:
        def __init__(self):
            self.calls = []
            self.responses = [
                LLMResponse(text="Here is the plan you asked for:"),
                LLMResponse(text=valid_plan),
            ]

        async def generate(self, **kwargs):
            self.calls.append(kwargs)
            return self.responses.pop(0)

    provider = FakeProvider()
    planner = TaskPlanner(provider=provider, use_adk=False)
    plan = await planner.create_milestone_plan(
        user_request="open Calculator",
        world_state=WorldState(),
        available_tools=["open_app"],
    )

    assert plan is not None
    assert len(plan.milestones) == 1
    assert len(provider.calls) == 2
    assert "response_json_schema" not in provider.calls[0]
    assert planner.last_failure is None


@pytest.mark.asyncio
async def test_provider_error_is_recorded_without_exposing_raw_error(capsys):
    class FakeProvider:
        async def generate(self, **kwargs):
            return LLMResponse(error=r"C:\Users\Example\private-screenshot.png")

    planner = TaskPlanner(provider=FakeProvider(), use_adk=False)
    plan = await planner.create_milestone_plan(
        user_request="open Calculator",
        world_state=WorldState(),
        available_tools=["open_app"],
    )

    assert plan is None
    assert planner.last_failure == "provider_error"
    assert "private-screenshot.png" not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_milestone_planning_honors_requested_reasoning_effort():
    class FakeProvider:
        def __init__(self):
            self.call = None

        async def generate(self, **kwargs):
            self.call = kwargs
            return LLMResponse(text=json.dumps({
                "task_summary": "Set volume",
                "milestones": [{
                    "id": 1,
                    "goal": "Set the volume to 50 percent",
                    "success_signal": "System volume is 50 percent",
                    "hint_tools": ["system_control"],
                }],
            }))

    provider = FakeProvider()
    plan = await TaskPlanner(provider=provider, use_adk=False).create_milestone_plan(
        user_request="set volume to 50",
        world_state=WorldState(),
        available_tools=["system_control"],
        thinking_level="LOW",
    )

    assert plan is not None
    assert provider.call["thinking_level"] == "LOW"
