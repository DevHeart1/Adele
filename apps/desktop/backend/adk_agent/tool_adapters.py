"""
ADELE — ADK tool adapters.

Thin wrappers that expose the existing ToolRegistry to Google ADK agents.
These are used by the deployable root agent and document the tool surface
for Agent Runtime / Agent Platform.
"""

from __future__ import annotations

async def _run_tool(name: str, args: dict) -> str:
    from tools import registry as tool_registry

    return await tool_registry.execute(name, args)


async def open_url(url: str) -> str:
    """Open a URL in the user's browser or default handler."""
    return await _run_tool("open_url", {"url": url})


async def get_web_information(query: str) -> str:
    """Search the web or read page content for factual information."""
    return await _run_tool("get_web_information", {"query": query})


async def send_response(message: str) -> str:
    """Send a short message to the user in the ADELE UI."""
    return await _run_tool("send_response", {"message": message})


async def click_ui(target: str, button: str = "left") -> str:
    """Click a UI element on the desktop using accessibility targeting."""
    return await _run_tool("click_ui", {"target": target, "button": button})


async def type_text(text: str) -> str:
    """Type text into the focused field or application."""
    return await _run_tool("type_text", {"text": text})


async def list_registered_tools(filter_prefix: str = "") -> str:
    """List ADELE tool names available to the agent (read-only introspection)."""
    from tools import registry as tool_registry

    names = sorted(tool_registry.list_names())
    prefix = (filter_prefix or "").strip().lower()
    if prefix:
        names = [n for n in names if n.startswith(prefix)]
    return "\n".join(names) if names else "(no tools matched)"


ADELE_ADK_TOOLS = [
    open_url,
    get_web_information,
    send_response,
    click_ui,
    type_text,
    list_registered_tools,
]
