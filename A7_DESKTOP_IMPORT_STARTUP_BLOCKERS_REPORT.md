# A7 Desktop Import Startup Blockers Report

Date: 2026-06-17

## Goal

Fix the known desktop backend import/startup blocker discovered during the baseline audit after the monorepo relocation stabilized.

## Main Fix

Repaired the optional MongoDB import block in:

```text
apps/desktop/backend/agent/memory.py
```

Before A7, the file had a `try:` block without a valid `except` or `finally` before the `pymongo` imports completed, which made the backend fail Python parsing.

The import block now:

- Imports `pymongo`, `ObjectId`, and `_PymongoMongoClient` inside the same `try`.
- Sets `PYMONGO_AVAILABLE = True` only when the MongoDB dependencies import successfully.
- Sets `pymongo`, `ObjectId`, and `_PymongoMongoClient` to `None` when MongoDB dependencies are not installed.
- Keeps the fast Mongo timeout wrapper intact.

## Verification

### A7 target compile checks

Ran from the repository root:

```powershell
python -m py_compile apps/desktop/backend/agent/memory.py apps/desktop/backend/servers/local_server.py apps/desktop/backend/agent/core_v2.py
```

Result:

```text
Pass
```

Ran from the backend working directory:

```powershell
python -m py_compile agent/memory.py servers/local_server.py agent/core_v2.py
```

Result:

```text
Pass
```

### Broader backend compile check

Ran:

```powershell
python -m compileall -q apps/desktop/backend
```

Result:

```text
Pass
```

One non-fatal warning remains:

```text
apps/desktop/backend\browser\cdp.py:76: SyntaxWarning: invalid escape sequence '\p'
```

This warning appears to come from a JavaScript regular expression embedded in a Python string and does not block compilation.

### Import smoke checks

Tried lightweight imports from `apps/desktop/backend`:

```powershell
python -c "import agent.memory; print('agent.memory import ok')"
python -c "import servers.local_server; print('servers.local_server import ok')"
python -c "import agent.core_v2; print('agent.core_v2 import ok')"
```

Result:

```text
ModuleNotFoundError: No module named 'dotenv'
ModuleNotFoundError: No module named 'websockets'
```

These are environment/dependency installation blockers, not syntax blockers. They are expected to be handled in A8, which rebuilds the Python/test environment and installs backend requirements.

## Current State

A7 is complete.

The known `memory.py` syntax blocker is fixed, and the backend source compiles across the targeted startup files plus the full backend tree.

## Known Follow-Ups

- A8 should create the selected desktop Python virtual environment and install `apps/desktop/backend/requirements.txt`.
- A8 should rerun the import smoke checks after dependency installation.
- The `browser/cdp.py` invalid escape sequence warning can be cleaned up in a later low-risk backend hygiene pass.
