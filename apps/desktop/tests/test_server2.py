import asyncio
import os

import pytest
import websockets


if os.environ.get("ADELE_RUN_MANUAL_WS_TESTS") != "1":
    pytest.skip("Manual WebSocket server smoke test; set ADELE_RUN_MANUAL_WS_TESTS=1 to run.", allow_module_level=True)


async def handler(websocket):
    print("Connected!")
    async for message in websocket:
        print(f"Received msg length: {len(message)}")

async def main():
    async with websockets.serve(handler, "localhost", 8001):
        print("Listening on 8001")
        await asyncio.Future()

asyncio.run(main())
