"""
Browser-intent helper predicates shared across tool selection and tests.
"""


BROWSER_UI_SHELL_PATTERNS = (
    "osascript",
    "system events",
    "google chrome",
    "safari",
    "arc",
    "brave",
    "firefox",
    "ui element",
    "front window",
    "window 1",
    "active tab",
)


def normalize_phrase(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def looks_like_browser_ui_shell_command(command: str) -> bool:
    lowered = (command or "").lower()
    return any(pattern in lowered for pattern in BROWSER_UI_SHELL_PATTERNS)


def is_browser_chrome_action(text: str) -> bool:
    normalized = normalize_phrase(text)
    chrome_phrases = (
        "switch to my",
        "switch to the",
        "go to my",
        "go to the",
        "next tab",
        "previous tab",
        "prev tab",
        "third tab",
        "second tab",
        "first tab",
        "last tab",
        "new tab",
        "close tab",
        "reopen tab",
        "duplicate tab",
        "pin tab",
        "reload tab",
        "refresh tab",
        "address bar",
        "omnibox",
        "go back",
        "go forward",
        "refresh page",
        "reload page",
    )
    if any(phrase in normalized for phrase in chrome_phrases):
        return True
    return " tab" in normalized and any(
        token in normalized
        for token in (
            "switch",
            "go to",
            "move to",
            "next",
            "previous",
            "prev",
            "close",
            "open",
            "new",
            "third",
            "second",
            "first",
            "last",
        )
    )


def is_browser_tab_query(text: str) -> bool:
    """Return true for read-only questions about the user's browser tabs.

    These requests must not be treated as requests to launch Chrome. Keeping
    this predicate narrow avoids changing normal browser navigation commands
    such as "open a new tab" or "switch to my second tab".
    """
    normalized = normalize_phrase(text)
    if "tab" not in normalized:
        return False

    browser_markers = ("chrome", "google chrome", "browser")
    if not any(marker in normalized for marker in browser_markers):
        return False

    action_markers = (
        "open chrome", "launch chrome", "start chrome", "switch to", "go to",
        "open a new tab", "open new tab", "close tab", "reopen tab", "duplicate tab",
        "next tab", "previous tab", "first tab", "last tab",
    )
    if any(marker in normalized for marker in action_markers):
        return False

    query_markers = (
        "how many", "number of", "count", "list", "show", "which",
        "what tabs", "what are my tabs", "tell me my tabs",
    )
    return any(marker in normalized for marker in query_markers)
