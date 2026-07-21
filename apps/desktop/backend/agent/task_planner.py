"""
ADELE — Task Planner V2
===========================
Milestone-first task planner for the unified execution loop.
"""

import asyncio
import json
import re
import time
from typing import Optional, List
from functools import partial

print = partial(print, flush=True)

from agent.world_state import WorldState, UserIntent, IntentAction, TargetType, IntentParser, TaskGraph
from agent.browser_intent_utils import is_browser_tab_query
from agent.planner import Milestone, MilestonePlan, MilestoneStatus
from agent.example_bank import ExampleBank
from agent.template_registry import TemplateRegistry
from tools.selector import get_tool_selector, is_time_sensitive_information_request


def _norm_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


# ═══════════════════════════════════════════════════════════════
#  Milestone Planning Prompt (V3)
# ═══════════════════════════════════════════════════════════════

MILESTONE_PLANNING_SYSTEM = """You are the milestone planner for ADELE, a cross-platform desktop AI assistant.
Your job: convert user requests into MILESTONE plans — high-level goal checkpoints.
Output ONLY valid JSON — no explanations, no markdown.

## Key Principle
You define WHAT must be accomplished, not HOW. Each milestone is a goal
with a success signal. The runtime executor decides which tools to call.

## Milestone Design Rules
1. Each milestone is a distinct GOAL, not a tool call.
2. The success_signal must be OBSERVABLE — something the executor can verify.
3. Use 1 milestone for simple direct tasks and 2-6 milestones for compound tasks. Don't micro-manage.
4. hint_tools are SUGGESTIONS, not prescriptions. The executor may use different tools.
5. Do not include max_actions. Runtime safety limits are enforced by the executor.
6. deliverable_key names the output stored in working memory for downstream milestones.
7. For time-sensitive factual requests (current results, team rosters, prices,
   schedules, or news), include `get_web_information` and require sourced data
   before the final response. Do not rely on static model knowledge.

## Voice Transcription Awareness
Requests arrive as voice-transcribed text. Correct obvious errors."""

MILESTONE_PLANNING_PROMPT = """Given this user request and context, create a milestone plan.

## Available Tools
{tool_categories}

## Current Desktop State
{world_state}

## Conversation History
{conversation_context}

## Relevant Saved Context
{supplemental_context}

## Active Skill Overlays
{skill_context}

## User Request
"{user_request}"

## Output Format
Return a JSON object with this exact structure:
{{
  "task_summary": "Brief description of the full task",
  "needs_clarification": false,
  "clarification_prompt": "",
  "milestones": [
    {{
      "id": 1,
      "goal": "What must be accomplished (natural language)",
      "success_signal": "Observable evidence that the goal is met",
      "hint_tools": ["tool_category_1", "tool_category_2"],
      "depends_on": [],
      "deliverable_key": "key_name"
    }}
  ],
  "final_response": "Short confirmation message to show user"
}}

## Milestone Design Examples

Request: "Research UK rental market and create a document"
{{
  "task_summary": "Research UK rental market and create a report",
  "needs_clarification": false,
  "milestones": [
    {{
      "id": 1,
      "goal": "Search for UK rental market data and identify 3+ authoritative sources",
      "success_signal": "At least 3 source URLs visited and content extracted",
      "hint_tools": ["get_web_information", "open_url"],
      "depends_on": [],
      "deliverable_key": "research_data"
    }},
    {{
      "id": 2,
      "goal": "Create a comprehensive Google Doc with findings",
      "success_signal": "Google Doc URL returned with content written",
      "hint_tools": ["gdocs_create", "gdocs_append"],
      "depends_on": [1],
      "deliverable_key": "document_url"
    }}
  ],
  "final_response": "Research complete! Here's your document."
}}

Request: "Compare prices of MacBook Pro vs Dell XPS on Amazon"
{{
  "task_summary": "Compare MacBook Pro and Dell XPS prices on Amazon",
  "needs_clarification": false,
  "milestones": [
    {{
      "id": 1,
      "goal": "Find MacBook Pro price on Amazon",
      "success_signal": "MacBook Pro price and model details extracted",
      "hint_tools": ["get_web_information", "open_url"],
      "depends_on": [],
      "deliverable_key": "macbook_price"
    }},
    {{
      "id": 2,
      "goal": "Find Dell XPS price on Amazon",
      "success_signal": "Dell XPS price and model details extracted",
      "hint_tools": ["get_web_information", "open_url"],
      "depends_on": [],
      "deliverable_key": "dell_price"
    }},
    {{
      "id": 3,
      "goal": "Present comparison to user",
      "success_signal": "Comparison table or summary delivered",
      "hint_tools": ["send_response"],
      "depends_on": [1, 2],
      "deliverable_key": "comparison"
    }}
  ],
  "final_response": ""
}}

Request: "Open Spotify"
{{
  "task_summary": "Open Spotify",
  "needs_clarification": false,
  "clarification_prompt": "",
  "milestones": [
    {{
      "id": 1,
      "goal": "Open the Spotify application",
      "success_signal": "Spotify is open and focused",
      "hint_tools": ["open_app"],
      "depends_on": [],
      "deliverable_key": "opened_app"
    }}
  ],
  "final_response": "Spotify is open."
}}

Request: "Message Chris on WhatsApp saying I'll be late"
{{
  "task_summary": "Send a WhatsApp message to Chris",
  "needs_clarification": false,
  "clarification_prompt": "",
  "milestones": [
    {{
      "id": 1,
      "goal": "Open WhatsApp, search for and open the chat with Chris",
      "success_signal": "WhatsApp is open and Chris's chat conversation is visible",
      "hint_tools": ["open_app", "click_ui", "type_in_field"],
      "depends_on": [],
      "deliverable_key": "chat_opened"
    }},
    {{
      "id": 2,
      "goal": "Type the message and send it to Chris",
      "success_signal": "The message has been typed into the chat and sent",
      "hint_tools": ["click_ui", "type_in_field", "type_text", "press_key"],
      "depends_on": [1],
      "deliverable_key": "message_sent"
    }}
  ],
  "final_response": "Message sent to Chris on WhatsApp."
}}

Now create a milestone plan for the user's request. Output ONLY the JSON:"""


REPLAN_PROMPT = """A milestone plan is being executed but milestone {failed_id} FAILED.
Revise the REMAINING milestones to recover and still achieve the original goal.

## Original User Request
"{user_request}"

## Original Plan Summary
{task_summary}

## Completed Milestones (DO NOT repeat)
{completed_summary}

## Failed Milestone
Goal: {failed_goal}
Error: {failure_reason}

## Remaining Milestones (THESE need revision)
{remaining_summary}

## Available Deliverables
{deliverables_summary}

## Instructions
- Revise the remaining milestones to work around the failure.
- You may add, remove, or merge milestones.
- Preserve deliverable keys that downstream milestones depend on.
- If the failure is unrecoverable, return an empty milestones array.
- Milestone IDs should continue from {next_id}.
- Output ONLY the JSON — no explanations.

## Output Format
{{
  "milestones": [
    {{
      "id": {next_id},
      "goal": "Revised goal",
      "success_signal": "Observable evidence",
      "hint_tools": ["tool_1"],
      "depends_on": [],
      "deliverable_key": "key_name"
    }}
  ],
  "recovery_strategy": "Brief explanation of how the revised plan recovers"
}}"""


# ═══════════════════════════════════════════════════════════════
#  Task Planner Class
# ═══════════════════════════════════════════════════════════════

class TaskPlanner:
    """
    Generates milestone plans from user requests.

    The active runtime is milestone-only.
    """
    
    def __init__(self, provider=None, tool_registry=None, use_adk: Optional[bool] = None):
        """
        Initialize the task planner.
        
        Args:
            provider: LLM provider for complex planning (optional)
            tool_registry: Tool registry for getting tool declarations
        """
        self.provider = provider
        self.tool_registry = tool_registry
        self.use_adk = use_adk
        self.intent_parser = IntentParser()
        self.example_bank = ExampleBank()
        self.template_registry = TemplateRegistry()
        # This intentionally contains a short diagnostic code only. Never
        # store model output, prompts, paths, screenshots, or exception text.
        self.last_failure: Optional[str] = None
        
        # Cache for tool descriptions
        self._tool_descriptions_cache: Optional[str] = None

    def _adk_planning_enabled(self) -> bool:
        if self.use_adk is not None:
            return bool(self.use_adk)
        try:
            from adk_agent.config import adk_planner_enabled
            return adk_planner_enabled()
        except Exception:
            return False

    async def _generate_with_compat(self, **kwargs):
        try:
            return await self.provider.generate(**kwargs)
        except TypeError as exc:
            optional_keys = (
                "thinking_level",
                "response_json_schema",
                "enable_builtin_tools",
            )
            trimmed = dict(kwargs)
            changed = False
            for key in optional_keys:
                if key in trimmed:
                    trimmed.pop(key, None)
                    changed = True
            if changed:
                return await self.provider.generate(**trimmed)
            raise

    def record_success(self, request: str, plan, intent: UserIntent):
        """Record a successful plan execution in the example bank for future learning."""
        if plan.needs_clarification:
            return
        # Only record LLM-generated plans (templates don't need learning)
        if getattr(plan, "source", "") in ("template", "template_pack"):
            return
        try:
            if isinstance(plan, MilestonePlan):
                if not plan.milestones:
                    return
                plan_dict = plan.to_dict()
                tools = sorted({
                    tool
                    for milestone in plan.milestones
                    for tool in milestone.hint_tools
                    if tool
                })
            else:
                if not plan.steps:
                    return
                plan_dict = {
                    "task_summary": plan.task_summary,
                    "steps": [s.to_dict() for s in plan.steps],
                    "final_response": plan.final_response,
                }
                tools = [s.tool for s in plan.steps]
            self.example_bank.record(
                request=request,
                intent_action=intent.action.value,
                intent_target=intent.target_type.value,
                plan_json=plan_dict,
                tools_used=tools,
                success=True,
            )
        except Exception:
            pass  # Non-critical

    def _looks_like_simple_media_open(self, user_request: str, intent: UserIntent) -> bool:
        text = f" {_norm_text(user_request)} "
        if intent.action not in {IntentAction.OPEN, IntentAction.PLAY}:
            return False
        if any(marker in text for marker in (
            " compare ",
            " summarize ",
            " summarise ",
            " research ",
            " explain ",
            " send ",
            " share ",
            " with ",
            " then ",
            " and ",
            " after ",
            " before ",
        )):
            return False
        if any(marker in text for marker in (" use the link ", " from clipboard ", " selected text ", " clipboard ")):
            return False
        media_markers = (" video ", " clip ", " movie ", " song ", " music ", " playlist ", " podcast ", " album ", " youtube ")
        if intent.target_type == TargetType.URL and intent.target_value:
            target_value = intent.target_value.lower()
            return "youtube" in target_value or "youtu.be" in target_value
        return any(marker in text for marker in media_markers)

    def _derive_media_query(self, user_request: str) -> str:
        query = (user_request or "").strip()
        lowered = query.lower()
        prefixes = [
            "please ",
            "can you ",
            "could you ",
            "would you ",
            "will you ",
            "open ",
            "play ",
            "show ",
            "start ",
            "launch ",
        ]
        changed = True
        while changed:
            changed = False
            for prefix in prefixes:
                if lowered.startswith(prefix):
                    query = query[len(prefix):].strip()
                    lowered = query.lower()
                    changed = True
        for article in ("a ", "an ", "the "):
            if lowered.startswith(article):
                query = query[len(article):].strip()
                lowered = query.lower()
                break
        return query.strip(" .?!")

    def _build_media_open_shortcut(
        self,
        user_request: str,
        intent: UserIntent,
        available_tools: Optional[List[str]] = None,
    ) -> Optional[MilestonePlan]:
        if intent.ambiguous or not self._looks_like_simple_media_open(user_request, intent):
            return None

        allowed = set(available_tools or [])
        if intent.target_type == TargetType.URL and intent.target_value and "open_url" in allowed:
            target_url = intent.target_value if intent.target_value.startswith(("http://", "https://")) else f"https://{intent.target_value}"
            return MilestonePlan(
                task_summary=f"Open {target_url}",
                milestones=[
                    Milestone(
                        id=1,
                        goal=f"Open {target_url}",
                        success_signal="Requested media page is open",
                        hint_tools=["open_url"],
                        deliverable_key="opened_media",
                    )
                ],
                final_response=f"Opened {target_url}.",
                source="milestone_media_shortcut",
            )

        if "play_media" not in allowed:
            return None

        media_query = self._derive_media_query(user_request) or "funny video"
        return MilestonePlan(
            task_summary=f"Open media results for {media_query}",
            milestones=[
                Milestone(
                    id=1,
                    goal=f"Open YouTube results for {media_query}",
                    success_signal=f"YouTube search results for {media_query} are open",
                    hint_tools=["play_media"],
                    deliverable_key="opened_media",
                )
            ],
            final_response=f"Opened YouTube results for {media_query}.",
            source="milestone_media_shortcut",
        )

    def build_direct_action_plan(
        self,
        user_request: str,
        world_state: WorldState,
        available_tools: Optional[List[str]] = None,
    ) -> Optional[MilestonePlan]:
        """Return a deterministic one-action plan when no milestone reasoning is needed.

        This deliberately covers only explicit, reversible or read-only actions
        with one known tool. Ambiguous, compound, or sensitive work stays on
        the normal milestone and approval path.
        """
        intent = world_state.intent or self.intent_parser.parse(user_request, world_state)
        task_graph = world_state.task_graph
        allowed_tools = set(available_tools or [])
        if intent.ambiguous or self._hard_safety_clarification_prompt(intent):
            return None

        # Browser-state questions are read-only and bounded. They must not fall
        # through to the generic milestone planner, which can confuse the word
        # "Chrome" with an instruction to open the application.
        if is_browser_tab_query(user_request) and "browser_list_tabs" in allowed_tools:
            print("[Planner] Route: browser_tab_query -> browser_list_tabs")
            return MilestonePlan(
                task_summary="Count the currently open browser tabs",
                milestones=[
                    Milestone(
                        id=1,
                        goal="Read the current browser tab count without changing Chrome",
                        success_signal="A live tab count is returned, or the missing browser bridge is explained",
                        hint_tools=["browser_list_tabs"],
                        deliverable_key="browser_tab_count",
                        direct_tool="browser_list_tabs",
                        direct_tool_args={"summary_only": True},
                    )
                ],
                final_response="",
                source="milestone_browser_tab_query",
            )

        # A current factual question is a bounded, read-only lookup.  It needs
        # a fresh source, but it should not pay the latency or UI cost of a
        # high-effort milestone plan.  Core V2 turns this gateway result into
        # the concise final response using the active ChatGPT provider.
        if (
            is_time_sensitive_information_request(user_request)
            and "get_web_information" in allowed_tools
        ):
            return MilestonePlan(
                task_summary="Look up current, source-backed information",
                milestones=[
                    Milestone(
                        id=1,
                        goal="Retrieve current information from a reliable web source",
                        success_signal="Current source data is retrieved and ready to summarize",
                        hint_tools=["get_web_information"],
                        deliverable_key="current_information",
                        direct_tool="get_web_information",
                        direct_tool_args={
                            "query": user_request,
                            "target_type": "page_summary",
                            "max_items": 5,
                            "max_chars": 6000,
                        },
                    )
                ],
                final_response="",
                source="milestone_current_information",
            )

        # Typing explicit text into the already focused field is a single,
        # bounded desktop action.  Route it directly instead of asking the
        # general planner to infer a multi-step task.  The resulting plan is
        # still approval-gated because type_text is a UI-mutating tool.
        direct_text = self._extract_explicit_text_entry(user_request)
        if direct_text and "type_text" in allowed_tools:
            target_app = (world_state.active_app or "").strip()
            destination = f" in {target_app}" if target_app else ""
            return MilestonePlan(
                task_summary=f"Type the supplied text into the active input{destination}",
                milestones=[
                    Milestone(
                        id=1,
                        goal=f"Type this exact text into the focused input{destination}: {direct_text}",
                        success_signal=(
                            "The supplied text is entered in the currently focused input"
                            f"{destination}"
                        ),
                        hint_tools=["type_text"],
                        deliverable_key="typed_text",
                        direct_tool="type_text",
                        direct_tool_args={
                            "text": direct_text,
                            "app_name": target_app,
                        },
                    )
                ],
                final_response="Typed the requested text into the focused input.",
                source="milestone_direct_text_entry",
            )

        if self._should_bypass_template_shortcuts(user_request, task_graph):
            return None

        if "read_screen" in allowed_tools and self._is_direct_visual_observation(user_request):
            return MilestonePlan(
                task_summary="Describe the visible screen",
                milestones=[
                    Milestone(
                        id=1,
                        goal="Describe the visible screen",
                        success_signal="A concise, evidence-based screen description is returned",
                        hint_tools=["read_screen"],
                        deliverable_key="screen_description",
                    )
                ],
                source="milestone_direct_screen",
            )

        media_shortcut = self._build_media_open_shortcut(
            user_request,
            intent,
            available_tools,
        )
        if media_shortcut is not None:
            return media_shortcut

        required_tool = ""
        if intent.action == IntentAction.OPEN and intent.target_type == TargetType.APP and intent.target_value:
            required_tool = "open_app"
        elif intent.action == IntentAction.OPEN and intent.target_type == TargetType.URL:
            required_tool = "open_url"
        elif intent.action == IntentAction.ANALYZE and intent.target_type == TargetType.FILE and intent.target_value:
            required_tool = "read_file"

        if not required_tool or required_tool not in allowed_tools:
            return None

        plan = self._build_sync_milestone_fallback(
            user_request,
            world_state,
            intent,
            task_graph,
        )
        if plan.needs_clarification or any(
            tool not in allowed_tools
            for milestone in plan.milestones
            for tool in milestone.hint_tools
        ):
            return None
        plan.source = "milestone_direct_action"
        return plan

    @staticmethod
    def _extract_explicit_text_entry(user_request: str) -> str:
        """Return literal text from a safe, single-field typing request.

        Examples: ``type \"Hello\"`` and ``paste: Hello``.  Relative requests
        such as "type it" deliberately stay on the regular planning path: the
        text to write must be visible in the approval card before Adele can
        modify the user's screen.
        """
        raw = (user_request or "").strip()
        if not raw:
            return ""

        destination = (
            r"(?:\s+(?:into|in|to)\s+(?:the|my|this)?\s*"
            r"(?:active|focused|current)?\s*(?:field|input|text box|document|google docs?))?"
        )
        quoted = re.fullmatch(
            r"(?:please\s+)?(?:type|paste|enter|insert)\s+"
            r"(?:the\s+following(?:\s+text)?\s*)?[\"\u201c](.+?)[\"\u201d]" + destination + r"[.!?]?",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        colon = re.fullmatch(
            r"(?:please\s+)?(?:type|paste|enter|insert)\s*[:\-]\s*(.+?)\s*",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        plain = re.fullmatch(
            r"(?:please\s+)?(?:type|paste|enter|insert)\s+(.+?)" + destination + r"[.!?]?",
            raw,
            flags=re.IGNORECASE | re.DOTALL,
        )
        match = quoted or colon or plain
        if not match:
            return ""

        text = match.group(1).strip()
        if not text or len(text) > 6000:
            return ""
        if text.lower() in {"it", "this", "that", "the above", "the story", "the draft"}:
            return ""
        return text

    @staticmethod
    def _is_direct_visual_observation(user_request: str) -> bool:
        """Recognize simple read-only screen questions that need no plan."""
        text = _norm_text(user_request)
        direct_requests = (
            "what is on my screen",
            "what's on my screen",
            "what do you see",
            "describe the screen",
            "read the screen",
            "look at my screen",
            "what is visible",
            "what's visible",
        )
        return any(marker in text for marker in direct_requests)

    def _looks_like_repeat_message_request(
        self,
        user_request: str,
        intent: UserIntent,
        world_state: WorldState,
    ) -> bool:
        if intent.action != IntentAction.COMMUNICATE:
            return False
        text = f" {_norm_text(user_request)} "
        repeat_markers = (" again ", " resend ", " repeat ", " same message ", " send it again ", " say it again ")
        if not any(marker in text for marker in repeat_markers):
            return False
        app_context = _norm_text(f"{world_state.active_app} {intent.target_value}")
        return any(marker in app_context for marker in ("whatsapp", "messages", "imessage", "slack", "discord", "telegram", "signal", "messenger"))

    def _build_repeat_message_shortcut(
        self,
        user_request: str,
        intent: UserIntent,
        world_state: WorldState,
        available_tools: Optional[List[str]] = None,
    ) -> Optional[MilestonePlan]:
        if intent.ambiguous or not self._looks_like_repeat_message_request(user_request, intent, world_state):
            return None

        allowed = set(available_tools or [])
        if not {"type_text", "press_key"}.issubset(allowed):
            return None

        hint_tools = [tool for tool in ("type_in_field", "type_text", "press_key") if tool in allowed]
        app_name = world_state.active_app or "the active chat app"
        return MilestonePlan(
            task_summary=f"Send the previous message again in {app_name}",
            milestones=[
                Milestone(
                    id=1,
                    goal=f"Send the previous message again in {app_name}",
                    success_signal="The previous message text is entered into the chat and sent",
                    hint_tools=hint_tools,
                    deliverable_key="message_sent",
                )
            ],
            final_response="Repeated the previous message.",
            source="milestone_repeat_message_shortcut",
        )

    def _try_template(self, intent: UserIntent, world_state: WorldState) -> Optional[MilestonePlan]:
        """Compatibility shim for the retired deterministic template path."""
        return None

    async def create_plan(
        self,
        user_request: str,
        world_state: WorldState,
        available_tools: Optional[List[str]] = None,
        conversation_history: Optional[List[dict]] = None
    ) -> MilestonePlan:
        """Compatibility wrapper: all requests now plan through MilestonePlan."""
        t_start = time.time()

        intent = self.intent_parser.parse(user_request, world_state)
        world_state.intent = intent
        task_graph = self.intent_parser.extract_task_graph(user_request, world_state)
        world_state.task_graph = task_graph

        print(f"[Planner] Intent: {intent.action.value} → {intent.target_type.value}:{intent.target_value} (conf={intent.confidence:.0%})")
        print(f"[Planner] Task graph: entities={len(task_graph.entities)} selectors={len(task_graph.selectors)} complexity={task_graph.complexity_score:.1f}")

        if intent.ambiguous:
            print(f"[Planner] Ambiguous request, needs clarification")
            return MilestonePlan(
                task_summary=user_request,
                needs_clarification=True,
                clarification_prompt=intent.clarification_prompt,
                source="milestone_planner",
            )

        safety_prompt = self._hard_safety_clarification_prompt(intent)
        if safety_prompt:
            print(f"[Planner] Hard safety clarification ({time.time() - t_start:.2f}s)")
            return MilestonePlan(
                task_summary=user_request,
                needs_clarification=True,
                clarification_prompt=safety_prompt,
                source="milestone_planner",
            )

        repeat_message_shortcut = self._build_repeat_message_shortcut(user_request, intent, world_state, available_tools)
        if repeat_message_shortcut is not None:
            print(f"[Planner] Repeat message shortcut ({time.time() - t_start:.2f}s)")
            return repeat_message_shortcut

        media_shortcut = self._build_media_open_shortcut(user_request, intent, available_tools)
        if media_shortcut is not None:
            print(f"[Planner] Direct media shortcut ({time.time() - t_start:.2f}s)")
            return media_shortcut

        skill_candidates = self.template_registry.get_skill_candidates(
            user_request=user_request,
            intent=intent,
            world_state=world_state,
            available_tools=available_tools,
            limit=3,
        )
        skill_context = self.template_registry.format_skill_context(skill_candidates)
        skill_names = self.template_registry.skill_names(skill_candidates)
        if skill_candidates:
            print(f"[Planner] Active skill overlays: {', '.join(skill_names)}")

        milestone_plan = await self.create_milestone_plan(
            user_request=user_request,
            world_state=world_state,
            conversation_history=conversation_history,
            available_tools=available_tools,
            skill_context=skill_context,
            skill_names=skill_names,
        )
        if milestone_plan is None:
            return MilestonePlan(
                task_summary=user_request,
                needs_clarification=True,
                clarification_prompt="I couldn't generate a milestone plan for that. Please try rephrasing it.",
                source="milestone_planner",
            )

        elapsed = time.time() - t_start
        print(f"[Planner] Unified milestone plan ready ({elapsed:.2f}s)")
        return milestone_plan

    # ═══════════════════════════════════════════════════════════════
    #  Milestone Planning (V3)
    # ═══════════════════════════════════════════════════════════════

    async def create_milestone_plan(
        self,
        user_request: str,
        world_state: WorldState,
        conversation_history: Optional[List[dict]] = None,
        available_tools: Optional[List[str]] = None,
        skill_context: str = "",
        skill_names: Optional[List[str]] = None,
        supplemental_context: str = "",
        thinking_level: str = "HIGH",
    ) -> Optional[MilestonePlan]:
        """
        Generate a milestone-based plan for a request.

        Returns None if no LLM provider is available or the model does not
        return usable plan JSON. Callers can then apply a deterministic
        milestone fallback or request clarification.
        """
        self.last_failure = None
        intent = world_state.intent or self.intent_parser.parse(user_request, world_state)
        repeat_message_shortcut = self._build_repeat_message_shortcut(user_request, intent, world_state, available_tools)
        if repeat_message_shortcut is not None:
            return repeat_message_shortcut

        media_shortcut = self._build_media_open_shortcut(user_request, intent, available_tools)
        if media_shortcut is not None:
            return media_shortcut

        if not self.provider and not self._adk_planning_enabled():
            return None

        t_start = time.time()

        if not skill_context:
            candidates = self.template_registry.get_skill_candidates(
                user_request=user_request,
                intent=intent,
                world_state=world_state,
                available_tools=available_tools,
                limit=3,
            )
            skill_context = self.template_registry.format_skill_context(candidates)
            if skill_names is None:
                skill_names = self.template_registry.skill_names(candidates)
        if skill_names:
            print(f"[Planner] Milestone skill overlays: {', '.join(skill_names)}")

        # Build the filtered LLM-facing tool surface for planning.
        tool_categories = self._get_tool_category_summary(available_tools)

        # Conversation context
        conversation_context = "(none)"
        if conversation_history and len(conversation_history) > 1:
            parts = []
            for turn in conversation_history[:-1]:
                role = turn.get("role", "")
                text = ""
                for part in turn.get("parts", []):
                    if "text" in part:
                        text = part["text"]
                        break
                if text and role in ("user", "model"):
                    label = "User" if role == "user" else "Assistant"
                    parts.append(f"  {label}: {text[:200]}")
            if parts:
                conversation_context = "\n".join(parts)

        prompt = MILESTONE_PLANNING_PROMPT.format(
            tool_categories=tool_categories,
            world_state=world_state.to_prompt_string(),
            user_request=user_request,
            conversation_context=conversation_context,
            supplemental_context=supplemental_context or "(none)",
            skill_context=skill_context or "(none)",
        )

        if self._adk_planning_enabled():
            try:
                from adk_agent.planner import get_adk_milestone_planner

                adk_plan = await get_adk_milestone_planner().plan(
                    user_prompt=prompt,
                    parse_fn=self._parse_milestone_response,
                    user_request=user_request,
                )
                if adk_plan is not None:
                    adk_plan.skill_context = skill_context or ""
                    adk_plan.skills_used = list(skill_names or [])
                    return adk_plan
            except Exception as exc:
                print(f"[Planner] ⚠ ADK planning unavailable: {exc}")

        try:
            response = await self._generate_with_compat(
                messages=[{"role": "user", "parts": [{"text": prompt}]}],
                system_prompt=MILESTONE_PLANNING_SYSTEM,
                tools=[],
                temperature=0.15,
                thinking_level=thinking_level,
                enable_builtin_tools=False,
            )
            if not response:
                self._record_planner_failure("no_response")
                return None
            if getattr(response, "error", None):
                self._record_planner_failure("provider_error")
                return None
            if not response.text:
                self._record_planner_failure("empty_response")
                return None

            try:
                plan = self._parse_milestone_response(response.text, user_request)
            except (ValueError, TypeError, json.JSONDecodeError):
                # GPT-5.6 uses prompt-constrained JSON here.  Retry only an
                # invalid response, rather than immediately falling back.
                repair_prompt = (
                    f"{prompt}\n\n"
                    "Your previous reply was not a valid ADELE milestone plan. "
                    "Return ONLY one valid JSON object in the exact Output Format "
                    "above. Do not include markdown, explanations, tool calls, "
                    "or any text before or after the JSON."
                )
                retry = await self._generate_with_compat(
                    messages=[{"role": "user", "parts": [{"text": repair_prompt}]}],
                    system_prompt=MILESTONE_PLANNING_SYSTEM,
                    tools=[],
                    temperature=0.0,
                    thinking_level=thinking_level,
                    enable_builtin_tools=False,
                )
                if not retry or getattr(retry, "error", None) or not retry.text:
                    self._record_planner_failure("plan_repair_unavailable")
                    return None
                try:
                    plan = self._parse_milestone_response(retry.text, user_request)
                except (ValueError, TypeError, json.JSONDecodeError):
                    self._record_planner_failure("malformed_plan_json")
                    return None

            plan.skill_context = skill_context or ""
            plan.skills_used = list(skill_names or [])
            elapsed = time.time() - t_start
            print(f"[Planner] 🎯 Milestone plan generated ({elapsed:.2f}s, "
                  f"{len(plan.milestones)} milestones)")
            return plan

        except asyncio.CancelledError:
            raise
        except Exception:
            self._record_planner_failure("planner_exception")
            return None

    def _record_planner_failure(self, code: str) -> None:
        """Record a safe planner diagnostic without user or system data."""
        self.last_failure = code
        print(f"[Planner] Milestone planning unavailable ({code}).")

    def _parse_milestone_response(self, text: str, user_request: str) -> MilestonePlan:
        """Parse an LLM milestone plan response into a MilestonePlan."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            first_nl = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
            cleaned = cleaned[first_nl + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(cleaned[start:end])
            else:
                raise ValueError("Could not parse milestone plan JSON")

        if data.get("needs_clarification"):
            return MilestonePlan(
                task_summary=data.get("task_summary", user_request),
                needs_clarification=True,
                clarification_prompt=data.get("clarification_prompt", ""),
            )

        milestones = []
        for m_data in data.get("milestones", []):
            raw_hints = m_data.get("hint_tools", [])
            sanitized_hints = self._sanitize_hint_tools(raw_hints)
            milestones.append(Milestone(
                id=m_data.get("id", len(milestones) + 1),
                goal=m_data.get("goal", ""),
                success_signal=m_data.get("success_signal", ""),
                hint_tools=sanitized_hints,
                depends_on=m_data.get("depends_on", []),
                deliverable_key=m_data.get("deliverable_key", ""),
            ))

        if not milestones:
            raise ValueError("Milestone plan did not include any milestones")

        return MilestonePlan(
            task_summary=data.get("task_summary", user_request),
            milestones=milestones,
            final_response=data.get("final_response", "Done!"),
            source="milestone_planner",
        )

    # Map commonly hallucinated tool names to their real equivalents
    _HALLUCINATED_TOOL_MAP: dict[str, list[str]] = {
        "computer_interface": ["click_ui", "type_in_field", "get_ui_tree"],
        "computer_control": ["click_ui", "type_in_field", "type_text", "press_key"],
        "computer_interaction": ["click_ui", "type_in_field", "type_text"],
        "open_application": ["open_app"],
        "close_application": ["quit_app"],
        "bash": ["run_shell"],
        "terminal": ["run_shell"],
        "shell": ["run_shell"],
        "browser": ["open_url", "browser_read_page"],
        "screenshot": ["read_screen"],
        "search": ["get_web_information"],
        "web_browse": ["open_url", "get_web_information"],
        "keyboard": ["press_key", "type_text"],
        "mouse": ["click_ui"],
        "ui_interact": ["click_ui", "type_in_field"],
        "desktop_interact": ["click_ui", "type_in_field", "get_ui_tree"],
    }

    def _sanitize_hint_tools(self, raw_hints: list) -> list[str]:
        """Map hallucinated tool names to real ones and drop unknowns."""
        available = set()
        if self.tool_registry:
            try:
                available = {d["name"] for d in self.tool_registry.declarations()}
            except Exception:
                pass

        sanitized: list[str] = []
        seen: set[str] = set()
        for hint in raw_hints or []:
            tool_name = str(hint).strip()
            if not tool_name:
                continue
            # Already a valid tool
            if not available or tool_name in available:
                if tool_name not in seen:
                    sanitized.append(tool_name)
                    seen.add(tool_name)
                continue
            # Try mapping hallucinated name → real tools
            mapped = self._HALLUCINATED_TOOL_MAP.get(tool_name.lower(), [])
            for real_tool in mapped:
                if (not available or real_tool in available) and real_tool not in seen:
                    sanitized.append(real_tool)
                    seen.add(real_tool)
            if not mapped:
                print(f"[Planner] ⚠ Dropping unknown hint_tool '{tool_name}'")
        return sanitized

    def _get_tool_category_summary(self, available_tools: Optional[List[str]] = None) -> str:
        """Build the filtered tool summary used by the milestone planner."""
        selector = get_tool_selector(self.tool_registry) if self.tool_registry else None
        if selector is None:
            selector = get_tool_selector()
        summary = selector.format_planning_tool_summary(available_tools)
        if summary.strip() == "(no tools available)":
            return "\n".join([
                "Browser/Web: get_web_information, find_and_act, browser_read_page, browser_click_match",
                "Google Workspace: gdocs_create, gdocs_read, gdocs_append, gsheets_read, gmail_read",
                "Desktop/UI: open_app, click_ui, type_in_field, press_key, read_screen",
                "Files: read_file, write_file, list_directory",
            ])
        return summary

    def _is_compound_task_graph(self, task_graph: Optional[TaskGraph]) -> bool:
        if not task_graph:
            return False
        entity_types = task_graph.entity_types()
        if len(entity_types) >= 2:
            return True
        if len(task_graph.selectors) >= 1 and len(task_graph.entities) >= 1:
            return True
        if len(task_graph.desired_outcomes) >= 2:
            return True
        if task_graph.complexity_score >= 3.0:
            return True
        return False

    def _should_bypass_template_shortcuts(self, user_request: str, task_graph: Optional[TaskGraph]) -> bool:
        text = (user_request or "").lower()
        if self._is_compound_task_graph(task_graph):
            return True

        compound_markers = (
            " and ", " then ", " after ", " before ", " using ", " with ",
            " from ", " into ", " latest ", " newest ", " most recent ",
        )
        if any(marker in f" {text} " for marker in compound_markers):
            return True
        return False

    def should_use_milestones(
        self,
        user_request: str,
        task_summary: str = "",
        task_graph: Optional[TaskGraph] = None,
    ) -> bool:
        """Return whether this request needs high-effort milestone reasoning.

        Single, explicit actions can still use a one-milestone executor plan,
        but do not need the slower high-effort planning pass. Compound,
        research, writing, communication, destructive, and unclear work keeps
        full milestone reasoning.
        """
        task_graph = task_graph or self.intent_parser.extract_task_graph(user_request)
        if self._is_compound_task_graph(task_graph) or self._should_bypass_template_shortcuts(user_request, task_graph):
            return True

        intent = self.intent_parser.parse(user_request)
        if intent.ambiguous:
            return True
        if intent.action in {
            IntentAction.CREATE,
            IntentAction.DELETE,
            IntentAction.COMMUNICATE,
            IntentAction.EXECUTE,
            IntentAction.SEARCH,
        }:
            return True

        complex_markers = (
            "research", "investigate", "analyze", "analyse", "compare",
            "report", "brief", "document", "summarize", "summarise",
        )
        text = f" {user_request.lower()} {task_summary.lower()} "
        return any(marker in text for marker in complex_markers)

    def _hard_safety_clarification_prompt(self, intent: UserIntent) -> Optional[str]:
        """Return a clarification prompt for destructive requests, if needed."""
        text = (intent.raw_text or "").lower()
        dangerous_markers = (
            "rm -rf /",
            "delete production database",
            "drop all tables",
            "wipe my hard drive",
            "format my disk",
        )
        if any(marker in text for marker in dangerous_markers):
            return "This looks destructive and irreversible. I need explicit confirmation with exact scope before proceeding."
        return None

    def _is_research_document_request(self, user_request: str, task_summary: str) -> bool:
        text = f"{user_request or ''} {task_summary or ''}".lower()
        research_terms = ("research", "investigate", "analyze", "analyse", "compare", "study", "find", "look up", "best")
        document_terms = ("document", "report", "write up", "write-up", "brief", "paper", "article", "essay")
        return any(t in text for t in research_terms) and any(t in text for t in document_terms)

    def _is_general_research_request(self, user_request: str, task_summary: str) -> bool:
        text = f"{user_request or ''} {task_summary or ''}".lower()
        strong_markers = ("research", "investigate", "study", "analyze", "analyse", "compare")
        weak_markers = ("look up", "look-up", "find me", "find the best", "best", "top")
        return any(marker in text for marker in strong_markers) or any(marker in text for marker in weak_markers)

    def _build_sync_milestone_fallback(
        self,
        user_request: str,
        world_state: WorldState,
        intent: UserIntent,
        task_graph: Optional[TaskGraph] = None,
        *,
        skill_context: str = "",
        skill_names: Optional[List[str]] = None,
    ) -> MilestonePlan:
        """Deterministic milestone fallback for sync/LLM-unavailable callers."""
        skill_names = list(skill_names or [])

        if intent.ambiguous:
            return MilestonePlan(
                task_summary=user_request,
                needs_clarification=True,
                clarification_prompt=intent.clarification_prompt,
                skill_context=skill_context,
                skills_used=skill_names,
                source="milestone_sync_fallback",
            )

        if intent.action == IntentAction.OPEN and intent.target_type == TargetType.APP and intent.target_value:
            return MilestonePlan(
                task_summary=f"Open {intent.target_value}",
                milestones=[
                    Milestone(
                        id=1,
                        goal=f"Open {intent.target_value}",
                        success_signal=f"{intent.target_value} is open or focused",
                        hint_tools=["open_app"],
                        deliverable_key="app_opened",
                        direct_tool="open_app",
                        direct_tool_args={"app_name": intent.target_value},
                    )
                ],
                final_response=f"Opened {intent.target_value}.",
                skill_context=skill_context,
                skills_used=skill_names,
                source="milestone_sync_fallback",
            )

        if intent.action == IntentAction.OPEN and intent.target_type == TargetType.URL:
            target_url = intent.target_value or world_state.browser_url or ""
            if target_url and not target_url.startswith(("http://", "https://")):
                target_url = f"https://{target_url}"
            return MilestonePlan(
                task_summary=f"Open {target_url or 'the requested URL'}",
                milestones=[
                    Milestone(
                        id=1,
                        goal=f"Open {target_url or 'the requested URL'}",
                        success_signal="Requested page is open",
                        hint_tools=["open_url"],
                        deliverable_key="opened_url",
                        direct_tool="open_url",
                        direct_tool_args={"url": target_url},
                    )
                ],
                final_response=f"Opened {target_url or 'the requested URL'}.",
                skill_context=skill_context,
                skills_used=skill_names,
                source="milestone_sync_fallback",
            )

        if intent.action == IntentAction.ANALYZE and intent.target_type == TargetType.FILE and intent.target_value:
            return MilestonePlan(
                task_summary=f"Read {intent.target_value}",
                milestones=[
                    Milestone(
                        id=1,
                        goal=f"Read {intent.target_value}",
                        success_signal="File contents are retrieved",
                        hint_tools=["read_file"],
                        deliverable_key="file_contents",
                    )
                ],
                final_response=f"Read {intent.target_value}.",
                skill_context=skill_context,
                skills_used=skill_names,
                source="milestone_sync_fallback",
            )

        if task_graph and self._is_compound_task_graph(task_graph):
            return MilestonePlan(
                task_summary=user_request,
                needs_clarification=True,
                clarification_prompt=(
                    "I need the milestone planner to break that down, but no async planning provider "
                    "is available in this sync path."
                ),
                skill_context=skill_context,
                skills_used=skill_names,
                source="milestone_sync_fallback",
            )

        return MilestonePlan(
            task_summary=user_request,
            needs_clarification=True,
            clarification_prompt="I'm not sure how to help with that. Could you be more specific?",
            skill_context=skill_context,
            skills_used=skill_names,
            source="milestone_sync_fallback",
        )

    # ═══════════════════════════════════════════════════════════════
    #  Dynamic Replanning
    # ═══════════════════════════════════════════════════════════════

    async def replan_remaining(
        self,
        plan: MilestonePlan,
        failed_milestone_id: int,
        failure_reason: str,
        deliverables: dict,
    ) -> list:
        """
        Re-plan the remaining milestones after a failure.

        Args:
            plan: The current MilestonePlan being executed.
            failed_milestone_id: ID of the milestone that failed.
            failure_reason: Description of why it failed.
            deliverables: Dict of milestone_id → deliverable string from completed milestones.

        Returns:
            A list of revised Milestone objects to replace the remaining milestones.
            Returns an empty list if replanning fails or the failure is unrecoverable.
        """
        completed_lines = []
        remaining_lines = []
        failed_goal = ""

        for m in plan.milestones:
            if m.status == MilestoneStatus.COMPLETED:
                completed_lines.append(
                    f"  M{m.id}: {m.goal} → ✅ {m.result_summary[:120]}"
                )
            elif m.id == failed_milestone_id:
                failed_goal = m.goal
            elif m.status == MilestoneStatus.PENDING:
                remaining_lines.append(
                    f"  M{m.id}: {m.goal} (depends_on={m.depends_on})"
                )

        deliverables_lines = []
        for mid, value in deliverables.items():
            deliverables_lines.append(f"  M{mid}: {str(value)[:200]}")

        next_id = max((m.id for m in plan.milestones), default=0) + 1

        prompt = REPLAN_PROMPT.format(
            failed_id=failed_milestone_id,
            user_request=plan.task_summary,
            task_summary=plan.task_summary,
            completed_summary="\n".join(completed_lines) or "(none)",
            failed_goal=failed_goal,
            failure_reason=failure_reason[:500],
            remaining_summary="\n".join(remaining_lines) or "(none)",
            deliverables_summary="\n".join(deliverables_lines) or "(none)",
            next_id=next_id,
        )

        # Try LLM replanning
        if self.provider:
            try:
                from providers.gemini import MILESTONE_PLAN_JSON_SCHEMA

                response = await self.provider.generate(
                    messages=[{"role": "user", "parts": [{"text": prompt}]}],
                    system_prompt=MILESTONE_PLANNING_SYSTEM,
                    tools=[],
                    temperature=0.2,
                    thinking_level="HIGH",
                    response_json_schema=MILESTONE_PLAN_JSON_SCHEMA,
                    enable_builtin_tools=False,
                )
                if response and response.text:
                    milestones = self._parse_replan_response(
                        response.text, next_id
                    )
                    if milestones is not None:
                        print(
                            f"[Planner] 🔄 Replanned: {len(milestones)} revised "
                            f"milestone(s) after M{failed_milestone_id} failure"
                        )
                        return milestones
            except Exception as e:
                print(f"[Planner] ⚠ LLM replanning failed: {e}")

        # Fallback: generate a single retry milestone
        print(f"[Planner] 🔄 Fallback replan: single retry milestone")
        return [
            Milestone(
                id=next_id,
                goal=f"Retry: {failed_goal}",
                success_signal=f"The goal '{failed_goal}' is achieved",
                hint_tools=[],
                deliverable_key=f"retry_{failed_milestone_id}",
            )
        ]

    def _parse_replan_response(
        self, text: str, start_id: int
    ) -> Optional[list]:
        """Parse the LLM replan response into a list of Milestone objects."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            first_nl = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
            cleaned = cleaned[first_nl + 1:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            print(f"[Planner] ⚠ Replan JSON parse failed")
            return None

        raw_milestones = data.get("milestones", [])
        if not isinstance(raw_milestones, list):
            return None

        recovery = data.get("recovery_strategy", "")
        if recovery:
            print(f"[Planner] 🔄 Recovery strategy: {recovery[:150]}")

        milestones = []
        for idx, m in enumerate(raw_milestones):
            if not isinstance(m, dict):
                continue
            milestones.append(
                Milestone(
                    id=m.get("id", start_id + idx),
                    goal=m.get("goal", "Unknown goal"),
                    success_signal=m.get("success_signal", ""),
                    hint_tools=m.get("hint_tools", []),
                    depends_on=m.get("depends_on", []),
                    deliverable_key=m.get("deliverable_key", ""),
                )
            )

        return milestones if milestones else None

    def create_plan_sync(
        self,
        user_request: str,
        world_state: WorldState
    ) -> MilestonePlan:
        """
        Synchronous compatibility planner.

        The sync path no longer emits ExecutionPlans or invokes template
        short-circuits. It returns a deterministic MilestonePlan fallback.
        """
        intent = self.intent_parser.parse(user_request, world_state)
        world_state.intent = intent
        task_graph = self.intent_parser.extract_task_graph(user_request, world_state)
        world_state.task_graph = task_graph

        safety_prompt = self._hard_safety_clarification_prompt(intent)
        if safety_prompt:
            return MilestonePlan(
                task_summary=user_request,
                needs_clarification=True,
                clarification_prompt=safety_prompt,
                source="milestone_sync_fallback",
            )

        skill_candidates = self.template_registry.get_skill_candidates(
            user_request=user_request,
            intent=intent,
            world_state=world_state,
            available_tools=None,
        )
        skill_context = self.template_registry.format_skill_context(skill_candidates)
        skill_names = self.template_registry.skill_names(skill_candidates)

        return self._build_sync_milestone_fallback(
            user_request=user_request,
            world_state=world_state,
            intent=intent,
            task_graph=task_graph,
            skill_context=skill_context if skill_context != "(none)" else "",
            skill_names=skill_names,
        )
