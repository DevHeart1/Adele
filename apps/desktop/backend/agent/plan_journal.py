"""
Persist milestone plans and execution snapshots to disk (local mode).
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Optional

from runtime_paths import (
    ensure_adele_data_layout,
    get_milestones_dir,
    get_plans_dir,
    get_traces_dir,
)


_SAFE_TRACE_TOKEN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_MAX_TRACE_EVENTS = 200


def _safe_trace_token(value: object, *, fallback: str = "unknown") -> str:
    """Allow only compact machine-readable trace labels, never arbitrary text."""
    normalized = str(value or "").strip().lower().replace(" ", "_")
    return normalized if _SAFE_TRACE_TOKEN.fullmatch(normalized) else fallback


def _safe_trace_tools(tool_names: object) -> list[str]:
    if not isinstance(tool_names, (list, tuple, set)):
        return []
    return sorted({
        token
        for item in tool_names
        if (token := _safe_trace_token(item, fallback=""))
    })[:24]


def _atomic_write_json(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def journal_request_trace(
    *,
    trace_id: str,
    phase: str,
    intent: str = "",
    target_type: str = "",
    route: str = "",
    tool_names: object = (),
    status: str = "",
    error_code: str = "",
) -> None:
    """Append a compact diagnostic event without retaining user or screen data.

    This journal is intentionally separate from plans and sessions.  It is used
    to diagnose routing and verification failures after the fact, so it only
    accepts enumerated labels.  Prompts, response text, URLs, filesystem paths,
    screenshots, credentials, and model reasoning are never accepted here.
    """
    try:
        ensure_adele_data_layout()
        payload = {
            "saved_at": round(time.time(), 3),
            "trace_id": _safe_trace_token(trace_id),
            "phase": _safe_trace_token(phase),
            "intent": _safe_trace_token(intent),
            "target_type": _safe_trace_token(target_type),
            "route": _safe_trace_token(route),
            "tool_names": _safe_trace_tools(tool_names),
            "status": _safe_trace_token(status),
            "error_code": _safe_trace_token(error_code),
        }
        path = os.path.join(get_traces_dir(), "request_trace.json")
        existing: list[dict] = []
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    candidate = json.load(f)
                if isinstance(candidate, list):
                    existing = [entry for entry in candidate if isinstance(entry, dict)]
            except (OSError, ValueError, TypeError):
                existing = []
        existing.append(payload)
        _atomic_write_json(path, existing[-_MAX_TRACE_EVENTS:])
    except Exception:
        # Diagnostics must never disrupt an interactive request.
        pass


def journal_pending_approval(
    *,
    plan_id: str,
    plan_dict: dict[str, Any],
    original_user_request: str,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """Called when a plan is shown to the user for approval."""
    try:
        ensure_adele_data_layout()
        ts = int(time.time())
        fname = f"pending_{plan_id}_{ts}.json"
        payload: dict[str, Any] = {
            "phase": "pending_approval",
            "plan_id": plan_id,
            "saved_at": time.time(),
            "original_user_request": original_user_request,
            "plan": plan_dict,
        }
        if extra:
            payload["extra"] = extra
        _atomic_write_json(os.path.join(get_plans_dir(), fname), payload)
    except Exception as e:
        print(f"[PlanJournal] pending_approval write skipped: {e}")


def journal_execution_snapshot(
    *,
    plan_dict: dict[str, Any],
    user_text: str,
    phase: str,
    label: str,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """
    phase: suspended | completed | failed | partial
    label: short id (e.g. execution_id or plan_id)
    """
    try:
        ensure_adele_data_layout()
        ts = int(time.time())
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:48]
        fname = f"{phase}_{safe_label}_{ts}.json"
        payload: dict[str, Any] = {
            "phase": phase,
            "label": label,
            "saved_at": time.time(),
            "user_text": user_text,
            "plan": plan_dict,
        }
        if extra:
            payload["extra"] = extra
        _atomic_write_json(os.path.join(get_milestones_dir(), fname), payload)
    except Exception as e:
        print(f"[PlanJournal] execution snapshot skipped: {e}")
