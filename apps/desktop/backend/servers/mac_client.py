"""
Legacy entrypoint — forwards to ``local_server`` (single desktop backend).
"""

from __future__ import annotations

import asyncio
import os
import sys
from functools import partial

print = partial(print, flush=True)

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

print("[MacClient] Starting unified backend (local_server).")

from servers.local_server import main  # noqa: E402

if __name__ == "__main__":
    asyncio.run(main())
