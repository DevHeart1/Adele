"""
Optional vault context prepended to user messages (TF-IDF recall, no extra services).
"""

from __future__ import annotations

from typing import Any


def build_agent_user_message_with_vault(agent: Any, user_text: str, *, max_hits: int = 5) -> str:
    """
    Prepend vault recall as formatted context before ``AdeleAgentV2.run``.

    Set ADELE_DISABLE_LOCAL_VAULT_RAG=1 to skip.
    """
    import os

    if os.environ.get("ADELE_DISABLE_LOCAL_VAULT_RAG", "").strip().lower() in (
        "1", "true", "yes",
    ):
        return user_text

    text = (user_text or "").strip()
    if not text:
        return user_text

    vault = getattr(agent, "vault", None)
    if vault is None:
        return user_text

    try:
        results = vault.recall(query=text, max_results=max_hits)
    except Exception as e:
        print(f"[Local] Vault recall skipped: {e}")
        return user_text

    if not results:
        return user_text

    from agent.rag import format_vault_results_for_prompt

    block = format_vault_results_for_prompt(text, results)
    if not block.strip():
        return user_text

    print(f"[Local] Vault RAG context injected ({len(block)} chars)")
    return f"{block}\n---\nUser:\n{text}"
