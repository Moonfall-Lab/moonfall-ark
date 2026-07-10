import asyncio
import json
import os
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


async def print_runtime_messages(websocket) -> None:
    async for raw in websocket:
        message = json.loads(raw)
        if message.get("topic") in {"cmd.robot", "state.event", "error"}:
            print(f"\n[runtime] {json.dumps(message, ensure_ascii=False)}")


async def main() -> None:
    print(f"[voice] connecting to {WS_URL} as {PLAYER_ID}")
    print("[voice] 输入中文指令；输入 exit 退出。示例：让一号车绕开月尘去东北资源区采集燃料")
    async with websockets.connect(WS_URL) as websocket:
        receiver = asyncio.create_task(print_runtime_messages(websocket))
        try:
            while True:
                text = await asyncio.to_thread(input, "> ")
                text = text.strip()
                if text.lower() in {"exit", "quit"}:
                    break
                if not text:
                    continue
                message = make_message(
                    "input.voice",
                    "voice_test",
                    {"player_id": PLAYER_ID, "text": text},
                )
                await websocket.send(json.dumps(message, ensure_ascii=False))
                await asyncio.sleep(0.2)
        finally:
            receiver.cancel()


if __name__ == "__main__":
    asyncio.run(main())
