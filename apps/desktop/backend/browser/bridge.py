"""
ADELE — Browser Bridge State
===============================
Tracks extension connection state and queued browser actions.
"""

import asyncio
import json
import os
import secrets
import time
from typing import Dict, List, Optional
from .models import ActionRequest, ActionResult, DomChangeEvent, PageSnapshot
from .store import browser_store
from runtime_state import runtime_state_store
from reliability import with_timeout_retry


class BrowserBridge:
    # If no heartbeat/snapshot is received within this window (seconds),
    # consider the extension disconnected even though it never sent a
    # disconnect event.
    STALE_THRESHOLD: float = 60.0

    def __init__(self):
        configured = os.environ.get("ADELE_BROWSER_BRIDGE_TOKEN", "").strip()
        self._session_token = configured or secrets.token_urlsafe(32)
        self._connected_session_id: Optional[str] = None
        self._last_seen_at: float = 0.0
        self._pending_actions: List[ActionRequest] = []
        self._extension_name: str = ""
        self._latest_result_by_action_id: Dict[str, ActionResult] = {}
        self._latest_dom_change_by_action_id: Dict[str, DomChangeEvent] = {}
        # Event-driven signaling — callers await these instead of polling
        self._result_events: Dict[str, asyncio.Event] = {}
        self._snapshot_event: asyncio.Event = asyncio.Event()
        self._tab_inventory_event: asyncio.Event = asyncio.Event()
        self._event_loop = None
        self._snapshot_generation: int = 0
        self._extension_ws = None  # WebSocket to the extension for push

    def _ensure_loop_events(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._event_loop is loop:
            return
        self._event_loop = loop
        self._result_events = {}
        self._snapshot_event = asyncio.Event()

    @property
    def session_token(self) -> str:
        return self._session_token

    def is_connected(self) -> bool:
        """True only if a session is registered AND we've heard from the
        extension within the staleness window."""
        if not self._connected_session_id:
            return False
        if self._last_seen_at and (time.time() - self._last_seen_at > self.STALE_THRESHOLD):
            # Auto-disconnect stale session
            self.disconnect()
            return False
        return True

    def connected_session_id(self) -> Optional[str]:
        return self._connected_session_id

    def last_seen_at(self) -> float:
        return self._last_seen_at

    def extension_name(self) -> str:
        return self._extension_name

    def authenticate(self, token: str) -> bool:
        return bool(token) and token == self._session_token

    def register_connection(self, session_id: str, extension_name: str = "") -> None:
        self._connected_session_id = session_id
        self._extension_name = extension_name
        self._last_seen_at = time.time()
        runtime_state_store.mark_browser_connected(session_id=session_id)

    def set_extension_ws(self, ws) -> None:
        """Store the extension WebSocket for server-push."""
        self._extension_ws = ws

    def clear_extension_ws(self) -> None:
        self._extension_ws = None

    def touch(self) -> None:
        self._last_seen_at = time.time()

    def register_snapshot(self, snapshot: PageSnapshot) -> None:
        self._ensure_loop_events()
        browser_store.upsert_snapshot(snapshot)
        self._connected_session_id = snapshot.session_id
        self._last_seen_at = time.time()
        runtime_state_store.register_browser_snapshot(snapshot)
        # Signal any coroutines waiting for a new snapshot
        self._snapshot_generation = getattr(snapshot, "generation", 0)
        self._snapshot_event.set()
        self._snapshot_event = asyncio.Event()  # Reset for next waiter

    def register_tab_inventory(self, tabs: List[dict], session_id: str) -> None:
        """Store a complete extension-reported tab inventory for a session."""
        self._ensure_loop_events()
        resolved_session_id = str(session_id or self._connected_session_id or "").strip()
        if not resolved_session_id:
            return
        browser_store.replace_session_tabs(list(tabs or []), resolved_session_id)
        self._last_seen_at = time.time()
        self._tab_inventory_event.set()
        self._tab_inventory_event = asyncio.Event()

    async def request_tab_inventory(self) -> bool:
        """Ask the connected extension for a fresh, read-only tab inventory."""
        if not self.is_connected() or self._extension_ws is None:
            return False
        try:
            await self._extension_ws.send(json.dumps({
                "type": "browser_tab_inventory_request",
                "session_id": self._connected_session_id or "",
            }))
            return True
        except Exception:
            return False

    async def wait_for_tab_inventory(self, timeout: float = 1.0) -> bool:
        """Wait briefly for an inventory response without launching a browser."""
        self._ensure_loop_events()
        event = self._tab_inventory_event
        try:
            await asyncio.wait_for(event.wait(), timeout=max(0.05, timeout))
            return True
        except asyncio.TimeoutError:
            return False

    def queue_action(self, request: ActionRequest) -> ActionResult:
        self._ensure_loop_events()
        if not self.is_connected():
            return ActionResult(
                ok=False,
                message="Browser extension bridge is not connected.",
                action=request.action,
                ref_id=request.ref_id,
            )

        snapshot = browser_store.get_snapshot(request.session_id or self._connected_session_id)
        if not snapshot:
            # Allow snapshot-independent actions (refresh_snapshot, evaluate_js)
            # to be queued even before the first snapshot arrives.
            _snapshotless_actions = {"refresh_snapshot", "evaluate_js", "extract_data", "extract_readability"}
            if request.action in _snapshotless_actions and (request.session_id or self._connected_session_id):
                request.session_id = request.session_id or self._connected_session_id or ""
                request.action_id = request.action_id or f"act_{int(time.time() * 1000)}_{secrets.token_hex(4)}"
                self._result_events[request.action_id] = asyncio.Event()
                self._pending_actions.append(request)
                self._try_push_actions(request.session_id)
                return ActionResult(
                    ok=True,
                    message=f"{request.action} queued (no snapshot yet).",
                    action=request.action,
                    ref_id=request.ref_id,
                    action_id=request.action_id,
                    session_id=request.session_id,
                    pre_generation=0,
                    post_generation=0,
                )
            return ActionResult(
                ok=False,
                message="No active browser snapshot available.",
                action=request.action,
                ref_id=request.ref_id,
            )

        request.session_id = request.session_id or snapshot.session_id
        request.action_id = request.action_id or f"act_{int(time.time() * 1000)}_{secrets.token_hex(4)}"
        self._result_events[request.action_id] = asyncio.Event()
        if request.action in {"evaluate_js", "extract_data", "extract_readability"}:
            request.metadata = {
                **request.metadata,
                "tab_id": request.metadata.get("tab_id", snapshot.tab_id),
                "generation": request.metadata.get("generation", str(snapshot.generation)),
            }
        if request.action == "refresh_snapshot":
            request.metadata = {
                **request.metadata,
                "tab_id": snapshot.tab_id,
                "generation": str(snapshot.generation),
            }
        
        if request.ref_id:
            element = browser_store.get_element(request.ref_id, request.session_id)
            if element:
                request.metadata = {
                    **request.metadata,
                    "tab_id": snapshot.tab_id,
                    "generation": str(snapshot.generation),
                    "agent_id": str(element.agent_id) if element.agent_id else "",
                    "dom_path": element.dom_path,
                    "role": element.role,
                    "tag": element.tag,
                    "label": element.primary_label(),
                    "text": element.text,
                    "aria_label": element.aria_label,
                    "name": element.name,
                    "placeholder": element.placeholder,
                    "href": element.href,
                }
        self._pending_actions.append(request)
        self._try_push_actions(request.session_id)
        return ActionResult(
            ok=True,
            message="Action queued for browser extension execution.",
            action=request.action,
            ref_id=request.ref_id,
            action_id=request.action_id,
            session_id=request.session_id,
            pre_generation=snapshot.generation,
            post_generation=snapshot.generation,
        )

    def drain_actions(self, session_id: Optional[str] = None) -> List[ActionRequest]:
        sid = session_id or self._connected_session_id
        if not sid:
            return []
        drained = [a for a in self._pending_actions if a.session_id == sid]
        self._pending_actions = [a for a in self._pending_actions if a.session_id != sid]
        return drained

    def pending_action_count(self, session_id: Optional[str] = None) -> int:
        sid = session_id or self._connected_session_id
        if not sid:
            return 0
        return sum(1 for action in self._pending_actions if action.session_id == sid)

    def _try_push_actions(self, session_id: str) -> None:
        """Push pending actions to the extension WebSocket immediately."""
        if os.environ.get("ADELE_BROWSER_BRIDGE_PUSH_ACTIONS", "").strip().lower() not in {"1", "true", "yes", "on"}:
            return
        import json as _json
        ws = self._extension_ws
        if ws is None:
            return
        actions = [a for a in self._pending_actions if a.session_id == session_id]
        if not actions:
            return
        try:
            payload = _json.dumps({
                "type": "browser_actions",
                "ok": True,
                "session_id": session_id,
                "actions": [a.__dict__ for a in actions],
            })
            # Keep actions pending until the extension reports a result or polls.
            # Push is an optimization; polling remains the durable fallback.
            # Fire-and-forget: schedule the send on the event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                async def _push():
                    return await ws.send(payload)
                loop.create_task(
                    with_timeout_retry(
                        "browser_bridge.push_actions",
                        _push,
                        timeout_s=2.5,
                        attempts=2,
                    )
                )
        except Exception:
            pass  # Fall back to polling

    def record_action_result(self, result: ActionResult) -> None:
        self._ensure_loop_events()
        if result.action_id:
            self._latest_result_by_action_id[result.action_id] = result
            # Signal any coroutine waiting on this action
            evt = self._result_events.pop(result.action_id, None)
            if evt:
                evt.set()
        self._last_seen_at = time.time()
        runtime_state_store.record_browser_action_result(result)
        details = result.details or {}
        if result.action == "extract_readability" and isinstance(details, dict):
            raw_result = details.get("result", "")
            if raw_result:
                try:
                    import json
                    payload = json.loads(raw_result)
                except Exception:
                    payload = {"ok": False, "message": "invalid_readability_payload"}
                if isinstance(payload, dict):
                    runtime_state_store.record_readability_extraction(payload)

    def latest_action_result(self, action_id: str) -> Optional[ActionResult]:
        return self._latest_result_by_action_id.get(action_id)

    async def wait_for_result(self, action_id: str, timeout: float = 10.0) -> Optional[ActionResult]:
        """Await the action result instead of polling.  Returns None on timeout."""
        self._ensure_loop_events()
        # Already recorded?
        existing = self._latest_result_by_action_id.get(action_id)
        if existing:
            self._result_events.pop(action_id, None)
            return existing
        evt = self._result_events.get(action_id)
        if not evt:
            return None
        try:
            await asyncio.wait_for(evt.wait(), timeout=max(0.05, timeout))
        except asyncio.TimeoutError:
            self._result_events.pop(action_id, None)
            return self._latest_result_by_action_id.get(action_id)
        self._result_events.pop(action_id, None)
        return self._latest_result_by_action_id.get(action_id)

    async def wait_for_snapshot(self, session_id: str = "", min_generation: int = 0, timeout: float = 2.0) -> Optional["PageSnapshot"]:
        """Await the next snapshot with generation > min_generation."""
        self._ensure_loop_events()
        requested_sid = str(session_id or "").strip()
        sid = "" if requested_sid == "default_browser_session_id" else (requested_sid or self._connected_session_id or "")
        # Check if we already have a satisfying snapshot
        current = browser_store.get_snapshot(sid or None)
        if current and current.generation > min_generation:
            return current
        deadline = time.time() + max(0.05, timeout)
        while time.time() < deadline:
            evt = self._snapshot_event
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(evt.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            current = browser_store.get_snapshot(sid or None)
            if current and current.generation > min_generation:
                return current
        return browser_store.get_snapshot(sid or None)

    def record_dom_change(self, event: DomChangeEvent) -> None:
        self._ensure_loop_events()
        if event.action_id:
            self._latest_dom_change_by_action_id[event.action_id] = event
        self._last_seen_at = time.time()

    def latest_dom_change(self, action_id: str) -> Optional[DomChangeEvent]:
        return self._latest_dom_change_by_action_id.get(action_id)

    def disconnect(self) -> None:
        self._connected_session_id = None
        self._extension_name = ""
        runtime_state_store.mark_browser_disconnected()

    def reset(self) -> None:
        self._connected_session_id = None
        self._last_seen_at = 0.0
        self._pending_actions.clear()
        self._latest_result_by_action_id.clear()
        self._latest_dom_change_by_action_id.clear()
        self._result_events.clear()
        self._snapshot_event = asyncio.Event()
        self._tab_inventory_event = asyncio.Event()
        self._snapshot_generation = 0
        self._extension_name = ""
        runtime_state_store.mark_browser_disconnected()


browser_bridge = BrowserBridge()
