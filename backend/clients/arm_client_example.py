import asyncio
import json
import os
import time

import websockets


WS_URL = os.getenv("MOONFALL_WS_URL", "ws://127.0.0.1:8000/ws")


def make_message(topic: str, source: str, payload: dict) -> dict:
    return {
        "topic": topic,
        "source": source,
        "timestamp": time.time(),
        "payload": payload,
    }


async def main() -> None:
    print(f"[arm] connecting to {WS_URL}")
    async with websockets.connect(WS_URL) as websocket:
        async for raw in websocket:
            message = json.loads(raw)
            if message.get("topic") != "cmd.arm":
                continue

            command = message.get("payload", {})
            print(f"[arm] received command: {json.dumps(command, ensure_ascii=False)}")
            # TODO: 在这里接真实机械臂控制代码，例如 move_obstacle、drop_dust、strike 等动作映射。
            await asyncio.sleep(1)

            done = make_message(
                "state.event",
                "arm",
                {
                    "event_type": "arm_done",
                    "message": "机械臂动作模拟完成",
                    "command_id": command.get("command_id"),
                    "action": command.get("action"),
                },
            )
            await websocket.send(json.dumps(done, ensure_ascii=False))
            print("[arm] sent arm_done event")


if __name__ == "__main__":
    asyncio.run(main())
