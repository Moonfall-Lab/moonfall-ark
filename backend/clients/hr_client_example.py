import asyncio
import json
import os
import random
import time

import websockets


WS_URL = os.getenv("MOONFALL_WS_URL", "ws://127.0.0.1:8000/ws")
PLAYER_ID = os.getenv("PLAYER_ID", "p1")


def make_message(topic: str, source: str, payload: dict) -> dict:
    return {
        "topic": topic,
        "source": source,
        "timestamp": time.time(),
        "payload": payload,
    }


async def drain_runtime_messages(websocket) -> None:
    async for raw in websocket:
        message = json.loads(raw)
        if message.get("topic") in {"error", "state.event"}:
            print(f"[hr] runtime: {json.dumps(message, ensure_ascii=False)}")


async def main() -> None:
    print(f"[hr] connecting to {WS_URL} for {PLAYER_ID}")
    async with websockets.connect(WS_URL) as websocket:
        receiver = asyncio.create_task(drain_runtime_messages(websocket))
        try:
            while True:
                heart_rate = random.randint(80, 125)
                message = make_message(
                    "sensor.hr",
                    f"hr_{PLAYER_ID}",
                    {"player_id": PLAYER_ID, "heart_rate": heart_rate},
                )
                await websocket.send(json.dumps(message, ensure_ascii=False))
                print(f"[hr] sent {PLAYER_ID} heart_rate={heart_rate}")
                await asyncio.sleep(1)
        finally:
            receiver.cancel()


if __name__ == "__main__":
    asyncio.run(main())
