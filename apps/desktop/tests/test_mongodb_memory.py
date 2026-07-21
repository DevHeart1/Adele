"""Regression tests for ADELE's local file-backed memory.

This module retains its historical filename so existing test commands continue
to discover it, but it deliberately verifies that no MongoDB service or client
is used.
"""

from __future__ import annotations

import json

import pytest

from agent.memory import ConversationMemory, TaskStore, UserPreferences, UserProfile, VaultMemory, get_mongo_db


@pytest.fixture(autouse=True)
def local_memory_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ADELE_DATA_DIR", str(tmp_path))


def test_memory_is_file_only():
    assert get_mongo_db() is None


def test_vault_stores_recalls_and_deletes_local_files(tmp_path):
    vault = VaultMemory()
    result = vault.store(
        category="notes",
        title="Important server configuration",
        content="The local backend listens on port 8000.",
        tags=["server", "port"],
    )

    assert result["ok"] is True
    entry_path = tmp_path / "vault" / "notes" / f"{result['id']}.json"
    assert entry_path.is_file()
    assert vault.recall(query="backend", category="notes")[0]["id"] == result["id"]
    assert vault.get_stats() == {"total_entries": 1, "by_category": {"notes": 1}}

    assert vault.delete(result["id"]) is True
    assert not entry_path.exists()
    assert vault.get_stats()["total_entries"] == 0


def test_conversation_preferences_profile_and_tasks_persist_as_files(tmp_path):
    conversation = ConversationMemory(persist=True)
    conversation.add_user("My name is Miles")
    conversation.add_model("Nice to meet you, Miles.")
    conversation._flush_save()

    session_path = tmp_path / "sessions" / f"{conversation._session_id}.json"
    assert session_path.is_file()
    assert len(json.loads(session_path.read_text(encoding="utf-8"))["turns"]) == 2

    preferences = UserPreferences()
    preferences.set("require_memory_approval", False)
    assert json.loads((tmp_path / "preferences.json").read_text(encoding="utf-8"))["require_memory_approval"] is False

    profile = UserProfile()
    profile.extract_facts("My name is Miles")
    assert profile.get_fact("name") == "miles"
    assert (tmp_path / "user_profile.json").is_file()

    tasks = TaskStore()
    task = tasks.add("Check email", 3600)
    assert tasks.list_active()[0].id == task.id
    assert json.loads((tmp_path / "tasks.json").read_text(encoding="utf-8"))[task.id]["description"] == "Check email"
