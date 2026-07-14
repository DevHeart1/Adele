"""
Persist milestone plans and execution snapshots to disk (local mode).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from runtime_paths import ensure_adele_data_layout, get_milestones_dir, get_plans_dir


def _atomic_write_json(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


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
