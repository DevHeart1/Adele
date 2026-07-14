"""Small, dependency-free redaction helpers for the Codex integration.

The App Server owns credentials.  These helpers are intentionally used only for
diagnostics and tests; they never attempt to recover or inspect credentials.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_AUTH_URL = re.compile(r"https?://(?=[^\s\"']*(?:auth|login|oauth))[^\s\"']+", re.I)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~-]+", re.I)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_API_KEY = re.compile(r"\b(?:sk|rk|AIza)[-_A-Za-z0-9]{12,}\b")
_EMAIL = re.compile(r"\b([A-Z0-9._%+-])[^@\s]*@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.I)
_WINDOWS_PATH = re.compile(r"\b[A-Z]:\\(?:[^\s\"']+\\?)*[^\s\"']*", re.I)
_HOME_PATH = re.compile(r"(?:~|/Users/[^/\s]+|/home/[^/\s]+)(?:/[^\s\"']*)?")


def mask_email(value: str | None) -> str | None:
    """Return the minimum useful account label without retaining the address."""
    if not value or "@" not in value:
        return None
    local, domain = value.split("@", 1)
    return f"{local[:1] or '*'}***@{domain}"


def redact_text(value: object) -> str:
    """Remove common secret and private-data shapes from diagnostic strings."""
    text = str(value or "")
    text = _AUTH_URL.sub("[redacted-auth-url]", text)
    text = _BEARER.sub("Bearer [redacted]", text)
    text = _JWT.sub("[redacted-jwt]", text)
    text = _API_KEY.sub("[redacted-api-key]", text)
    text = _EMAIL.sub(lambda match: f"{match.group(1)}***@{match.group(2)}", text)
    text = _WINDOWS_PATH.sub("[redacted-path]", text)
    return _HOME_PATH.sub("[redacted-path]", text)


def safe_error_code(error: object) -> str:
    """Classify an exception without returning its potentially private message."""
    name = error.__class__.__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "auth" in name or "unauthor" in name:
        return "authentication_required"
    if "notinstalled" in name or "filenotfound" in name:
        return "runtime_missing"
    if "protocol" in name:
        return "protocol_error"
    if "interrupt" in name or "cancel" in name:
        return "interrupted"
    return "runtime_error"


def safe_path_name(path: str | Path | None) -> str:
    """Expose only a basename when a local diagnostic needs a file reference."""
    return Path(path or "").name or "[redacted-path]"


def redact_mapping(value: Any) -> Any:
    """Redact recursively for tests and structured diagnostics.

    This is deliberately conservative: values under sensitive keys are removed
    rather than transformed, which avoids accidentally retaining a secret.
    """
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if any(token in key.lower() for token in ("token", "secret", "password", "authurl", "apikey", "cookie")):
                result[key] = "[redacted]"
            else:
                result[key] = redact_mapping(item)
        return result
    if isinstance(value, list):
        return [redact_mapping(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
