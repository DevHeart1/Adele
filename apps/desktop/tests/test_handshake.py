import sys
import asyncio
import os

import pytest
import websockets


if os.environ.get("ADELE_RUN_MANUAL_WS_TESTS") != "1":
    pytest.skip("Manual WebSocket handshake server; set ADELE_RUN_MANUAL_WS_TESTS=1 to run.", allow_module_level=True)


async def handler(websocket):
    print("HANDSHAKE SUCCESSFUL", flush=True)

async def main():
    async with websockets.serve(handler, "localhost", 8000, ping_interval=None):
        print("Listening on 8000", flush=True)
        await asyncio.Future()

asyncio.run(main())
