"""
ADELE — Agent Core V2
=========================
Sense-Plan-Act-Verify (SPAV) architecture for improved tool calling.

Key improvements over V1:
  1. Structured WorldState instead of raw context strings
  2. Explicit milestone planning before execution
  3. Milestone micro-loop execution with verification
  4. Intelligent tool selection (reduced from 30+ to a focused request surface)
  5. Better error recovery with evidence-gated completion
"""

import asyncio
import json
import time as _time
import os
import uuid
import random as _random
import re as _re
from typing import Callable, Optional, Awaitable, List
from functools import partial
from dataclasses import dataclass, field
from urllib.parse import urlparse

print = partial(print, flush=True)

# Load .env file
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# ADELE V2 modules
from agent.world_state import WorldState, UserIntent, IntentParser, EntityExtractor, IntentAction
from agent.planner import ExecutionStep, StepStatus
from agent.planner import MilestonePlan, Milestone, MilestoneStatus
from agent.task_planner import TaskPlanner
from agent.verifier import get_verifier
from agent.memory import ConversationMemory, UserPreferences, TaskStore, UserProfile, WorkingMemory, VaultMemory
from agent.workspace_prompts import format_for_system_prompt, load_workspace_prompt_bundle
from tools.selector import get_tool_selector, set_tool_gateway_context, set_web_progress_callback
from tools import registry as tool_registry
from tools.registry import set_automation_cursor_callback
from providers.router import ModelRouter
from providers import LLMProvider
import agent.perception as perception
from agent.plan_journal import (
    journal_execution_snapshot,
    journal_pending_approval,
    journal_request_trace,
)


# ═══════════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════════

PENDING_PLAN_TTL_SECONDS = 600


def _trace_error_code(value: object) -> str:
    """Collapse failures into safe diagnostic categories without logging text."""
    normalized = str(value or "").lower()
    if "timeout" in normalized or "timed out" in normalized:
        return "timeout"
    if "approval" in normalized or "confirm" in normalized:
        return "approval_required"
    if "verify" in normalized or "still running" in normalized:
        return "verification_failed"
    if "unavailable" in normalized or "not connected" in normalized:
        return "unavailable"
    if "tool" in normalized or "execute" in normalized:
        return "tool_execution_failed"
    if normalized:
        return "request_failed"
    return "unknown"

# Browser timing — seconds to wait after navigation actions so the page
# has time to load and the snapshot can be refreshed.  Centralised here
# instead of scattered as magic numbers throughout _execute_step().
BROWSER_NAV_SETTLE_S = 0.3      # reduced — snapshot event-wait handles the real delay
BROWSER_RECOVERY_SETTLE_S = 0.2 # after refresh_refs recovery

BROWSER_APP_NAMES = {
    "google chrome",
    "chrome",
    "safari",
    "arc",
    "brave browser",
    "firefox",
    "microsoft edge",
    "edge",
}

WEB_FLOW_TOOLS = {
    "open_url",
    "get_web_information",
    "web_search",
    "fetch_web_content",
    "web_scrape",
    "browser_snapshot",
    "browser_read_page",
    "browser_read_text",
    "read_page_content",
    "extract_structured_data",
    "get_page_summary",
    "browser_find",
    "browser_click_match",
    "browser_click_ref",
    "browser_type_ref",
    "browser_select_ref",
    "browser_refresh_refs",
    "browser_scroll",
    "browser_wait_for",
    "browser_list_tabs",
    "browser_switch_tab",
    "gdocs_create",
    "gdocs_append",
    "gdocs_read",
    "gworkspace_analyze",
}

# Simplified system prompt for V2 (planning is done separately)
SYSTEM_PROMPT_V2 = """You are ADELE, a cross-platform desktop assistant.

## Personality & Tone
- Warm, helpful, and efficient — like a capable friend, not a corporate bot.
- Keep responses concise (1-3 sentences for simple tasks). Be direct.
- Occasionally use light humor or personality, but never force it.
- Use the user's name naturally when you know it (from profile).
- Match the user's energy — enthusiastic with excited users, calm with
  frustrated ones, casual with casual tone, professional when appropriate.
- When something goes wrong, be empathetic and solution-focused.
- Celebrate successes briefly ("Done!", "All set!") but don't be over-the-top.
- Remember: you're voice-first. Write responses that sound natural when spoken aloud.

## Reasoning Protocol (MANDATORY)
Before EVERY tool call you MUST include a `reasoning` argument — one sentence
explaining WHY you are calling that tool and what you expect the result to be.

Never request or reveal private chain-of-thought. The reasoning argument is a
brief, user-safe justification for the requested action.

Core behavior:
- Requests are voice-transcribed; correct obvious transcription errors.
- Resolve references ("it", "that", "go ahead") from conversation history + desktop context.
- Prefer action over clarification when context resolves ambiguity.

Tooling rules:
- App/URL control: `open_app`, `open_url`, `quit_app`, `close_window`.
- UI interaction: prefer `click_ui` and `type_in_field`.
- Browser interaction: use extension tools (`browser_read_page`, `browser_click_match`, `browser_click_ref`, `browser_type_ref`, `browser_select_ref`).
- Browser scrolling: use `browser_scroll`, not `press_key`.
- For time-sensitive factual questions (for example current results, rosters,
  prices, schedules, or news), call `get_web_information` before answering.
  Do not rely on static model knowledge for a request that could have changed.
- Use `run_shell` only for real shell/file/system tasks, never for browser/UI automation.
- For file edits: read first (`read_file`), then mutate (`replace_in_file`/`write_file`).
- For Google Docs/Sheets/Slides/Gmail/Calendar, prefer dedicated `g*` API tools.

Communication rules:
- `send_response` is the final user message for completed work.
- `await_reply` is only for a true blocking question.
- Do not emit raw conversational text outside these tools.
"""

# WebSocket callback type
WSCallback = Callable[[dict], Awaitable[None]]


@dataclass
class PendingPlanState:
    """Frozen plan awaiting explicit user approval."""
    plan_id: str
    plan: MilestonePlan
    created_at: float
    context_fingerprint: dict
    provider: Optional[LLMProvider]
    original_user_request: str
    selected_tools: List[str] = field(default_factory=list)
    stale_replan_count: int = 0


@dataclass
class PendingExecutionState:
    """Suspended milestone execution awaiting user follow-up."""
    execution_id: str
    plan: MilestonePlan
    created_at: float
    provider: Optional[LLMProvider]
    original_user_request: str
    selected_tools: List[str] = field(default_factory=list)
    deliverables: dict[int, str] = field(default_factory=dict)
    milestone_step_results: dict[int, str] = field(default_factory=dict)
    milestone_step_result_idx: int = 0
    suspended_milestone_id: int = 0
    await_payload: dict = field(default_factory=dict)
    followup_inputs: List[str] = field(default_factory=list)
    blocked_await_signatures: List[str] = field(default_factory=list)
    last_opened_url: str = ""


# ═══════════════════════════════════════════════════════════════
#  Agent V2 Class
# ═══════════════════════════════════════════════════════════════

class AdeleAgentV2:
    """
    V2 Agent with Sense-Plan-Act-Verify architecture.
    
    Flow:
    1. SENSE: Build structured WorldState from context
    2. PLAN: Generate a milestone plan
    3. ACT: Execute milestones via the LLM micro-loop
    4. VERIFY: Check success and handle failures
    """

    def __init__(self, use_planning: bool = True, persist: bool = True):
        """
        Initialize the V2 agent.
        
        Args:
            use_planning: If True, use LLM for complex planning. 
                         If False, use only rule-based templates (faster).
            persist: If True, persist conversation sessions to disk.
                    Set False for benchmarks / tests.
        """
        # Memory systems
        self.conversation = ConversationMemory(max_turns=30, idle_timeout=600, persist=persist)
        self.preferences = UserPreferences()
        self.user_profile = UserProfile()
        self.task_store = TaskStore()
        self.working_memory = WorkingMemory(max_actions=40, max_entities=60)
        self.vault = VaultMemory()
        
        # Routing
        self.router = ModelRouter()
        self._pending_reply_provider: Optional[LLMProvider] = None
        
        # V2 components
        self.intent_parser = IntentParser()
        self.entity_extractor = EntityExtractor()
        self.tool_selector = get_tool_selector(tool_registry)
        self.verifier = get_verifier(router=self.router)
        self.planner: Optional[TaskPlanner] = None  # Lazy init with provider
        self._pending_plan: Optional[PendingPlanState] = None
        self._pending_execution: Optional[PendingExecutionState] = None
        self._last_opened_url: str = ""
        
        # Configuration
        self.use_planning = use_planning

    def _build_system_prompt(self) -> str:
        """Build the system prompt with user preferences, profile, and working memory."""
        prompt = SYSTEM_PROMPT_V2
        ws = format_for_system_prompt(load_workspace_prompt_bundle())
        if ws:
            prompt += ws
        prefs = self.preferences.to_prompt_string()
        if prefs:
            prompt += f"\n\n{prefs}"
        profile = self.user_profile.to_prompt_string()
        if profile:
            prompt += f"\n\n{profile}"
        # Inject working memory (recent actions, entities, session goal)
        wm = self.working_memory.to_prompt_string()
        if wm:
            prompt += f"\n\n{wm}"
        # Inject vault memory summary (permanent cross-session knowledge)
        vault_summary = self.vault.to_prompt_string()
        if vault_summary:
            prompt += f"\n\n{vault_summary}"
        return prompt

    def _context_fingerprint(self, context: perception.ContextSnapshot) -> dict:
        app = (context.active_app or "").strip().lower()
        domain = ""
        if context.browser_url:
            try:
                domain = (urlparse(context.browser_url).netloc or "").lower()
            except Exception:
                domain = ""
        return {
            "active_app": app,
            "browser_domain": domain,
        }

    def _classify_pending_followup(self, text: str) -> str:
        normalized = " ".join((text or "").strip().lower().split())
        if not normalized:
            return "modify"
        import re

        def _has_term(term: str) -> bool:
            if " " in term:
                return term in normalized
            return re.search(rf"\b{re.escape(term)}\b", normalized) is not None

        cancel_terms = (
            "cancel",
            "never mind",
            "nevermind",
            "stop",
            "abort",
            "dismiss",
            "don't",
            "do not",
            "no thanks",
            "no",
        )
        modify_terms = (
            "change",
            "modify",
            "instead",
            "but",
            "except",
            "skip",
            "remove",
            "add",
            "edit",
            "update",
        )
        approve_terms = (
            "proceed",
            "go ahead",
            "yes",
            "approved",
            "approve",
            "start",
            "continue",
            "do it",
            "looks good",
            "ok",
            "okay",
        )
        if any(_has_term(term) for term in cancel_terms):
            return "cancel"
        if any(_has_term(term) for term in modify_terms):
            return "modify"
        if any(_has_term(term) for term in approve_terms):
            return "approve"
        return "modify"

    # ── Instant Acknowledgment ──────────────────────────────────

    _ACK_ACTION = [
        "On it!", "Sure thing", "Got it", "Working on it",
        "One sec", "Right away", "Let me handle that",
    ]
    _ACK_QUESTION = [
        "Let me check", "Good question", "Looking into it",
        "One moment", "Let me find out",
    ]
    _ACK_RESEARCH = [
        "Let me look into that", "Searching now",
        "I'll dig into that", "Researching",
    ]

    def _pick_ack(self, user_text: str) -> str:
        """Pick a natural acknowledgment phrase based on request type."""
        lower = user_text.strip().lower()
        # Questions
        if any(lower.startswith(w) for w in ("what", "how", "why", "who", "where", "when", "is ", "are ", "can ", "do ", "does ")):
            return _random.choice(self._ACK_QUESTION)
        # Research-like
        if any(w in lower for w in ("research", "find", "search", "look up", "compare")):
            return _random.choice(self._ACK_RESEARCH)
        # Default action
        return _random.choice(self._ACK_ACTION)

    # ── Small-Talk Fast Path ────────────────────────────────────

    _GREETING_PATTERNS = _re.compile(
        r"^\s*(?:hey|hi|hello|good\s+(?:morning|afternoon|evening)|howdy|sup|what'?s\s+up|yo)\s*[!.?]?\s*$",
        _re.IGNORECASE,
    )
    _THANKS_PATTERNS = _re.compile(
        r"^\s*(?:thanks?(?:\s+you)?|thank\s+you(?:\s+so\s+much)?|thx|cheers|appreciate\s+it)\s*[!.?]?\s*$",
        _re.IGNORECASE,
    )
    _FAREWELL_PATTERNS = _re.compile(
        r"^\s*(?:bye|goodbye|see\s+you|later|good\s*night|take\s+care|peace)\s*[!.?]?\s*$",
        _re.IGNORECASE,
    )
    _MOOD_PATTERNS = _re.compile(
        r"^\s*(?:how\s+are\s+you|how'?s\s+it\s+going|how\s+do\s+you\s+feel|are\s+you\s+there)\s*[?!.]?\s*$",
        _re.IGNORECASE,
    )
    _SIMPLE_FACTUAL = _re.compile(
        r"^\s*(?:what(?:'s| is)\s+the\s+(?:time|date|day)|what\s+time\s+is\s+it|what\s+day\s+is\s+(?:it|today))\s*[?]?\s*$",
        _re.IGNORECASE,
    )

    _VAULT_USER_SEPARATOR = "\n---\nUser:\n"
    _DIRECT_SCREEN_QUESTION_MARKERS = (
        "what can you see",
        "what do you see",
        "what is on my screen",
        "what's on my screen",
        "describe the screen",
        "read the screen",
        "look at my screen",
        "what is visible",
        "what's visible",
    )
    _ACTION_REQUEST_MARKERS = (
        "open",
        "launch",
        "click",
        "tap",
        "type",
        "send",
        "delete",
        "remove",
        "close",
        "create",
        "write",
        "download",
        "install",
        "search",
        "find",
        "play",
        "start",
        "stop",
    )
    _CONTENT_REQUEST_NOUNS = (
        "story",
        "poem",
        "essay",
        "script",
        "outline",
        "draft",
        "bio",
        "caption",
        "post",
        "message",
        "email",
        "letter",
        "speech",
        "proposal",
        "summary",
        "summary",
    )
    _DESKTOP_INSERTION_PATTERNS = (
        r"\b(?:type|paste|insert|put|enter)\b",
        r"\b(?:write|draft|create|generate)\b.*?\b(?:in|into|on)\s+"
        r"(?:my|the|this)?\s*(?:google docs?|document|notepad|editor|text box|form)\b",
    )

    @classmethod
    def _visible_user_request(cls, text: str) -> str:
        """Remove the internal vault envelope before classifying speech."""
        raw = str(text or "")
        if cls._VAULT_USER_SEPARATOR in raw:
            return raw.rsplit(cls._VAULT_USER_SEPARATOR, 1)[-1].strip()
        return raw.strip()

    @classmethod
    def _vault_retrieval_context(cls, text: str) -> str:
        """Extract local vault recall without mixing it into the user command."""
        raw = str(text or "")
        if cls._VAULT_USER_SEPARATOR not in raw:
            return ""
        return raw.rsplit(cls._VAULT_USER_SEPARATOR, 1)[0].strip()

    @classmethod
    def _is_contextual_guidance_question(cls, text: str) -> bool:
        """Recognize advice requests that should answer, never plan or act."""
        normalized = " ".join(cls._visible_user_request(text).lower().split())
        if not normalized or any(marker in normalized for marker in cls._DIRECT_SCREEN_QUESTION_MARKERS):
            return False

        # Action requests remain on the existing approval and verification path.
        if any(_re.search(rf"\b{_re.escape(marker)}\b", normalized) for marker in cls._ACTION_REQUEST_MARKERS):
            return normalized.startswith(("how do i ", "how can i ", "what should i do"))

        guidance_starts = (
            "why ",
            "what should i do",
            "what do i do next",
            "what next",
            "how do i ",
            "how can i ",
            "can you explain",
            "could you explain",
            "please explain",
            "help me",
            "please help",
        )
        return normalized.startswith(guidance_starts)

    @classmethod
    def _is_content_generation_request(cls, text: str) -> bool:
        """Recognize requests to draft content rather than control an app.

        Mentioning an app as background (for example, "I'm working in Google
        Docs") does not mean the user has asked Adele to type into it.  Keep
        those requests on the no-tools ChatGPT path unless the user explicitly
        asks to insert the content into a desktop surface.
        """
        normalized = " ".join(cls._visible_user_request(text).lower().split())
        if not normalized or any(marker in normalized for marker in cls._DIRECT_SCREEN_QUESTION_MARKERS):
            return False
        if any(_re.search(pattern, normalized) for pattern in cls._DESKTOP_INSERTION_PATTERNS):
            return False

        noun_pattern = "|".join(_re.escape(noun) for noun in cls._CONTENT_REQUEST_NOUNS)
        drafting_pattern = (
            r"\b(?:help(?: me)?|can you|could you|please|would you)\s+"
            r"(?:to\s+)?(?:write|draft|brainstorm|create|generate|come up with)\b"
        )
        direct_pattern = (
            r"^\s*(?:write|draft|brainstorm|create|generate|summarize)\s+"
            r"(?:me\s+)?(?:a|an|the)?\s*(?:" + noun_pattern + r")\b"
        )
        return bool(_re.search(drafting_pattern, normalized) or _re.search(direct_pattern, normalized))

    def _is_conversational(self, text: str) -> str | None:
        """
        Classify if text is small-talk that can skip the full pipeline.
        Returns the category string or None if it's a real task.
        """
        text = self._visible_user_request(text)
        if self._GREETING_PATTERNS.match(text):
            return "greeting"
        if self._THANKS_PATTERNS.match(text):
            return "thanks"
        if self._FAREWELL_PATTERNS.match(text):
            return "farewell"
        if self._MOOD_PATTERNS.match(text):
            return "mood"
        if self._SIMPLE_FACTUAL.match(text):
            return "factual"
        if self._is_content_generation_request(text):
            return "creative_content"
        if self._is_contextual_guidance_question(text):
            return "contextual_guidance"
        return None

    async def _try_conversational_fast_path(
        self,
        user_text: str,
        context: perception.ContextSnapshot,
        ws_callback: Optional[WSCallback] = None,
    ) -> tuple | None:
        """
        Handle greetings, thanks, farewells, and simple questions
        without going through the full routing/planning pipeline.
        Returns (response_text, False) or None if not conversational.
        """
        visible_request = self._visible_user_request(user_text)
        category = self._is_conversational(visible_request)
        if not category:
            return None

        print(f"[AgentV2] 💬 Conversational fast path: {category}")

        # Get user's name for personalization
        user_name = self.user_profile.get_fact("name") or ""

        async def return_template_response() -> tuple:
            reply, _ = self._template_chat_response(category, user_name)
            if ws_callback:
                try:
                    await tool_registry.execute("send_response", {"message": reply})
                except Exception:
                    pass
                await ws_callback({
                    "type": "response",
                    "payload": {
                        "text": reply,
                        "display": "pill" if len(reply) <= 60 else "card",
                        "app": context.active_app.lower() if context.active_app else "",
                    },
                })
            return (reply, False)

        # These replies do not need desktop context or a model turn. Keeping
        # them local makes the first interaction immediate while Codex is cold
        # without pretending to answer factual questions.
        if category in {"greeting", "thanks", "farewell", "mood"}:
            return await return_template_response()

        # Use fast tier for speed
        await self.router.initialize()
        provider = self.router.fast
        if not provider:
            # Fallback to template responses
            return await return_template_response()

        # Build a lightweight conversational prompt
        history = self.conversation.get_history()[-6:]
        history_text = ""
        for turn in history:
            role = turn.get("role", "")
            parts = turn.get("parts", [])
            text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict))
            if text:
                clean_text = self._visible_user_request(text) if role == "user" else text
                history_text += f"{'User' if role == 'user' else 'ADELE'}: {clean_text}\n"

        profile_hint = ""
        if user_name:
            profile_hint = f"The user's name is {user_name}. Use it naturally (not every time).\n"

        context_hint = (
            f"Current desktop context: active app is '{context.active_app or 'Unknown'}'; "
            f"window title is '{context.window_title or 'Unknown'}'."
        )
        if context.page_title:
            context_hint += f" Page title: '{context.page_title}'."
        if context.visible_text:
            context_hint += f" Visible page text: {context.visible_text[:800]}"

        response_length = (
            "For a writing or brainstorming request, provide a useful concise draft "
            "of up to 250 words."
            if category == "creative_content"
            else "Keep responses short (1-2 sentences max), natural, and warm."
        )
        system = (
            "You are ADELE, a friendly cross-platform desktop assistant. "
            f"{response_length} "
            "Sound like a helpful friend, not a corporate bot. "
            "You're voice-first — write responses that sound natural when spoken aloud. "
            f"{profile_hint}"
        )

        system += (
            " Answer guidance questions directly. Do not claim to see screen details "
            "that are not present in the supplied desktop context, and do not perform "
            "or promise any desktop action in this no-tools response."
        )

        prompt = (
            f"{context_hint}\n\nConversation so far:\n{history_text}"
            f"\nUser: {visible_request}\n\nRespond naturally:"
        )

        try:
            response = await provider.generate(
                messages=[{"role": "user", "parts": [{"text": prompt}]}],
                system_prompt=system,
                tools=[],
                temperature=0.7,
                thinking_level="LOW",
                enable_builtin_tools=False,
            )
            reply = (response.text or "").strip() if response else ""
            if not reply:
                return await return_template_response()
        except Exception as e:
            print(f"[AgentV2] Fast path LLM error: {e}")
            return await return_template_response()

        # Deliver the response
        if ws_callback:
            display = "pill" if len(reply) <= 60 else "card"
            try:
                await tool_registry.execute("send_response", {"message": reply})
            except Exception:
                pass
            await ws_callback({
                "type": "response",
                "payload": {
                    "text": reply,
                    "display": display,
                    "app": context.active_app.lower() if context.active_app else "",
                },
            })

        self.conversation.add_model(reply)
        return (reply, False)

    def _template_chat_response(self, category: str, user_name: str = "") -> tuple:
        """Fallback template responses when no LLM is available."""
        name_suffix = f", {user_name}" if user_name else ""
        templates = {
            "greeting": [f"Hey{name_suffix}! What can I help with?", f"Hi{name_suffix}! Ready when you are.", "Hey! What's on your mind?"],
            "thanks": ["Happy to help!", "Anytime!", "You got it!"],
            "farewell": [f"See you{name_suffix}!", "Take care!", "Catch you later!"],
            "mood": ["I'm doing great, thanks for asking! What can I help with?", "All good here! What's up?"],
            "factual": ["Let me check that for you…"],
            "creative_content": [
                "I can help draft that. Tell me the tone or length you want, and I’ll write it with you."
            ],
        }
        templates["contextual_guidance"] = [
            "I can help with that. Tell me what you want to accomplish, or ask me to look at your screen."
        ]
        choices = templates.get(category, ["What can I help you with?"])
        reply = _random.choice(choices)
        self.conversation.add_model(reply)
        return (reply, False)

    def _suggest_followup(self, response: str, user_text: str) -> str:
        """Return a brief proactive follow-up, or empty string to skip."""
        suggestions = [
            "Anything else I can help with?",
            "Want me to do anything else with this?",
            "Need anything else?",
            "Let me know if you'd like to tweak anything.",
            "Want me to continue with something related?",
        ]
        # Don't suggest if the response already asks a question
        if response.rstrip().endswith("?"):
            return ""
        return _random.choice(suggestions)

    def _recent_conversation_snippet(self) -> str:
        recent_turns = self.conversation.get_history()[-6:]
        return " ".join(
            p.get("text", "") for t in recent_turns
            for p in (t.get("parts") or []) if isinstance(p, dict) and "text" in p
        )

    def _current_tool_gateway_context(self) -> dict:
        """Collect live browser bridge state for gateway routing."""
        try:
            from browser.bridge import browser_bridge
            from browser.store import browser_store
        except Exception:
            return {
                "browser_bridge_connected": False,
                "browser_has_snapshot": False,
                "browser_session_id": "",
            }

        snapshot = browser_store.get_snapshot()
        session_id = (
            str(browser_bridge.connected_session_id() or "").strip()
            or str(getattr(snapshot, "session_id", "") or "").strip()
        )
        return {
            "browser_bridge_connected": bool(browser_bridge.is_connected()),
            "browser_has_snapshot": snapshot is not None,
            "browser_session_id": session_id,
        }

    def _select_tool_surface(
        self,
        user_request: str,
        context: perception.ContextSnapshot,
        world_state: Optional[WorldState] = None,
    ) -> tuple[list[str], list[dict]]:
        intent = getattr(world_state, "intent", None) if world_state else None
        if intent is None or intent.action == IntentAction.UNKNOWN:
            try:
                intent = self.intent_parser.parse(user_request)
            except Exception:
                intent = None
        selected_tools = self.tool_selector.select(
            user_request=user_request,
            context_app=context.active_app or "",
            context_url=context.browser_url or "",
            conversation_history=self._recent_conversation_snippet(),
            clipboard_content=context.clipboard or "",
            selected_text=getattr(context, "selected_text", None) or "",
            intent_action=intent.action.value if intent else "",
            intent_target_type=intent.target_type.value if intent else "",
            intent_target_value=intent.target_value if intent else "",
        )
        llm_tool_declarations = self.tool_selector.get_llm_tool_declarations(selected_tools)
        return selected_tools, llm_tool_declarations

    def _llm_tool_names(self, llm_tool_declarations: Optional[list[dict]]) -> set[str]:
        return {
            str(decl.get("name", "")).strip()
            for decl in (llm_tool_declarations or [])
            if str(decl.get("name", "")).strip()
        }

    def _unsupported_plan_hints(
        self,
        plan: MilestonePlan,
        llm_tool_declarations: Optional[list[dict]],
    ) -> list[tuple[int, str, list[str]]]:
        allowed = self._llm_tool_names(llm_tool_declarations)
        issues: list[tuple[int, str, list[str]]] = []
        for milestone in plan.milestones:
            hinted = sorted({
                str(tool).strip()
                for tool in (milestone.hint_tools or [])
                if str(tool).strip() and str(tool).strip() not in {"send_response", "await_reply"}
            })
            missing = [tool for tool in hinted if tool not in allowed]
            if missing:
                issues.append((milestone.id, milestone.goal, missing))
        return issues

    def _enforce_plan_tool_contract(
        self,
        plan: MilestonePlan,
        llm_tool_declarations: Optional[list[dict]],
    ) -> MilestonePlan:
        issues = self._unsupported_plan_hints(plan, llm_tool_declarations)
        if not issues:
            return plan

        fragments = []
        for milestone_id, goal, missing in issues[:3]:
            label = goal or f"Milestone {milestone_id}"
            fragments.append(f"{label} requires {', '.join(missing)}")
        clarification = (
            "I can’t execute the current plan with the tools available for this request. "
            f"{'; '.join(fragments)}. Please provide the missing source or rephrase the task."
        )
        return MilestonePlan(
            task_summary=plan.task_summary,
            needs_clarification=True,
            clarification_prompt=clarification,
            final_response=plan.final_response,
            skill_context=getattr(plan, "skill_context", ""),
            skills_used=list(getattr(plan, "skills_used", [])),
            source=f"{getattr(plan, 'source', 'milestone_planner')}_tool_contract",
        )

    def _is_pending_plan_stale(self, pending: PendingPlanState, context: perception.ContextSnapshot) -> tuple[bool, str]:
        age = _time.time() - pending.created_at
        if age > PENDING_PLAN_TTL_SECONDS:
            return True, f"older than {PENDING_PLAN_TTL_SECONDS}s"

        current_fp = self._context_fingerprint(context)
        old_app = pending.context_fingerprint.get("active_app", "")
        new_app = current_fp.get("active_app", "")
        plan_tools = self._planned_tool_names(pending.plan)
        is_web_flow_plan = bool(plan_tools.intersection(WEB_FLOW_TOOLS))
        if old_app and new_app and old_app != new_app:
            # Approval can be spoken/typed via ADELE's Electron panel while the
            # original browser task context is still valid. Don't invalidate for that.
            if is_web_flow_plan and old_app in BROWSER_APP_NAMES and new_app in {"electron", "adele"}:
                pass
            elif is_web_flow_plan and old_app in BROWSER_APP_NAMES and new_app in BROWSER_APP_NAMES:
                pass
            else:
                return True, "active app changed"

        old_domain = pending.context_fingerprint.get("browser_domain", "")
        new_domain = current_fp.get("browser_domain", "")
        if old_domain and new_domain and old_domain != new_domain:
            return True, "browser domain changed"

        return False, ""

    def _planned_tool_names(self, plan: MilestonePlan) -> set[str]:
        planned_tools: set[str] = set()
        for milestone in plan.milestones:
            planned_tools.update(
                str(tool).strip()
                for tool in milestone.hint_tools
                if str(tool).strip()
            )
        return planned_tools

    def _plan_unit_count(self, plan: MilestonePlan) -> int:
        return len(plan.milestones)

    @staticmethod
    def _plan_requires_provider(plan: MilestonePlan) -> bool:
        """Return whether a plan needs GPT after deterministic planning.

        Direct actions retain Adele's normal tool validation, approval, and
        verification path. They do not need to start Codex just to select a
        tool whose arguments are already bounded by the deterministic planner.
        A web lookup is the exception because its source material is summarized
        by the active ChatGPT provider after the gateway succeeds.
        """
        return any(
            not str(getattr(milestone, "direct_tool", "") or "").strip()
            or str(getattr(milestone, "direct_tool", "") or "").strip()
            == "get_web_information"
            for milestone in plan.milestones
        )

    def _should_gate_plan(self, plan: MilestonePlan) -> bool:
        communication_tools = {"send_response", "await_reply"}
        read_only_tools = {
            "read_file",
            "read_screen",
            "get_ui_tree",
            "browser_snapshot",
            "browser_read_page",
            "browser_find",
            "browser_describe_ref",
            "browser_list_tabs",
            "gdocs_read",
            "gsheets_read",
            "gdrive_search",
            "gmail_read",
            "gcal_list_events",
            "gworkspace_analyze",
            "list_directory",
            "get_web_information",
            "fetch_web_content",
            "web_scrape",
            "web_search",
            "read_page_content",
            "extract_structured_data",
            "get_page_summary",
        }
        high_risk_tools = {
            "write_file",
            "replace_in_file",
            "run_shell",
            "browser_click_ref",
            "browser_type_ref",
            "browser_select_ref",
            "browser_click_match",
            "browser_click",
            "browser_fill",
            "click_ui",
            "type_in_field",
            "click_element",
            "type_text",
            "press_key",
            "mouse_action",
            "gdocs_create",
            "gdocs_append",
            "gdocs_insert_image",
            "gsheets_create",
            "gsheets_write",
            "gsheets_append_rows",
            "gsheets_formula",
            "gslides_create",
            "gslides_add_slide",
            "gdrive_upload",
            "gmail_send",
            "gmail_draft",
            "gcal_create_event",
        }
        medium_risk_tools = {
            "open_url",
            "open_app",
            "quit_app",
            "close_window",
            "window_manager",
            "save_image",
            "clipboard_ops",
        }
        side_effect_tools = high_risk_tools | medium_risk_tools

        planned_tools = self._planned_tool_names(plan)
        if not planned_tools:
            return False

        if all(tool in read_only_tools for tool in planned_tools):
            return False

        if self._plan_unit_count(plan) == 1 and planned_tools.issubset(medium_risk_tools):
            return False

        if any(tool in high_risk_tools for tool in planned_tools):
            return True

        has_side_effect = any(tool in side_effect_tools for tool in planned_tools)
        if self._plan_unit_count(plan) >= 3 and has_side_effect:
            return True
        return False

    def _modal_steps_from_plan(self, plan: MilestonePlan) -> list[dict]:
        """Build compressed plan phases for the UI modal.
        
        Groups related steps into logical phases so the user sees a clean
        high-level summary.  The agent treats the full plan as a reference —
        actual execution adapts based on what it observes.
        """
        return [
            {
                "label": milestone.goal or f"Milestone {milestone.id}",
                "detail": milestone.success_signal or ", ".join(milestone.hint_tools) or "Complete this goal",
            }
            for milestone in plan.milestones
        ]

    async def _show_plan_gate(
        self,
        pending: PendingPlanState,
        context: perception.ContextSnapshot,
        provider: Optional[LLMProvider],
        ws_callback: Optional[WSCallback],
        note: str = "",
    ) -> tuple[str, bool]:
        steps_payload = self._modal_steps_from_plan(pending.plan)
        message = "Review this plan and choose Proceed to execute it."
        if note:
            message = f"{note}\n\n{message}"

        await_payload = {
            "message": message,
            "modal": "plan",
            "steps": steps_payload,
            "plan_id": pending.plan_id,
        }
        raw = await tool_registry.execute("await_reply", await_payload)

        await_msg = message
        await_modal_data = None
        if isinstance(raw, str) and raw.startswith("AWAIT:"):
            parsed = raw[len("AWAIT:"):]
            try:
                await_modal_data = json.loads(parsed)
                await_msg = await_modal_data.get("message", await_msg)
            except (json.JSONDecodeError, TypeError):
                await_msg = parsed or await_msg

        self._pending_reply_provider = provider
        self.conversation.add_model(await_msg)

        if ws_callback:
            payload = {
                "type": "response",
                "payload": {
                    "text": await_msg,
                    "display": "card",
                    "await_input": True,
                    "app": context.active_app.lower() if context.active_app else "",
                },
            }
            if await_modal_data:
                payload["payload"]["modal_data"] = await_modal_data
            await ws_callback(payload)

        return (await_msg, True)

    async def _run_impl(
        self,
        user_text: str,
        context: perception.ContextSnapshot,
        ws_callback: Optional[WSCallback] = None,
    ) -> tuple:
        """
        Main entry point for V2 agent.
        
        Args:
            user_text: User's request text
            context: Current desktop context from perception layer
            ws_callback: WebSocket callback for streaming updates
            
        Returns:
            Tuple of (response_text, awaiting_reply)
        """
        t_start = _time.time()
        trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        visible_user_text = self._visible_user_request(user_text)
        vault_context = self._vault_retrieval_context(user_text)
        print(f"\n[AgentV2] ═══ New Request ═══")
        print("[AgentV2] Request context captured.")

        # Record user turn in conversation memory (for multi-turn context)
        self.conversation.add_user(visible_user_text)

        # Extract facts from user message into persistent profile
        extracted = self.user_profile.extract_facts(visible_user_text)
        if extracted:
            print(f"[AgentV2] 📝 Extracted facts: {extracted}")

        # ══════════════════════════════════════════════════════════════
        # FAST PATH: Small-talk / conversational (skip full pipeline)
        # ══════════════════════════════════════════════════════════════
        if not self._pending_plan and not self._pending_execution:
            chat_result = await self._try_conversational_fast_path(visible_user_text, context, ws_callback)
            if chat_result is not None:
                journal_request_trace(
                    trace_id=trace_id,
                    phase="completed",
                    intent="conversation",
                    route="fast_path",
                    status="passed",
                )
                elapsed = _time.time() - t_start
                print(f"[AgentV2] ⚡ Fast path: {elapsed:.2f}s")
                return chat_result

        # Stream "thinking" state to UI
        if ws_callback:
            await ws_callback({"type": "thinking"})

        # ══════════════════════════════════════════════════════════════
        # PHASE 1: SENSE — Build structured WorldState
        # ══════════════════════════════════════════════════════════════
        world_state = await self._build_world_state(visible_user_text, context)
        self.log_screen_event(context, visible_user_text)
        gateway_context = self._current_tool_gateway_context()
        set_tool_gateway_context(
            active_app=world_state.active_app,
            browser_url=world_state.browser_url or "",
            background_mode=False,
            browser_bridge_connected=gateway_context["browser_bridge_connected"],
            browser_has_snapshot=gateway_context["browser_has_snapshot"],
            browser_session_id=gateway_context["browser_session_id"],
        )
        # Wire live progress updates from web gateway → Electron overlay
        set_web_progress_callback(ws_callback)
        set_automation_cursor_callback(ws_callback)
        print(f"[AgentV2] Intent: {world_state.intent.action.value if world_state.intent else 'unknown'}")

        planning_request = visible_user_text

        if self._pending_execution:
            pending_execution = self._pending_execution
            age = _time.time() - pending_execution.created_at
            if age > PENDING_PLAN_TTL_SECONDS:
                print(f"[AgentV2] Pending execution expired after {age:.1f}s; discarding state.")
                self._pending_execution = None
            else:
                followup = self._classify_pending_followup(visible_user_text)
                print(f"[AgentV2] Pending execution follow-up: {followup} ({pending_execution.execution_id})")

                if followup == "cancel":
                    self._pending_execution = None
                    cancel_message = "Cancelled the in-progress task."
                    try:
                        await tool_registry.execute("send_response", {"message": cancel_message})
                    except Exception:
                        pass
                    if ws_callback:
                        await ws_callback({
                            "type": "response",
                            "payload": {
                                "text": cancel_message,
                                "display": "card",
                                "app": context.active_app.lower() if context.active_app else "",
                            }
                        })
                    self.conversation.add_model(cancel_message)
                    return (cancel_message, False)

                provider = pending_execution.provider
                if provider is None:
                    try:
                        decision = await self.router.route(
                            pending_execution.original_user_request,
                            context_summary=f"App: {context.active_app}, Window: {context.window_title}",
                            has_screenshot=context.screenshot_path is not None,
                        )
                        provider = decision.provider
                    except RuntimeError as e:
                        error_msg = str(e)
                        if ws_callback:
                            await ws_callback({
                                "type": "response",
                                "payload": {"text": error_msg}
                            })
                        return (error_msg, False)

                resume_inputs = list(pending_execution.followup_inputs or [])
                if visible_user_text:
                    resume_inputs.append(visible_user_text)
                resume_request = pending_execution.original_user_request
                if resume_inputs:
                    resume_request = (
                        f"{pending_execution.original_user_request}\n\n"
                        "User follow-up:\n"
                        + "\n".join(resume_inputs)
                    )

                # Preserve the original intent from the pending execution so the
                # tool selector doesn't re-classify the follow-up text as a
                # different intent (e.g. 'analyze' instead of 'communicate').
                if pending_execution.plan and pending_execution.plan.milestones:
                    original_intent = self.intent_parser.parse(
                        pending_execution.original_user_request
                    )
                    if original_intent and original_intent.action != IntentAction.UNKNOWN:
                        world_state.intent = original_intent

                selected_tools, llm_tool_declarations = self._select_tool_surface(
                    resume_request,
                    context,
                    world_state,
                )
                pending_execution.plan = self._enforce_plan_tool_contract(
                    pending_execution.plan,
                    llm_tool_declarations,
                )
                if pending_execution.plan.needs_clarification:
                    self._pending_execution = None
                    result = await self._handle_clarification(
                        pending_execution.plan.clarification_prompt,
                        provider,
                        context,
                        ws_callback,
                    )
                    return result

                pending_execution.provider = provider
                pending_execution.selected_tools = list(selected_tools)
                pending_execution.followup_inputs = resume_inputs
                self._pending_execution = None

                final_response, awaiting = await self._execute_milestone_plan(
                    plan=pending_execution.plan,
                    world_state=world_state,
                    provider=provider,
                    context=context,
                    user_text=resume_request,
                    llm_tool_declarations=llm_tool_declarations,
                    ws_callback=ws_callback,
                    pending_execution=pending_execution,
                    followup_inputs=resume_inputs,
                )
                print(f"[AgentV2] ⏱ TOTAL: {_time.time() - t_start:.2f}s")
                return (final_response, awaiting)

        # Pending-plan follow-up handling (approve/cancel/modify)
        if self._pending_plan:
            pending = self._pending_plan
            followup = self._classify_pending_followup(visible_user_text)
            print(f"[AgentV2] Pending plan follow-up: {followup} ({pending.plan_id})")

            if followup == "cancel":
                self._pending_plan = None
                cancel_message = "Plan cancelled."
                try:
                    await tool_registry.execute("send_response", {"message": cancel_message})
                except Exception:
                    pass
                if ws_callback:
                    await ws_callback({
                        "type": "response",
                        "payload": {
                            "text": cancel_message,
                            "display": "card",
                            "app": context.active_app.lower() if context.active_app else "",
                        }
                    })
                self.conversation.add_model(cancel_message)
                return (cancel_message, False)

            if followup == "approve":
                stale, stale_reason = self._is_pending_plan_stale(pending, context)
                if stale and pending.stale_replan_count < 1 and self.use_planning:
                    print(f"[AgentV2] Pending plan stale ({stale_reason}); regenerating once.")
                    self._pending_plan = None

                    provider = pending.provider
                    if provider is None:
                        decision = await self.router.route(
                            pending.original_user_request,
                            context_summary=f"App: {context.active_app}, Window: {context.window_title}",
                            has_screenshot=context.screenshot_path is not None,
                        )
                        provider = decision.provider

                    if self.planner is None:
                        self.planner = TaskPlanner(provider=provider, tool_registry=tool_registry)
                    else:
                        self.planner.provider = provider

                    selected_tools, llm_tool_declarations = self._select_tool_surface(
                        pending.original_user_request,
                        context,
                        world_state,
                    )
                    if ws_callback:
                        await ws_callback({"type": "doing", "text": "Refreshing plan due to context change...", "tool": "planner"})

                    refreshed_plan = await self.planner.create_milestone_plan(
                        user_request=pending.original_user_request,
                        world_state=world_state,
                        conversation_history=self.conversation.get_history(),
                        available_tools=selected_tools,
                    )
                    if refreshed_plan is None:
                        refreshed_plan = MilestonePlan(
                            task_summary=pending.original_user_request,
                            needs_clarification=True,
                            clarification_prompt="I couldn't refresh the plan. Please try again.",
                        )
                    refreshed_plan = self._enforce_plan_tool_contract(refreshed_plan, llm_tool_declarations)
                    if refreshed_plan.needs_clarification:
                        result = await self._handle_clarification(
                            refreshed_plan.clarification_prompt,
                            provider,
                            context,
                            ws_callback,
                        )
                        return result

                    refreshed_pending = PendingPlanState(
                        plan_id=uuid.uuid4().hex[:10],
                        plan=refreshed_plan,
                        created_at=_time.time(),
                        context_fingerprint=self._context_fingerprint(context),
                        provider=provider,
                        original_user_request=pending.original_user_request,
                        selected_tools=list(selected_tools),
                        stale_replan_count=pending.stale_replan_count + 1,
                    )
                    self._pending_plan = refreshed_pending
                    result = await self._show_plan_gate(
                        pending=refreshed_pending,
                        context=context,
                        provider=provider,
                        ws_callback=ws_callback,
                        note="Context changed since the original plan, so I refreshed it.",
                    )
                    return result

                if stale:
                    print(f"[AgentV2] Pending plan stale ({stale_reason}) but refresh already used; executing frozen plan.")

                provider = pending.provider
                if provider is None and self._plan_requires_provider(pending.plan):
                    try:
                        decision = await self.router.route(
                            pending.original_user_request,
                            context_summary=f"App: {context.active_app}, Window: {context.window_title}",
                            has_screenshot=context.screenshot_path is not None,
                        )
                        provider = decision.provider
                    except RuntimeError as e:
                        error_msg = str(e)
                        if ws_callback:
                            await ws_callback({
                                "type": "response",
                                "payload": {"text": error_msg}
                            })
                        return (error_msg, False)

                self._pending_plan = None
                print(f"[AgentV2] Executing frozen approved plan: {pending.plan.task_summary}")
                llm_tool_declarations = self.tool_selector.get_llm_tool_declarations(pending.selected_tools)
                final_response, awaiting = await self._execute_milestone_plan(
                    plan=pending.plan,
                    world_state=world_state,
                    provider=provider,
                    context=context,
                    user_text=pending.original_user_request,
                    llm_tool_declarations=llm_tool_declarations,
                    ws_callback=ws_callback,
                )
                print(f"[AgentV2] ⏱ TOTAL: {_time.time() - t_start:.2f}s")
                return (final_response, awaiting)

            # Modification path: clear frozen plan and replan with explicit plan context.
            previous_plan = pending.plan.to_prompt_string()
            previous_request = pending.original_user_request
            self._pending_plan = None
            planning_request = (
                f"{visible_user_text}\n\n"
                "Previous proposed plan (modify this):\n"
                f"{previous_plan}\n\n"
                "Original request:\n"
                f"{previous_request}"
            )
            print("[AgentV2] Replanning from user modifications to pending plan.")

        # ══════════════════════════════════════════════════════════════
        # ROUTING — Select model tier
        # ══════════════════════════════════════════════════════════════
        # Fast local path: identify deterministic one-step actions before
        # starting the Codex App Server. This retains the same tool registry,
        # approval gate, and verifier used by the normal execution path.
        if self._pending_reply_provider is None:
            if self.planner is None:
                self.planner = TaskPlanner(provider=None, tool_registry=tool_registry)

            world_state.task_graph = self.planner.intent_parser.extract_task_graph(
                planning_request,
                world_state,
            )
            selected_tools, llm_tool_declarations = self._select_tool_surface(
                planning_request,
                context,
                world_state,
            )
            direct_plan = self.planner.build_direct_action_plan(
                user_request=planning_request,
                world_state=world_state,
                available_tools=selected_tools,
            )

            if direct_plan is not None and not self._plan_requires_provider(direct_plan):
                intent = world_state.intent
                selected_route = "direct_local"
                journal_request_trace(
                    trace_id=trace_id,
                    phase="routing",
                    intent=intent.action.value if intent else "unknown",
                    target_type=intent.target_type.value if intent else "unknown",
                    route=selected_route,
                    tool_names=selected_tools,
                    status="selected",
                )
                milestone_plan = self._enforce_plan_tool_contract(
                    direct_plan,
                    llm_tool_declarations,
                )
                print(f"[AgentV2] Direct local path: {milestone_plan.task_summary}")

                if self._should_gate_plan(milestone_plan):
                    pending = PendingPlanState(
                        plan_id=uuid.uuid4().hex[:10],
                        plan=milestone_plan,
                        created_at=_time.time(),
                        context_fingerprint=self._context_fingerprint(context),
                        provider=None,
                        original_user_request=planning_request,
                        selected_tools=list(selected_tools),
                    )
                    self._pending_plan = pending
                    journal_pending_approval(
                        plan_id=pending.plan_id,
                        plan_dict=pending.plan.to_dict(),
                        original_user_request=pending.original_user_request,
                    )
                    return await self._show_plan_gate(
                        pending=pending,
                        context=context,
                        provider=None,
                        ws_callback=ws_callback,
                    )

                if ws_callback:
                    first_goal = milestone_plan.milestones[0].goal if milestone_plan.milestones else "Working"
                    await ws_callback({"type": "doing", "text": first_goal, "tool": "executor"})

                final_response, awaiting = await self._execute_milestone_plan(
                    plan=milestone_plan,
                    world_state=world_state,
                    provider=None,
                    context=context,
                    user_text=planning_request,
                    llm_tool_declarations=llm_tool_declarations,
                    ws_callback=ws_callback,
                    thinking_level="LOW",
                    show_milestone_progress=False,
                    trace_id=trace_id,
                )
                journal_request_trace(
                    trace_id=trace_id,
                    phase="completed",
                    intent=intent.action.value if intent else "unknown",
                    target_type=intent.target_type.value if intent else "unknown",
                    route=selected_route,
                    tool_names=selected_tools,
                    status="awaiting_input" if awaiting else "completed",
                )
                print(f"[AgentV2] Direct local total: {_time.time() - t_start:.2f}s")
                return (final_response, awaiting)

        provider: Optional[LLMProvider] = None
        if self._pending_reply_provider:
            provider = self._pending_reply_provider
            self._pending_reply_provider = None
            print(f"[AgentV2] Resuming with {provider.name}")
        else:
            # ── Instant acknowledgment ──
            if ws_callback:
                ack = self._pick_ack(visible_user_text)
                await ws_callback({"type": "ack", "text": ack})

            # Immediate feedback while routing LLM runs
            if ws_callback:
                await ws_callback({"type": "doing", "text": "Analyzing…", "tool": "router"})
            try:
                decision = await self.router.route(
                    planning_request,
                    context_summary=f"App: {context.active_app}, Window: {context.window_title}",
                    has_screenshot=context.screenshot_path is not None,
                )
                provider = decision.provider
                print(f"[AgentV2] Using {provider.name} ({decision.reason})")
            except RuntimeError as e:
                error_msg = str(e)
                journal_request_trace(
                    trace_id=trace_id,
                    phase="routing",
                    route="provider",
                    status="failed",
                    error_code=_trace_error_code(error_msg),
                )
                if ws_callback:
                    await ws_callback({
                        "type": "response",
                        "payload": {"text": error_msg}
                    })
                return (error_msg, False)

        # Initialize planner with provider
        if self.planner is None:
            self.planner = TaskPlanner(provider=provider, tool_registry=tool_registry)
        else:
            self.planner.provider = provider

        world_state.task_graph = self.planner.intent_parser.extract_task_graph(
            planning_request,
            world_state,
        )

        # ══════════════════════════════════════════════════════════════
        # PHASE 2: PLAN — Generate execution plan (parallelised)
        # ══════════════════════════════════════════════════════════════
        # Tool selection is CPU-only (deterministic, ~0ms).  We run it
        # first so its result feeds into the LLM planning call.
        selected_tools, llm_tool_declarations = self._select_tool_surface(
            planning_request,
            context,
            world_state,
        )
        intent = world_state.intent
        selected_route = "web_research" if "get_web_information" in selected_tools else "agent_planning"
        journal_request_trace(
            trace_id=trace_id,
            phase="routing",
            intent=intent.action.value if intent else "unknown",
            target_type=intent.target_type.value if intent else "unknown",
            route=selected_route,
            tool_names=selected_tools,
            status="selected",
        )

        direct_plan = self.planner.build_direct_action_plan(
            user_request=planning_request,
            world_state=world_state,
            available_tools=selected_tools,
        )
        needs_high_effort = self.planner.should_use_milestones(
            planning_request,
            task_graph=world_state.task_graph,
        )

        if direct_plan is not None:
            milestone_plan = direct_plan
            needs_high_effort = False
            print(f"[AgentV2] Direct action path: {milestone_plan.task_summary}")
        else:
            # Stream progress immediately — don't wait for the LLM.
            # Small, single-step requests use LOW effort; complex requests use HIGH.
            if ws_callback:
                status_text = "Planning…" if needs_high_effort else "Working…"
                await ws_callback({"type": "doing", "text": status_text, "tool": "planner"})

            milestone_plan = await self.planner.create_milestone_plan(
                user_request=planning_request,
                world_state=world_state,
                conversation_history=self.conversation.get_history(),
                available_tools=selected_tools,
                supplemental_context=vault_context,
                thinking_level="HIGH" if needs_high_effort else "LOW",
            )
        if milestone_plan is None:
            failure_code = getattr(self.planner, "last_failure", None) or "no_plan"
            journal_request_trace(
                trace_id=trace_id,
                phase="planning",
                intent=intent.action.value if intent else "unknown",
                target_type=intent.target_type.value if intent else "unknown",
                route=selected_route,
                tool_names=selected_tools,
                status="failed",
                error_code=_trace_error_code(failure_code),
            )
            print(f"[AgentV2] Planning unavailable ({failure_code}); returning to idle.")
            fallback = self._planner_unavailable_message(world_state.intent)
            self.conversation.add_model(fallback)
            if ws_callback:
                await ws_callback({
                    "type": "response",
                    "payload": {
                        "text": fallback,
                        "display": "card",
                        "app": context.active_app.lower() if context.active_app else "",
                    },
                })
            print(f"[AgentV2] ⏱ TOTAL: {_time.time() - t_start:.2f}s")
            return (fallback, False)
        milestone_plan = self._enforce_plan_tool_contract(milestone_plan, llm_tool_declarations)

        print(f"[AgentV2] Milestone plan: {milestone_plan.task_summary} "
              f"({len(milestone_plan.milestones)} milestones)")

        # Handle clarification needed
        if milestone_plan.needs_clarification:
            result = await self._handle_clarification(
                milestone_plan.clarification_prompt,
                provider, 
                context, 
                ws_callback
            )
            return result

        if self._should_gate_plan(milestone_plan):
            pending = PendingPlanState(
                plan_id=uuid.uuid4().hex[:10],
                plan=milestone_plan,
                created_at=_time.time(),
                context_fingerprint=self._context_fingerprint(context),
                provider=provider,
                original_user_request=planning_request,
                selected_tools=list(selected_tools),
            )
            self._pending_plan = pending
            print(f"[AgentV2] Plan gated for approval: {pending.plan_id}")
            journal_pending_approval(
                plan_id=pending.plan_id,
                plan_dict=pending.plan.to_dict(),
                original_user_request=pending.original_user_request,
            )
            result = await self._show_plan_gate(
                pending=pending,
                context=context,
                provider=provider,
                ws_callback=ws_callback,
            )
            print(f"[AgentV2] ⏱ TOTAL: {_time.time() - t_start:.2f}s")
            return result

        # ══════════════════════════════════════════════════════════════
        # PHASE 3 & 4: ACT + VERIFY — Execute milestone plan
        # ══════════════════════════════════════════════════════════════
        if ws_callback:
            first_goal = milestone_plan.milestones[0].goal if milestone_plan.milestones else "Working"
            await ws_callback({"type": "doing", "text": first_goal, "tool": "executor"})

        final_response, awaiting = await self._execute_milestone_plan(
            plan=milestone_plan,
            world_state=world_state,
            provider=provider,
            context=context,
            user_text=planning_request,
            llm_tool_declarations=llm_tool_declarations,
            ws_callback=ws_callback,
            thinking_level="MEDIUM" if needs_high_effort else "LOW",
            show_milestone_progress=needs_high_effort,
            trace_id=trace_id,
        )

        print(f"[AgentV2] ⏱ TOTAL: {_time.time() - t_start:.2f}s")

        # ── Background memory curator: decide what to persist ──
        journal_request_trace(
            trace_id=trace_id,
            phase="completed",
            intent=intent.action.value if intent else "unknown",
            target_type=intent.target_type.value if intent else "unknown",
            route=selected_route,
            tool_names=selected_tools,
            status="awaiting_input" if awaiting else "completed",
        )
        asyncio.ensure_future(self._curate_vault(visible_user_text, final_response))

        return (final_response, awaiting)

    async def run(
        self,
        user_text: str,
        context: perception.ContextSnapshot,
        ws_callback: Optional[WSCallback] = None,
    ) -> tuple:
        """Run a request and always remove its temporary visual capture."""
        try:
            return await self._run_impl(user_text, context, ws_callback)
        finally:
            perception.delete_temporary_screenshot(context.screenshot_path)

    async def _curate_vault(self, user_text: str, agent_response: str) -> None:
        """Background curator: review the conversation and decide what to persist.

        Spawned as a fire-and-forget task after ``run()`` completes.
        Uses a lightweight Flash call to judge whether any facts, contacts,
        preferences, or research snippets from the exchange are worth storing
        permanently in the vault.
        """
        try:
            # Only curate if there's meaningful content
            if not user_text or len(user_text.strip()) < 10:
                return
            if not agent_response or len(agent_response.strip()) < 20:
                return

            # Build a compact context for the curator prompt
            recent_actions = self.working_memory.get_recent_actions(5)
            action_summary = "; ".join(
                f"{a.tool}→{str(a.result_summary or '')[:60]}"
                for a in recent_actions
            ) if recent_actions else "none"

            curator_prompt = (
                "You are a memory curator. Review this conversation exchange and decide "
                "if anything should be permanently stored in the user's vault memory.\n\n"
                f"User said: {user_text[:500]}\n"
                f"Agent response: {agent_response[:500]}\n"
                f"Recent actions: {action_summary[:300]}\n\n"
                "If there's something worth remembering (a contact detail, preference, "
                "research finding, important fact, file reference, etc.), respond with "
                "a JSON object: {\"store\": true, \"category\": \"...\", \"title\": \"...\", "
                "\"content\": \"...\", \"tags\": [\"...\"]}\n"
                "If nothing is worth storing, respond with: {\"store\": false}\n"
                "Be selective — only store genuinely useful long-term information."
            )

            # Use fast tier for speed (lightweight model)
            await self.router.initialize()
            provider = self.router.fast
            if not provider:
                return

            from providers.gemini import MEMORY_CURATOR_JSON_SCHEMA

            result = await provider.generate(
                messages=[{"role": "user", "parts": [{"text": curator_prompt}]}],
                system_prompt="You are a concise memory curator. Respond ONLY with valid JSON.",
                tools=[],
                temperature=0.1,
                thinking_level="LOW",
                response_json_schema=MEMORY_CURATOR_JSON_SCHEMA,
                enable_builtin_tools=False,
            )

            response_text = (result.text or "").strip() if result else ""
            if not response_text:
                return

            # Parse the curator's decision
            # Strip markdown code fences if present
            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            decision = json.loads(response_text)
            if not decision.get("store"):
                return

            # Store in vault
            category = decision.get("category", "notes")
            title = decision.get("title", "")
            content = decision.get("content", "")
            tags = decision.get("tags", [])

            if title and content:
                self.vault.store(
                    category=category,
                    title=title,
                    content=content,
                    tags=tags if isinstance(tags, list) else [],
                    source=f"auto-curated from conversation",
                )
                print(f"[AgentV2] 🧠 Curator stored: [{category}] {title[:60]}")

        except json.JSONDecodeError:
            pass  # Curator response wasn't valid JSON — skip silently
        except Exception as e:
            print(f"[AgentV2] ⚠ Curator error (non-fatal): {e}")

    def log_screen_event(self, context: perception.ContextSnapshot, user_text: str):
        """Legacy hook retained for callers; screen events are not persisted."""
        del context, user_text

    async def _build_world_state(
        self,
        user_text: str,
        context: perception.ContextSnapshot
    ) -> WorldState:
        """Build structured WorldState from context and user text."""
        
        # Extract entities from user text
        entities = self.entity_extractor.extract(user_text)
        
        # Parse intent
        intent = self.intent_parser.parse(user_text)
        
        # Build world state
        world_state = WorldState(
            # Desktop state
            active_app=context.active_app or "",
            window_title=context.window_title or "",
            browser_url=context.browser_url,
            
            # Extracted entities
            mentioned_apps=entities.get("apps", []),
            mentioned_files=entities.get("files", []),
            mentioned_urls=entities.get("urls", []),
            
            # Clipboard
            clipboard_content=context.clipboard,
            
            # Selected text
            selected_text=getattr(context, 'selected_text', None),
            
            # Screenshot
            has_screenshot=context.screenshot_path is not None,
            screenshot_path=context.screenshot_path,
            
            # Intent
            intent=intent,
            
            # Metadata
            timestamp=context.timestamp
        )
        
        return world_state

    async def _handle_clarification(
        self,
        prompt: str,
        provider: LLMProvider,
        context: perception.ContextSnapshot,
        ws_callback: Optional[WSCallback]
    ) -> tuple:
        """Handle a request that needs clarification."""
        print(f"[AgentV2] ⏳ Awaiting clarification: {prompt}")
        
        # Add to conversation memory
        self.conversation.add_model(prompt)
        
        # Lock provider for follow-up
        self._pending_reply_provider = provider
        
        if ws_callback:
            await ws_callback({
                "type": "response",
                "payload": {
                    "text": prompt,
                    "display": "card",
                    "await_input": True,
                    "app": context.active_app.lower() if context.active_app else ""
                }
            })
        
        return (prompt, True)

    @staticmethod
    def _planner_unavailable_message(intent: Optional[UserIntent]) -> str:
        """Keep planner faults out of the user-facing voice experience."""
        if intent is None or intent.action in {
            IntentAction.UNKNOWN,
            IntentAction.QUERY,
            IntentAction.ANALYZE,
        }:
            return (
                "I didn't catch a clear task. Try a short request such as "
                "“open Spotify” or “summarize this text.”"
            )
        return (
            "I couldn't complete that request from the current context. "
            "Try a short, specific command such as “open Spotify.”"
        )

    @staticmethod
    def _milestone_failure_message(
        failed: list[Milestone],
        completed: list[Milestone],
    ) -> str:
        """Describe an execution outcome without exposing planner-only goals.

        Milestone goals are internal instructions, not user-facing explanations.
        A cancellation means no cause was verified, so it must not be presented as
        a diagnosis. Other failures are intentionally kept generic unless a tool
        has supplied a separately validated response.
        """
        if any("cancelled by user" in (milestone.error or "").lower() for milestone in failed):
            return "That request was stopped before it finished, so I couldn't verify the result."
        if completed:
            return "I completed part of that request, but I couldn't verify the remaining result."
        return "I couldn't complete that request or verify a successful result."

    # ═══════════════════════════════════════════════════════════════
    #  Adaptive Plan Execution (LLM-in-the-loop)
    # ═══════════════════════════════════════════════════════════════

    async def _perceive_environment(self, followup_inputs: Optional[list[str]] = None) -> dict:
        """Quick perception of the current desktop/browser state for step reasoning."""
        env: dict = {}
        try:
            active_app, window_title, clipboard = await asyncio.gather(
                perception.get_active_app(),
                perception.get_window_title(),
                perception.get_clipboard(),
            )
            env["active_app"] = active_app
            env["window_title"] = window_title
            if clipboard:
                env["clipboard"] = clipboard[:500]
            if active_app.lower() in perception.BROWSERS:
                browser_url, selected_text = await asyncio.gather(
                    perception.get_browser_url(active_app),
                    perception.get_browser_selected_text(active_app),
                )
                env["browser_url"] = browser_url or ""
                if selected_text:
                    env["selected_text"] = selected_text[:500]
        except Exception as e:
            print(f"[AgentV2] ⚠ Perception failed: {e}")
        if followup_inputs:
            env["user_followups"] = " || ".join(text[:200] for text in followup_inputs if text)
        last_typed_text = self.working_memory.get_last_typed_text()
        if last_typed_text:
            env["last_typed_text"] = last_typed_text[:500]
        search_leads = self.working_memory.get_search_leads()
        if search_leads:
            env["search_lead_count"] = len(search_leads)
            top_leads = []
            for lead in search_leads[-3:]:
                title = str(lead.get("title", "")).strip()
                domain = str(lead.get("domain", "")).strip()
                status = "opened" if lead.get("opened") else "unopened"
                row = " | ".join(part for part in (title, domain, status) if part)
                if row:
                    top_leads.append(row[:180])
            if top_leads:
                env["search_leads"] = " || ".join(top_leads)
        return env

    # ═══════════════════════════════════════════════════════════════
    #  Milestone-Based Execution (LLM micro-loop per milestone)
    # ═══════════════════════════════════════════════════════════════

    async def _execute_milestone_plan(
        self,
        plan: MilestonePlan,
        world_state: WorldState,
        provider: LLMProvider,
        context: perception.ContextSnapshot,
        user_text: str,
        llm_tool_declarations: Optional[list[dict]],
        ws_callback: Optional[WSCallback],
        pending_execution: Optional[PendingExecutionState] = None,
        followup_inputs: Optional[list[str]] = None,
        thinking_level: str = "MEDIUM",
        show_milestone_progress: bool = True,
        trace_id: str = "",
    ) -> tuple:
        """Execute a milestone-based plan using the LLM micro-loop.

        Each milestone is executed autonomously — the LLM decides tool calls
        within the milestone's scope until the success_signal is met or
        the runtime safety cap is reached.

        Returns:
            Tuple of (final_response, awaiting_reply)
        """
        from agent.milestone_executor import get_milestone_executor

        t_start = _time.time()
        exec_label = (
            pending_execution.execution_id
            if pending_execution
            else uuid.uuid4().hex[:12]
        )
        executor = get_milestone_executor(provider, llm_tool_declarations or tool_registry.declarations())
        request_scope_tool_names = {
            str(decl.get("name", "")).strip()
            for decl in (llm_tool_declarations or tool_registry.declarations())
            if str(decl.get("name", "")).strip()
        }
        deliverables: dict[int, str] = dict(pending_execution.deliverables) if pending_execution else {}
        milestone_step_results: dict[int, str] = (
            dict(pending_execution.milestone_step_results) if pending_execution else {}
        )
        milestone_step_result_idx = pending_execution.milestone_step_result_idx if pending_execution else 0
        blocked_await_signatures = set(pending_execution.blocked_await_signatures or []) if pending_execution else set()
        followup_inputs = list(
            followup_inputs
            or (pending_execution.followup_inputs if pending_execution else [])
            or []
        )
        last_await_payload: Optional[dict] = dict(pending_execution.await_payload) if pending_execution else None
        self._last_opened_url = pending_execution.last_opened_url if pending_execution else ""

        print(f"\n[AgentV2] ═══ Milestone Plan: {plan.task_summary} ═══")
        print(f"[AgentV2]   Milestones: {len(plan.milestones)}")
        for m in plan.milestones:
            deps = f" (depends: {m.depends_on})" if m.depends_on else ""
            print(f"[AgentV2]   [{m.id}] {m.goal} — signal: {m.success_signal}{deps}")
        print(f"[AgentV2] ═══{'═' * 50}═══\n")

        # Reset Glance perception for this new task
        from agent.glance import get_glance as _get_glance
        _get_glance().reset()

        is_research = self._looks_like_research_doc_task(user_text, plan.task_summary or "")

        # Tracks whether a send_response was already forwarded to ws_callback
        # inside the milestone executor.  Suppresses the duplicate plain-text
        # fallback response that _execute_milestone_plan would otherwise send.
        response_emitted_to_ui = False

        # Track whether the last tool was UI-mutating (drives passive visual injection)
        last_tool_was_ui_mutating = False

        async def milestone_visual_context() -> str:
            """Gather DOM snapshot + screenshot description for passive injection."""
            parts: list[str] = []
            try:
                from browser.store import browser_store
                snap = browser_store.get_snapshot()
                if snap and snap.elements:
                    dom_lines = [f"Page: {snap.title} ({snap.url})"]
                    for el in snap.elements[:30]:
                        label = el.primary_label()[:60] if el.primary_label() else el.tag
                        dom_lines.append(f"  [{el.ref_id}] {el.role or el.tag}: {label}")
                    parts.append("\n".join(dom_lines))
            except Exception as e:
                print(f"[AgentV2] ⚠ DOM snapshot for visual context failed: {e}")

            return "\n".join(parts) if parts else ""

        async def milestone_env_perceiver() -> dict:
            env = await self._perceive_environment(followup_inputs=followup_inputs)
            # Passive visual injection: only after UI-mutating tools
            if last_tool_was_ui_mutating:
                try:
                    visual = await milestone_visual_context()
                    if visual:
                        env["visual_state"] = visual[:1500]
                except Exception as e:
                    print(f"[AgentV2] ⚠ Passive visual injection failed: {e}")
            return env

        # Build tool-executor closure that reuses the existing step infrastructure
        async def tool_executor(tool: str, args: dict) -> tuple[str, bool]:
            nonlocal milestone_step_result_idx
            nonlocal last_await_payload
            nonlocal last_tool_was_ui_mutating
            nonlocal response_emitted_to_ui

            # Research synthesis for writing tools + send_response
            _WRITING_FIELDS = {
                "gdocs_create": "body",
                "gdocs_append": "text",
                "write_file": "content",
                "send_response": "message",   # inject research into the reply
            }
            target_field = _WRITING_FIELDS.get(tool)
            if target_field:
                # For send_response: synthesise whenever working_memory has snippets
                # (not gated on is_research so verbal research replies also get content)
                wm_snippets_available = bool(self.working_memory.get_research_snippets())
                should_synthesize = (
                    is_research
                    if tool != "send_response"
                    else wm_snippets_available
                )
                if should_synthesize:
                    snippets = self._collect_research_snippets(milestone_step_results)
                    if snippets:
                        try:
                            synthesized = await self._synthesize_research_body(
                                provider=provider,
                                user_text=user_text,
                                task_summary=plan.task_summary or "",
                                snippets=snippets,
                                for_response=(tool == "send_response"),
                            )
                            if synthesized:
                                args[target_field] = synthesized
                                if tool == "send_response":
                                    # Upgrade to rich modal so markdown renders properly
                                    args.setdefault("modal", "rich")
                                    args.setdefault("title", "Research Results")
                                print(f"[AgentV2] 📝 Synthesized research for {tool} ({len(synthesized)} chars)")
                        except Exception as e:
                            print(f"[AgentV2] ⚠ Research synthesis failed: {e}")

            temp_step = ExecutionStep(
                id=0, tool=tool, args=dict(args),
                description=f"{tool}",
            )
            success = await self._execute_step(
                temp_step, world_state, ws_callback,
                user_text=user_text,
                task_summary=plan.task_summary or "",
            )
            result = str(temp_step.result or "") if success else str(temp_step.error or "")
            if trace_id:
                intent = world_state.intent
                journal_request_trace(
                    trace_id=trace_id,
                    phase="tool_verification",
                    intent=intent.action.value if intent else "unknown",
                    target_type=intent.target_type.value if intent else "unknown",
                    route="web_research" if tool == "get_web_information" else "agent_execution",
                    tool_names=[tool],
                    status="passed" if success else "failed",
                    error_code="" if success else _trace_error_code(result),
                )

            if success and tool == "await_reply":
                last_await_payload = dict(temp_step.modal_data or {})
                if "message" not in last_await_payload:
                    last_await_payload["message"] = result
                if ws_callback:
                    payload = {
                        "type": "response",
                        "payload": {
                            "text": result,
                            "display": "card",
                            "await_input": True,
                            "app": context.active_app.lower() if context.active_app else "",
                        },
                    }
                    if temp_step.modal_data:
                        payload["payload"]["modal_data"] = temp_step.modal_data
                    await ws_callback(payload)

            if success and tool == "send_response":
                # Forward the rich modal payload immediately so the UI renders
                # the correct modal type (rich, list, cards, etc.) rather than
                # waiting for the outer plain-text fallback send.
                modal_data = temp_step.modal_data or {}
                if ws_callback:
                    forward_payload: dict = {
                        **modal_data,
                        "display": "card",
                        "app": context.active_app.lower() if context.active_app else "",
                    }
                    await ws_callback({"type": "response", "payload": forward_payload})
                # Record so the outer _execute_milestone_plan fallback is skipped
                response_emitted_to_ui = True
                plan.final_response = modal_data.get("message", result) or result

            if success and tool != "await_reply":
                milestone_step_result_idx += 1
                milestone_step_results[milestone_step_result_idx] = result

            # Track UI-mutating tools for passive visual injection
            from agent.constants import UI_MUTATING_TOOLS as _UI_MUTATING_TOOLS
            last_tool_was_ui_mutating = tool in _UI_MUTATING_TOOLS

            return (result, success)

        # ── Bridge: wraps executor.execute_milestone() for SubAgentManager ──
        # SubAgentManager calls this per milestone; it must capture all closure
        # state (provider, ws_callback, etc.) and return (success, result_summary).

        class _AwaitReplySignal(Exception):
            """Sentinel raised when a milestone suspends via await_reply."""
            def __init__(self, suspended_milestone_id: int, await_payload: dict,
                         await_data: dict):
                self.suspended_milestone_id = suspended_milestone_id
                self.await_payload = await_payload
                self.await_data = await_data

        async def milestone_execute_fn(
            milestone,
            current_deliverables: dict,
        ) -> tuple:
            nonlocal milestone_step_result_idx, last_await_payload

            plan.mark_milestone_in_progress(milestone.id)

            if ws_callback and show_milestone_progress:
                total_m = len(plan.milestones)
                progress_idx = next(
                    (i + 1 for i, m in enumerate(plan.milestones) if m.id == milestone.id),
                    milestone.id,
                )
                await ws_callback({
                    "type": "doing",
                    "text": f"Milestone {progress_idx}/{total_m}: {milestone.goal}",
                    "tool": "milestone",
                })

            # A direct plan has already supplied validated arguments and has
            # passed Adele's normal approval gate.  Do not send a one-step
            # typing action back through the model micro-loop: the overlay can
            # steal focus while it deliberates, causing text to land nowhere.
            direct_tool = str(getattr(milestone, "direct_tool", "") or "").strip()
            if direct_tool:
                milestone.actions_taken = 1
                result, success = await tool_executor(
                    direct_tool,
                    dict(getattr(milestone, "direct_tool_args", {}) or {}),
                )
                if direct_tool == "browser_list_tabs":
                    safe_response, route_status = self._browser_tab_query_response(result)
                    # Keep browser URLs and tab titles out of the milestone
                    # journal and response for a count-only request.
                    plan.final_response = safe_response
                    print(
                        "[AgentV2] Browser tab query diagnostic: "
                        f"route=browser_list_tabs status={route_status}"
                    )
                    return success, safe_response
                if direct_tool == "get_web_information":
                    if not success:
                        return False, (
                            "I couldn't verify current information from a web source. "
                            "Please try again in a moment."
                        )
                    safe_response = await self._summarize_current_information(
                        provider=provider,
                        user_text=user_text,
                        gateway_result=result,
                    )
                    plan.final_response = safe_response
                    return True, safe_response
                return success, result

            success, result_summary = await executor.execute_milestone(
                milestone=milestone,
                plan=plan,
                env_perceiver=milestone_env_perceiver,
                tool_executor=tool_executor,
                deliverables=current_deliverables,
                skill_context=getattr(plan, "skill_context", ""),
                request_scope_tool_names=request_scope_tool_names,
                blocked_await_signatures=blocked_await_signatures,
                ws_callback=ws_callback,
                thinking_level=thinking_level,
            )

            # Detect await_reply suspension — raise a sentinel so the outer
            # method can store PendingExecutionState and return to the caller.
            if not success and result_summary.startswith("AWAIT_REPLY:"):
                try:
                    await_data = json.loads(result_summary[len("AWAIT_REPLY:"):])
                except (json.JSONDecodeError, TypeError):
                    await_data = {}
                if await_data.get("signature"):
                    blocked_await_signatures.add(str(await_data["signature"]))
                await_payload = dict(last_await_payload or {})
                if "message" not in await_payload:
                    await_payload["message"] = str(
                        await_data.get("message") or "I need more information."
                    )
                raise _AwaitReplySignal(
                    suspended_milestone_id=milestone.id,
                    await_payload=await_payload,
                    await_data=await_data,
                )

            return success, result_summary

        # ── Execute milestones via SubAgentManager (parallel where possible) ──
        from multi_agent.sub_agent_manager import SubAgentManager

        sub_manager = SubAgentManager(
            provider=provider,
            tool_declarations=llm_tool_declarations or tool_registry.declarations(),
            system_prompt="",
            ws_callback=ws_callback,
        )

        try:
            from agent.vision_harness import use_vision_provider

            with use_vision_provider(provider):
                deliverables = await sub_manager.dispatch(
                    plan=plan,
                    existing_deliverables=deliverables,
                    execute_fn=milestone_execute_fn,
                    replan_fn=self.planner.replan_remaining if (self.planner and not is_research) else None,
                )
        except _AwaitReplySignal as sig:
            # A milestone requested a reply from the user — suspend execution.
            self._pending_execution = PendingExecutionState(
                execution_id=uuid.uuid4().hex[:10],
                plan=plan,
                created_at=_time.time(),
                provider=provider,
                original_user_request=(
                    pending_execution.original_user_request
                    if pending_execution is not None
                    else user_text
                ),
                selected_tools=[
                    str(decl.get("name", "")).strip()
                    for decl in (llm_tool_declarations or [])
                    if str(decl.get("name", "")).strip()
                ],
                deliverables=dict(deliverables),
                milestone_step_results=dict(milestone_step_results),
                milestone_step_result_idx=milestone_step_result_idx,
                suspended_milestone_id=sig.suspended_milestone_id,
                await_payload=sig.await_payload,
                followup_inputs=list(followup_inputs),
                blocked_await_signatures=sorted(blocked_await_signatures),
                last_opened_url=self._last_opened_url,
            )
            journal_execution_snapshot(
                plan_dict=plan.to_dict(),
                user_text=user_text,
                phase="suspended",
                label=self._pending_execution.execution_id,
                extra={"suspended_milestone_id": sig.suspended_milestone_id},
            )
            await_message = str(
                sig.await_payload.get("message") or "I need more information."
            )
            self.conversation.add_model(await_message)
            return await_message, True

        elapsed = _time.time() - t_start

        # ── Execution Summary ──
        completed = [m for m in plan.milestones if m.status == MilestoneStatus.COMPLETED]
        failed = [m for m in plan.milestones if m.status == MilestoneStatus.FAILED]
        skipped = [m for m in plan.milestones if m.status == MilestoneStatus.SKIPPED]

        print(f"\n[AgentV2] ═══ Milestone Execution Summary ═══")
        print(f"[AgentV2]   Total: {len(plan.milestones)} | "
              f"Completed: {len(completed)} | Failed: {len(failed)} | Skipped: {len(skipped)}")
        print(f"[AgentV2]   Duration: {elapsed:.2f}s")
        print(f"[AgentV2]   Progress: {plan.progress_percentage():.0f}%")
        for m in plan.milestones:
            icon = {
                "COMPLETED": "✓", "FAILED": "✗", "SKIPPED": "⏭",
                "PENDING": "◻", "IN_PROGRESS": "▶",
            }.get(m.status.name, "?")
            hint = f" → {m.result_summary[:80]}" if m.result_summary else ""
            print(f"[AgentV2]   {icon} [{m.id}] {m.goal}{hint}")
        print(f"[AgentV2] ═══{'═' * 50}═══\n")

        # ── Build final response ──
        if plan.is_complete():
            final_response = plan.final_response or "Done!"
            if deliverables and not plan.final_response:
                last_deliv = list(deliverables.values())[-1]
                if last_deliv and len(last_deliv) > 10:
                    final_response = last_deliv
        elif plan.has_failed():
            final_response = self._milestone_failure_message(failed, completed)
        else:
            final_response = f"Partially completed ({len(completed)}/{len(plan.milestones)} milestones)."

        # ── Send final response ──
        try:
            await tool_registry.execute("send_response", {"message": final_response})
        except StopAsyncIteration:
            pass
        except Exception as e:
            print(f"[AgentV2] send_response error: {e}")

        if ws_callback and final_response and not response_emitted_to_ui:
            display_text = final_response.replace("[CONVERSATION_MODE_ON]", "").replace("[CONVERSATION_MODE_OFF]", "")
            display = "pill" if len(display_text) <= 40 else "card"
            await ws_callback({
                "type": "response",
                "payload": {
                    "text": display_text,
                    "display": display,
                    "app": context.active_app.lower() if context.active_app else "",
                },
            })

        self.conversation.add_model(final_response)

        # ── Proactive follow-up (conversation mode only) ──
        # Occasionally hint the user can keep talking
        if getattr(self, '_conversation_mode', False) and plan.is_complete() and _random.random() < 0.35:
            followup = self._suggest_followup(final_response, user_text)
            if followup:
                final_response = f"{final_response}\n\n{followup}"

        # Log research summary
        research_summary = self.working_memory.get_research_summary()
        if research_summary:
            print(f"\n[AgentV2] ═══ Research Summary ═══")
            print(research_summary)
            print(f"[AgentV2] ═══ End Research Summary ═══\n")

        if plan.has_failed():
            _journal_phase = "failed"
        elif plan.is_complete():
            _journal_phase = "completed"
        else:
            _journal_phase = "partial"
        journal_execution_snapshot(
            plan_dict=plan.to_dict(),
            user_text=user_text,
            phase=_journal_phase,
            label=exec_label,
        )

        return (final_response, False)

    @staticmethod
    def _browser_tab_query_response(result: str) -> tuple[str, str]:
        """Build a count-only browser response without retaining tab metadata."""
        try:
            payload = json.loads(result or "{}")
        except (TypeError, ValueError):
            return (
                "I couldn't read the current Chrome tab count. Please check that the ADELE Browser Bridge extension is connected.",
                "invalid_result",
            )

        if payload.get("status") == "browser_bridge_unavailable":
            return (
                "I can't inspect your Chrome tabs because the ADELE Browser Bridge extension is not connected. I did not open Chrome.",
                "bridge_unavailable",
            )

        try:
            count = max(0, int(payload.get("count", 0)))
        except (TypeError, ValueError):
            return (
                "I couldn't read the current Chrome tab count. Please check that the ADELE Browser Bridge extension is connected.",
                "invalid_count",
            )
        noun = "tab" if count == 1 else "tabs"
        return (f"You have {count} open Chrome {noun}.", "ok")

    @staticmethod
    def _current_information_source_text(gateway_result: str) -> str:
        """Extract source text from the web gateway without exposing its metadata."""
        try:
            payload = json.loads(gateway_result or "{}")
        except (TypeError, ValueError):
            return ""
        if not isinstance(payload, dict) or payload.get("ok") is False:
            return ""
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        chunks: list[str] = []
        for key in ("title", "summary", "content"):
            value = str(data.get(key, "") or "").strip()
            if value:
                chunks.append(value)
        items = data.get("items", [])
        if isinstance(items, list):
            for item in items[:5]:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or item.get("title") or "").strip()
                snippet = str(item.get("snippet") or item.get("text") or "").strip()
                combined = " — ".join(part for part in (label, snippet) if part)
                if combined:
                    chunks.append(combined)
        return "\n\n".join(chunks)[:9000]

    async def _summarize_current_information(
        self,
        *,
        provider: LLMProvider,
        user_text: str,
        gateway_result: str,
    ) -> str:
        """Answer a live factual question using only verified gateway content."""
        source_text = self._current_information_source_text(gateway_result)
        if not source_text:
            return "I couldn't verify current information from a web source. Please try again in a moment."

        prompt = (
            f"Question: {user_text}\n\n"
            "Use only the source material below to answer the question concisely. "
            "Do not add facts from memory. If the material does not establish an "
            "answer, say that it could not be verified.\n\n"
            f"Source material:\n{source_text}"
        )
        try:
            response = await provider.generate(
                messages=[{"role": "user", "parts": [{"text": prompt}]}],
                system_prompt=(
                    "You are ADELE. Give a short, factual, source-grounded answer. "
                    "Never reveal hidden reasoning."
                ),
                tools=[],
                temperature=0.1,
                thinking_level="LOW",
            )
            answer = str(getattr(response, "text", "") or "").strip()
            if answer:
                return answer[:6000]
        except Exception:
            pass
        return "I found current source material, but I couldn't summarize it reliably. Please try again."

    def _looks_like_research_doc_task(self, user_text: str, task_summary: str) -> bool:
        """Delegate to the planner's canonical implementation."""
        if self.planner:
            return self.planner._is_research_document_request(user_text, task_summary)
        # Fallback: inline heuristic when planner not yet initialized
        lower = (user_text or "").lower()
        return any(k in lower for k in ("write a document", "create a document", "write a report", "make a doc"))

    def _looks_like_contentful_doc_task(self, user_text: str, task_summary: str) -> bool:
        text = f"{user_text or ''} {task_summary or ''}".lower()
        doc_terms = ("document", "google doc", "report", "brief", "article", "essay", "write about")
        return any(term in text for term in doc_terms)

    def _build_research_stream_lines(self, content_text: str, max_lines: int = 3) -> list[str]:
        lines: list[str] = []
        for raw_line in str(content_text or "").splitlines():
            compact = " ".join(raw_line.split())
            if not compact:
                continue
            while compact and len(lines) < max_lines:
                if len(compact) <= 220:
                    lines.append(compact)
                    compact = ""
                    break
                split_at = compact.rfind(" ", 0, 220)
                if split_at < 80:
                    split_at = 220
                lines.append(compact[:split_at].rstrip())
                compact = compact[split_at:].lstrip()
            if len(lines) >= max_lines:
                break

        if not lines:
            compact = " ".join(str(content_text or "").split())
            if compact:
                lines.append(compact[:220])
        return lines[:max_lines]

    def _emit_research_stream(
        self,
        step: ExecutionStep,
        source_url: str,
        source_title: str,
        content_text: str,
        element_count: int,
    ) -> None:
        print(
            f"[ResearchStream] tool={step.tool} "
            f"source={source_url or 'current page'} "
            f"items={int(element_count or 0)}"
        )
        if source_title:
            print(f"[ResearchStream] title={source_title}")
        for idx, line in enumerate(self._build_research_stream_lines(content_text), 1):
            print(f"[ResearchStream] snippet[{idx}] {line}")

    def _log_research_content(
        self,
        step: ExecutionStep,
        result: str,
        is_research: bool,
        *,
        emit_stream: bool = True,
        commit_to_memory: bool = True,
    ) -> None:
        """Log detailed research content from browser_read_page and similar tools."""
        if not result:
            return
        raw_result = str(result).strip()
        if raw_result.startswith("Opened http") or raw_result.startswith("Opened web search"):
            return

        source_url = ""
        source_title = ""
        content_text = ""
        element_count = 0

        try:
            data = json.loads(result)
            if isinstance(data, dict):
                source_url = data.get("url", "")
                source_title = data.get("title", "")
                element_count = data.get("element_count", 0) or data.get("item_count", 0) or data.get("paragraph_count", 0)
                target_type = str(data.get("target_type", "")).strip().lower()
                content_text = data.get("content", "")

                # For fetch_web_content results
                if not content_text:
                    content_text = data.get("text", data.get("summary", ""))

                # For structured extraction tools
                if isinstance(data.get("items"), list) and (
                    not content_text or target_type in {"search_results", "structured_data"}
                ):
                    preview_rows: list[str] = []
                    for item in data.get("items", [])[:8]:
                        if not isinstance(item, dict):
                            continue
                        label = str(item.get("label", "")).strip()
                        href = str(item.get("href", "")).strip()
                        context = str(item.get("context", "")).strip()
                        row = " | ".join(part for part in (label, context, href) if part)
                        if row:
                            preview_rows.append(row[:220])
                    if preview_rows:
                        content_text = "\n".join(preview_rows)

                # For page-summary tools
                if not content_text and isinstance(data.get("headings"), list):
                    heading_lines = []
                    for h in data.get("headings", [])[:6]:
                        if isinstance(h, dict):
                            text = str(h.get("text", "")).strip()
                            if text:
                                heading_lines.append(text[:140])
                    if heading_lines:
                        page_type = str(data.get("page_type", "unknown")).strip()
                        content_text = f"Page type: {page_type}\n" + "\n".join(heading_lines)
        except (json.JSONDecodeError, TypeError):
            content_text = result[:500] if len(result) >= 60 else ""

        # Log what the agent is reading
        if content_text:
            preview = content_text[:300].replace("\n", " ↵ ")
            if emit_stream:
                print(f"[AgentV2] 📖 READING from: {source_url or 'current page'}")
                print(f"[AgentV2] 📖 Page title: {source_title or '(untitled)'}")
                print(f"[AgentV2] 📖 Elements read: {element_count}")
                print(f"[AgentV2] 📖 Content preview: {preview}{'...' if len(content_text) > 300 else ''}")
                print(f"[AgentV2] 📖 Content length: {len(content_text)} chars")
                self._emit_research_stream(step, source_url, source_title, content_text, element_count)

            # Store as research snippet in working memory (with quality filtering)
            if commit_to_memory and (is_research or len(content_text) >= 100):
                # Skip search engine homepages and browser navigation chrome
                _src_domain = self._domain_key(source_url)
                _junk_domains = {"google.com", "bing.com", "duckduckgo.com", "yahoo.com", "baidu.com"}
                _is_search_page = (
                    _src_domain in _junk_domains
                    or "/webhp" in source_url
                    or "/search?" in source_url
                    or source_url.rstrip("/").endswith(("google.com", "bing.com"))
                )
                _is_chrome_content = content_text.count("[mw_") > 3

                if _is_search_page or _is_chrome_content:
                    print(f"[AgentV2] 📖 Skipping non-research content from {_src_domain or 'unknown'}")
                    reason = "search_page" if _is_search_page else "browser_chrome"
                    print(f"[ResearchStream] stored=false reason={reason}")
                else:
                    was_stored = self.working_memory.log_research_snippet(
                        source=source_url,
                        title=source_title,
                        content=content_text,
                        tool=step.tool,
                    )
                    snippet_count = len(self.working_memory.get_research_snippets())
                    if was_stored:
                        print(f"[AgentV2] 📚 Research stored: {snippet_count} snippet(s) total")
                        print(f"[ResearchStream] stored=true snippets={snippet_count}")
                    else:
                        print(f"[AgentV2] 📚 Research store skipped by working-memory filter")
                        print(f"[ResearchStream] stored=false reason=memory_filter")
        elif emit_stream:
            print(f"[AgentV2] 📖 Page read returned no extractable content (url={source_url})")
            print(f"[ResearchStream] tool={step.tool} empty=true source={source_url or 'current page'}")

    def _extract_research_text(self, tool_result: str) -> str:
        if not tool_result:
            return ""
        raw = str(tool_result).strip()
        if not raw or raw.startswith("ERROR"):
            return ""
        if raw.startswith("Opened http"):
            return ""

        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                target_type = str(data.get("target_type", "")).strip().lower()
                source_url = str(data.get("url", "")).strip()
                if target_type == "search_results":
                    return ""
                if source_url and (
                    self._domain_key(source_url) in {"google.com", "bing.com", "duckduckgo.com", "yahoo.com"}
                    or "/search?" in source_url
                ):
                    return ""
                if isinstance(data.get("content"), str) and data["content"].strip():
                    prefix = []
                    if data.get("title"):
                        prefix.append(f"Title: {data['title']}")
                    if data.get("url"):
                        prefix.append(f"URL: {data['url']}")
                    prefix_text = "\n".join(prefix)
                    return (prefix_text + "\n" + data["content"]).strip()

                items = data.get("items")
                if isinstance(items, list) and items:
                    lines = []
                    if data.get("title"):
                        lines.append(f"Title: {data.get('title')}")
                    if data.get("url"):
                        lines.append(f"URL: {data.get('url')}")
                    for item in items[:10]:
                        if not isinstance(item, dict):
                            continue
                        label = str(item.get("label", "")).strip()
                        context = str(item.get("context", "")).strip()
                        href = str(item.get("href", "")).strip()
                        row = " | ".join(part for part in (label, context, href) if part)
                        if row:
                            lines.append(f"- {row[:240]}")
                    if len(lines) > 2:
                        return "\n".join(lines)

                for key in ("text", "summary", "message"):
                    value = data.get(key)
                    if isinstance(value, str) and len(value.strip()) >= 40:
                        return value.strip()
        except (json.JSONDecodeError, TypeError):
            pass

        return raw if len(raw) >= 60 else ""

    def _collect_research_snippets(self, step_results: dict) -> list[str]:
        snippets: list[str] = []
        seen_source_keys: set[str] = set()
        seen_content_keys: set[str] = set()

        def _remember(snippet_text: str, source_key: str = "") -> bool:
            normalized = " ".join(str(snippet_text or "").split()).lower()[:800]
            if not normalized:
                return False
            if source_key and source_key in seen_source_keys:
                return False
            if normalized in seen_content_keys:
                return False
            if source_key:
                seen_source_keys.add(source_key)
            seen_content_keys.add(normalized)
            return True

        # First, collect from working memory (more structured, with source info)
        wm_snippets = self.working_memory.get_research_snippets()
        for ws in wm_snippets:
            content = ws.get("content", "")
            source = ws.get("source", "")
            title = ws.get("title", "")
            if not content or len(content.strip()) < 40:
                continue
            header_parts = []
            if title:
                header_parts.append(f"Title: {title}")
            if source:
                header_parts.append(f"URL: {source}")
            header = "\n".join(header_parts)
            snippet = (header + "\n" + content).strip()[:3200]
            source_key = source.strip().rstrip("/").lower()
            if _remember(snippet, source_key=source_key):
                snippets.append(snippet)
            if len(snippets) >= 6:
                break

        # Supplement from step_results if needed
        if len(snippets) < 4:
            for _, result in sorted(step_results.items(), key=lambda item: item[0]):
                raw_result = str(result)
                snippet = self._extract_research_text(raw_result)
                if not snippet:
                    continue
                source_key = ""
                try:
                    data = json.loads(raw_result)
                    if isinstance(data, dict):
                        source_key = str(data.get("url", "")).strip().rstrip("/").lower()
                except (json.JSONDecodeError, TypeError):
                    source_key = ""
                snippet = snippet[:3200]
                if _remember(snippet, source_key=source_key):
                    snippets.append(snippet)
                if len(snippets) >= 6:
                    break

        if snippets:
            print(f"[AgentV2] 📚 Collected {len(snippets)} research snippet(s) for document synthesis")

        return snippets

    async def _synthesize_research_body(
        self,
        provider: LLMProvider,
        user_text: str,
        task_summary: str,
        snippets: list[str],
        for_response: bool = False,
    ) -> str:
        snippet_text = "\n\n".join(
            f"[Snippet {idx + 1}]\n{snippet}" for idx, snippet in enumerate(snippets)
        )
        if for_response:
            # Conversational summary — returned directly to the user via send_response
            prompt = (
                f"The user asked: {user_text or task_summary}\n\n"
                "Using ONLY the research snippets below, write a clear and engaging summary "
                "to present to the user. Cover: what it is, key facts, background context, "
                "and anything interesting or directly relevant to the user's question. "
                "Use **bold** section labels but keep the tone conversational. "
                "Return only the summary — no preamble, no meta-commentary.\n\n"
                f"{snippet_text}"
            )
            system_prompt = (
                "You are a knowledgeable research assistant. "
                "Present findings clearly, concisely, and engagingly."
            )
        else:
            # Full document — written to a file or Google Doc
            prompt = (
                "Write a complete, factual document from the research snippets.\n"
                f"Task: {user_text or task_summary}\n\n"
                "Requirements:\n"
                "- Use clear section headings.\n"
                "- Cover major system categories, how they work, and key tradeoffs.\n"
                "- Keep claims grounded in the snippets.\n"
                "- Return only the document text (markdown allowed).\n\n"
                f"{snippet_text}"
            )
            system_prompt = "You are an expert research analyst. Produce concise, accurate prose."
        response = await provider.generate(
            messages=[{"role": "user", "parts": [{"text": prompt}]}],
            system_prompt=system_prompt,
            tools=[],
            temperature=0.2,
            thinking_level="HIGH",
        )
        text = (response.text or "").strip() if response else ""
        if text.startswith("```"):
            text = text.strip("`")
        return text[:14000]

    async def _synthesize_document_body(
        self,
        provider: LLMProvider,
        title: str,
        user_text: str,
        task_summary: str,
    ) -> str:
        prompt = (
            f"Write a complete document titled: {title or 'Untitled'}\n\n"
            f"User request: {user_text or task_summary}\n"
            f"Task summary: {task_summary or user_text}\n\n"
            "Use clear headings and concise, useful prose. Return only the document body."
        )
        kwargs = {
            "messages": [{"role": "user", "parts": [{"text": prompt}]}],
            "system_prompt": "You write polished, factual document drafts.",
            "tools": [],
            "temperature": 0.2,
        }
        try:
            response = await provider.generate(**kwargs, thinking_level="HIGH")
        except TypeError:
            response = await provider.generate(**kwargs)
        text = (response.text or "").strip() if response else ""
        if text.startswith("```"):
            text = text.strip("`")
        return text[:14000]

    def _remember_opened_url(self, step: ExecutionStep, result: str) -> None:
        if step.tool == "open_url":
            candidate = str(step.args.get("url") or "").strip()
            if not candidate:
                import re
                match = re.search(r"https?://[^\s\"']+", str(result))
                if match:
                    candidate = match.group(0).rstrip(".,)")
            if candidate:
                self._last_opened_url = candidate
        elif step.tool == "web_search":
            # web_search opens a Google search URL — track it so the
            # browser_read_page recovery can detect tab mismatches.
            query = str(step.args.get("query", "")).strip()
            if query:
                from urllib.parse import quote_plus
                self._last_opened_url = f"https://www.google.com/search?q={quote_plus(query)}"

    def _domain_key(self, url: str) -> str:
        if not url:
            return ""
        try:
            host = (urlparse(url).netloc or "").lower()
        except Exception:
            return ""
        if host.startswith("www."):
            host = host[4:]
        return host

    async def _recover_browser_context(self, step: ExecutionStep, result: str) -> str:
        browser_read_tools = {
            "browser_read_page",
            "browser_read_text",
            "read_page_content",
            "extract_structured_data",
            "get_page_summary",
        }
        if step.tool not in browser_read_tools or not self._last_opened_url:
            return result

        expected_url = self._last_opened_url

        try:
            payload = json.loads(result)
        except (TypeError, json.JSONDecodeError):
            return result
        if not isinstance(payload, dict):
            return result
        observed_url = str(payload.get("url") or "").strip()
        if not observed_url:
            return result

        expected_domain = self._domain_key(expected_url)
        observed_domain = self._domain_key(observed_url)
        if expected_domain and observed_domain and expected_domain == observed_domain:
            return result

        print(
            f"[AgentV2] {step.tool} context drift detected "
            f"(expected {expected_domain or expected_url}, got {observed_domain or observed_url}); retrying."
        )
        switched = False
        for switch_target in (expected_url, expected_domain):
            if not switch_target:
                continue
            try:
                switch_result = await tool_registry.execute("browser_switch_tab", {"url": switch_target})
                try:
                    switch_payload = json.loads(switch_result)
                    switched = bool(switch_payload.get("ok"))
                except (TypeError, json.JSONDecodeError):
                    switched = "switched" in str(switch_result).lower()
            except Exception as e:
                print(f"[AgentV2] browser_switch_tab recovery failed: {e}")
                switched = False
            if switched:
                break

        if not switched:
            return result

        try:
            await tool_registry.execute("browser_refresh_refs", {})
        except Exception as e:
            print(f"[AgentV2] browser_refresh_refs during recovery failed: {e}")

        retry_args = dict(step.args)
        if step.tool in ("browser_read_page", "browser_read_text"):
            retry_args["refresh"] = True
        try:
            retry_result = await tool_registry.execute(step.tool, retry_args)
        except Exception as e:
            print(f"[AgentV2] {step.tool} recovery retry failed: {e}")
            return result

        return retry_result

    def _extract_visual_coordinates(self, text: str) -> Optional[tuple[int, int]]:
        match = _re.search(r"\(?\b(?:x\s*[:=]\s*)?(\d{1,4})\s*,\s*(?:y\s*[:=]\s*)?(\d{1,4})\b\)?", str(text or ""), _re.I)
        if not match:
            return None
        return int(match.group(1)), int(match.group(2))

    async def _try_conservative_vision_recovery(
        self,
        step: ExecutionStep,
        verification,
    ) -> bool:
        if step.tool not in {"browser_click_match", "find_and_act", "click_ui"}:
            return False
        message = str(getattr(verification, "message", "") or "").lower()
        if not any(marker in message for marker in ("could not find", "element not found", "not found")):
            return False

        target = str(step.args.get("query") or step.args.get("target") or step.description or "the target element")
        question = f"Find the clickable UI element for: {target}. Return its coordinates as (x, y)."
        screen_result = await tool_registry.execute("read_screen", {"question": question})
        coords = self._extract_visual_coordinates(screen_result)
        if not coords:
            return False

        x, y = coords
        click_args = {"x": x, "y": y}
        click_result = await tool_registry.execute("click_element", click_args)
        click_verify = await self.verifier.verify_with_visual(
            tool_name="click_element",
            tool_args=click_args,
            tool_result=click_result,
            success_criteria=step.success_criteria,
            get_current_state=self._get_quick_state,
            get_visual_state=self._get_visual_state,
        )
        if not click_verify.success:
            return False

        step.status = StepStatus.COMPLETED
        step.result = click_result
        return True

    async def _execute_step(
        self,
        step: ExecutionStep,
        world_state: WorldState,
        ws_callback: Optional[WSCallback],
        user_text: str = "",
        task_summary: str = "",
    ) -> bool:
        """
        Execute a single step and verify the result.
        
        Returns:
            True if step succeeded, False if failed
        """
        t_start = _time.time()
        print(f"[AgentV2] ┌─ EXECUTE: {step.tool}")
        print(f"[AgentV2] │  Args: {json.dumps(step.args, ensure_ascii=False)[:300]}")
        
        try:
            gateway_context = self._current_tool_gateway_context()
            set_tool_gateway_context(
                active_app=world_state.active_app,
                browser_url=self._last_opened_url or world_state.browser_url or "",
                background_mode=False,
                browser_bridge_connected=gateway_context["browser_bridge_connected"],
                browser_has_snapshot=gateway_context["browser_has_snapshot"],
                browser_session_id=gateway_context["browser_session_id"],
            )
            browser_read_tools = {
                "browser_read_page",
                "browser_read_text",
                "read_page_content",
                "extract_structured_data",
                "get_page_summary",
            }
            # Before browser reads: verify snapshot matches real browser URL
            # Only check if the snapshot is stale (>3s) — post-nav refresh already covers fresh cases
            if step.tool in browser_read_tools and not step.args.get("refresh"):
                try:
                    from browser.store import browser_store as _bstore
                    _snap = _bstore.get_snapshot()
                    _snap_age = (_time.time() - float(_snap.timestamp or 0)) if _snap else 999
                    if _snap_age > 3.0:
                        _rd_app = await perception.get_active_app()
                        if _rd_app.lower() in perception.BROWSERS:
                            _rd_url = await perception.get_browser_url(_rd_app)
                            if _rd_url and _snap and self._domain_key(_rd_url) != self._domain_key(_snap.url or ""):
                                if step.tool in ("browser_read_page", "browser_read_text"):
                                    step.args["refresh"] = True
                                else:
                                    await tool_registry.execute("browser_refresh_refs", {})
                                print(f"[AgentV2] 🔄 Auto-refresh: browser={self._domain_key(_rd_url)}, "
                                      f"snapshot={self._domain_key(_snap.url or '')}")
                except Exception:
                    pass

            # Screen analysis always runs through the ChatGPT provider selected
            # for this request. It never falls back to a second model client.
            if step.tool == "read_screen":
                from agent.vision_harness import analyze_screen

                result = await analyze_screen(
                    question=str(step.args.get("question") or ""),
                )
            else:
                result = await tool_registry.execute(step.tool, step.args)
            elapsed = _time.time() - t_start
            self._remember_opened_url(step, result)

            print(f"[AgentV2] │  Duration: {elapsed:.2f}s")

            # After web_search: wait for the browser tab to switch and force a
            # snapshot refresh so the next browser_read_page reads the search
            # results instead of whatever tab was previously active.
            if step.tool == "web_search":
                # Wait for a new snapshot instead of a fixed sleep
                from browser.bridge import browser_bridge as _bb
                from browser.store import browser_store as _bstore
                _pre_snap = _bstore.get_snapshot()
                _pre_gen = _pre_snap.generation if _pre_snap else 0
                try:
                    await tool_registry.execute("browser_refresh_refs", {})
                except Exception:
                    pass  # Non-critical
                await _bb.wait_for_snapshot(min_generation=_pre_gen, timeout=2.0)

            # After click navigation: wait for page to load and refresh snapshot
            # so the next read step sees the new page, not stale pre-click data.
            should_refresh_after_nav = step.tool in ("browser_click_match", "browser_click_ref", "open_url")
            if step.tool == "find_and_act" and str(step.args.get("action", "")).lower() == "click":
                should_refresh_after_nav = True
            if should_refresh_after_nav:
                # Event-driven: wait for a snapshot newer than pre-action, with short fallback
                from browser.bridge import browser_bridge as _bb2
                from browser.store import browser_store as _bstore2
                _nav_pre_snap = _bstore2.get_snapshot()
                _nav_pre_gen = _nav_pre_snap.generation if _nav_pre_snap else 0
                try:
                    await tool_registry.execute("browser_refresh_refs", {})
                except Exception:
                    pass
                await _bb2.wait_for_snapshot(min_generation=_nav_pre_gen, timeout=2.0)
                # Update tracked URL to the REAL browser URL after navigation.
                # This prevents drift detection from trying to navigate BACK to
                # the previous page (e.g. Google search results).
                try:
                    _nav_app = await perception.get_active_app()
                    if _nav_app.lower() in perception.BROWSERS:
                        _nav_url = await perception.get_browser_url(_nav_app)
                        if _nav_url:
                            self._last_opened_url = _nav_url
                except Exception:
                    pass

            result = await self._recover_browser_context(step, result)
            
            # Screen descriptions may contain sensitive on-screen content. The
            # response is returned to the user, but never copied to diagnostics.
            if step.tool == "read_screen":
                print("[AgentV2] │  Output: [screen analysis redacted]")
            else:
                result_preview = result[:200].replace("\n", " ↵ ") if result else "(empty)"
                print(f"[AgentV2] │  Output: {result_preview}{'…' if len(result) > 200 else ''}")
                print(f"[AgentV2] │  Output length: {len(result)} chars")

            # ── Research logging & content extraction ──
            is_research = self._looks_like_research_doc_task(user_text, task_summary)
            research_content_tools = {
                "browser_read_page",
                "browser_read_text",
                "fetch_web_content",
                "web_scrape",
                "get_web_information",
                "gworkspace_analyze",
                "gdocs_read",
                "read_page_content",
                "extract_structured_data",
                "get_page_summary",
            }
            if step.tool in research_content_tools:
                self._log_research_content(
                    step,
                    result,
                    is_research,
                    emit_stream=True,
                    commit_to_memory=False,
                )
            elif step.tool == "web_search" and is_research:
                query = step.args.get("query", "")
                print(f"[AgentV2] 🔍 RESEARCH SEARCH: '{query}'")
            elif step.tool == "browser_click_match" and is_research:
                query = step.args.get("query", "")
                print(f"[AgentV2] 🖱️ NAVIGATING to source: clicking '{query}'")
            elif step.tool == "browser_scroll" and is_research:
                direction = step.args.get("direction", "down")
                print(f"[AgentV2] 📜 SCROLLING {direction} for more research content")
            
            # Handle special response tools
            if step.tool == "send_response" and result.startswith("RESPONSE:"):
                raw = result[len("RESPONSE:"):]
                try:
                    modal_data = json.loads(raw)
                    step.result = modal_data.get("message", raw)
                    step.modal_data = modal_data  # structured modal payload
                except (json.JSONDecodeError, TypeError):
                    step.result = raw
                    step.modal_data = None
                step.status = StepStatus.COMPLETED
                return True
            
            if step.tool == "await_reply" and result.startswith("AWAIT:"):
                raw = result[len("AWAIT:"):]
                try:
                    modal_data = json.loads(raw)
                    step.result = modal_data.get("message", raw)
                    step.modal_data = modal_data
                except (json.JSONDecodeError, TypeError):
                    step.result = raw
                    step.modal_data = None
                step.status = StepStatus.COMPLETED
                return True
            
            # Verify the result (visual verification for UI-mutating tools)
            verification = await self.verifier.verify_with_visual(
                tool_name=step.tool,
                tool_args=step.args,
                tool_result=result,
                success_criteria=step.success_criteria,
                get_current_state=self._get_quick_state,
                get_visual_state=self._get_visual_state,
            )
            
            print(f"[AgentV2] │  Verification: success={verification.success}, "
                  f"confidence={verification.confidence:.0%}, msg={verification.message}")

            verification_success = verification.success
            if verification.confidence < 0.5:
                verification_success = False
                if not verification.should_retry:
                    verification.should_retry = True
                verification.message = (
                    f"Verification confidence too low ({verification.confidence:.0%}): "
                    f"{verification.message}"
                )

            if verification_success:
                if step.tool in research_content_tools:
                    self._log_research_content(
                        step,
                        result,
                        is_research,
                        emit_stream=False,
                        commit_to_memory=True,
                    )
                if step.tool not in ("send_response", "await_reply", "read_screen"):
                    self.working_memory.log_action(
                        tool=step.tool,
                        args=step.args,
                        result=result,
                        success=True,
                        session_id=self.conversation._session_id,
                    )
                step.status = StepStatus.COMPLETED
                step.result = result
                total_elapsed = _time.time() - t_start
                print(f"[AgentV2] └─ ✓ Step {step.id} COMPLETED ({total_elapsed:.2f}s)")
                return True
            
            # Verification failed - try conservative vision recovery, retry, or fallback
            if await self._try_conservative_vision_recovery(step, verification):
                total_elapsed = _time.time() - t_start
                print(f"[AgentV2] └─ ✓ Step {step.id} RECOVERED via vision click ({total_elapsed:.2f}s)")
                return True

            if verification.should_retry and step.retries < step.max_retries:
                print(f"[AgentV2] │  ↻ Retrying step {step.id} (attempt {step.retries + 1}/{step.max_retries})…")
                step.retries += 1
                step.status = StepStatus.PENDING  # Reset for retry

                # Adaptive retry: modify args for known failure patterns
                if step.tool == "type_in_field" and "no text field matching" in str(verification.message).lower():
                    # Try alternative field descriptions on retry
                    original_desc = step.args.get("field_description", "")
                    alt_descs = {
                        "Search": "Search or filter",
                        "search": "Search or filter",
                        "Search or filter": "text field",
                        "Message": "Type a message",
                        "message": "Type a message",
                    }
                    new_desc = alt_descs.get(original_desc)
                    if new_desc:
                        step.args["field_description"] = new_desc
                        print(f"[AgentV2] │  Adapted retry: field_description='{new_desc}'")

                if step.tool == "get_ui_tree" and "timed out" in str(verification.message).lower():
                    # On timeout retry, add a brief delay for app to settle
                    import asyncio as _asyncio
                    await _asyncio.sleep(1.0)
                    print(f"[AgentV2] │  Adapted retry: added 1s settle delay after timeout")

                return await self._execute_step(step, world_state, ws_callback, user_text=user_text, task_summary=task_summary)
            
            # Try fallback tool if available
            if step.fallback_tool:
                print(f"[AgentV2] │  Trying fallback tool: {step.fallback_tool}")
                fallback_result = await tool_registry.execute(
                    step.fallback_tool, 
                    step.fallback_args or step.args
                )
                
                fallback_verify = await self.verifier.verify(
                    tool_name=step.fallback_tool,
                    tool_args=step.fallback_args or step.args,
                    tool_result=fallback_result,
                    success_criteria=step.success_criteria
                )
                
                if fallback_verify.success:
                    step.status = StepStatus.COMPLETED
                    step.result = fallback_result
                    return True
            
            # Step failed
            step.status = StepStatus.FAILED
            step.error = verification.message
            if step.tool not in ("send_response", "await_reply"):
                self.working_memory.log_action(
                    tool=step.tool, args=step.args,
                    result=verification.message, success=False,
                    session_id=self.conversation._session_id,
                )
            print(f"[AgentV2] └─ ✗ Step {step.id} FAILED: {verification.message}")
            return False
            
        except StopAsyncIteration:
            # send_response in benchmark mode raises this - treat as success
            step.status = StepStatus.COMPLETED
            step.result = str(step.args.get("message") or step.args.get("response_text", "Done"))
            print(f"[AgentV2] └─ ✓ Step {step.id} COMPLETED (benchmark mode)")
            return True
        except Exception as e:
            print(f"[AgentV2] └─ ✗ Step {step.id} EXCEPTION: {e}")
            step.status = StepStatus.FAILED
            step.error = str(e)
            if step.tool not in ("send_response", "await_reply"):
                self.working_memory.log_action(
                    tool=step.tool, args=step.args,
                    result=str(e), success=False,
                    session_id=self.conversation._session_id,
                )
            return False

    async def _get_quick_state(self) -> dict:
        """Get quick state for verification (minimal perception)."""
        try:
            active_app, window_title, clipboard = await asyncio.gather(
                perception.get_active_app(),
                perception.get_window_title(),
                perception.get_clipboard(),
            )
            browser_url = None
            if active_app.lower() in perception.BROWSERS:
                browser_url = await perception.get_browser_url(active_app)
            
            return {
                "active_app": active_app,
                "window_title": window_title,
                "browser_url": browser_url,
                "clipboard": (clipboard or "")[:500],
                "last_typed_text": self.working_memory.get_last_typed_text()[:500],
            }
        except Exception:
            return {}

    async def _get_visual_state(self) -> str:
        """Get DOM snapshot + screenshot summary for visual verification."""
        parts: list[str] = []
        try:
            from browser.store import browser_store
            snap = browser_store.get_snapshot()
            if snap and snap.elements:
                dom_lines = [f"Page: {snap.title} ({snap.url})"]
                for el in snap.elements[:30]:
                    label = el.primary_label()[:60] if el.primary_label() else el.tag
                    dom_lines.append(f"  [{el.ref_id}] {el.role or el.tag}: {label}")
                parts.append("\n".join(dom_lines))
        except Exception:
            pass

        try:
            screenshot_path = await perception.capture_screenshot()
            if screenshot_path:
                parts.append(f"Screenshot: {screenshot_path}")
        except Exception:
            pass

        return "\n".join(parts) if parts else ""


# ═══════════════════════════════════════════════════════════════
#  Factory Function
# ═══════════════════════════════════════════════════════════════

def create_agent(version: str = "v2", use_planning: bool = True, persist: bool = True):
    """
    Create the active ADELE agent runtime.
    
    Args:
        version: Deprecated compatibility argument. V2 is always used.
        use_planning: For V2, whether to use LLM planning (slower but smarter)
        persist: If True, persist conversation sessions to disk.
                Set False for benchmarks / tests.
        
    Returns:
        AdeleAgentV2 instance
    """
    if str(version or "v2").lower() != "v2":
        print(f"[AgentV2] Ignoring deprecated agent version '{version}' and using V2.")
    return AdeleAgentV2(use_planning=use_planning, persist=persist)
