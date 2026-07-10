import asyncio
import json
import os
import time

import websockets


WS_URL = os.getenv("MOONFALL_WS_URL", "ws://127.0.0.1:8000/ws")
ROBOT_ID = os.getenv("ROBOT_ID", "r1")


def make_message(topic: str, source: str, payload: dict) -> dict:
    return {
        "topic": topic,
        "source": source,
        "timestamp": time.time(),
        "payload": payload,
    }


async def main() -> None:
    print(f"[robot] connecting to {WS_URL} as {ROBOT_ID}")
    async with websockets.connect(WS_URL) as websocket:
        pose = make_message(
            "perception.pose",
            f"robot_{ROBOT_ID}",
            {
                "robot_id": ROBOT_ID,
                "x": 0.0,
                "y": 0.0,
                "theta": 0.0,
                "status": "online",
            },
        )
        await websocket.send(json.dumps(pose, ensure_ascii=False))
        print("[robot] sent initial pose")

        async for raw in websocket:
            message = json.loads(raw)
            if message.get("topic") != "cmd.robot":
                continue

            payload = message.get("payload", {})
            if payload.get("robot_id") != ROBOT_ID:
                continue

            print(f"[robot] command for {ROBOT_ID}: {json.dumps(payload, ensure_ascii=False)}")
            # TODO: 在这里接真实小车控制代码，例如串口、ROS、CAN 或厂商 SDK。
            # 建议只把 Runtime 命令翻译成小车底层动作，不要让小车直接连接其他设备。


if __name__ == "__main__":
    asyncio.run(main())
