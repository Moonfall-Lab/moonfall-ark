"""
rPPG → Moonfall-Ark 心率桥接脚本

功能：
  1. 每秒轮询 rPPG demo server 的 /stats 接口
  2. 将每位 player 的最新心率通过 WebSocket 推送到 moonfall-ark backend
  3. 支持 player_id 映射（rPPG player_1 → moonfall p1）

用法：
  python rppg_bridge.py

环境变量（可在 .env 中设置）：
  RPPG_URL       rPPG server 地址，默认 http://192.168.20.29:5050
  MOONFALL_WS    moonfall backend WS 地址，默认 ws://127.0.0.1:8000/ws
  POLL_INTERVAL  轮询间隔秒数，默认 1.0
"""
import asyncio
import json
import os
import time
from pathlib import Path

import aiohttp
import websockets
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")

RPPG_URL      = os.getenv("RPPG_URL",    "http://192.168.20.29:5050")
MOONFALL_WS   = os.getenv("MOONFALL_WS", "ws://127.0.0.1:8000/ws")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1.0"))

# rPPG player_id  →  moonfall player_id
PLAYER_MAP = {
    "player_1": "p1",
    "player_2": "p2",
    "player_3": "p3",
    "player_4": "p4",
}


def _make_hr_message(moonfall_pid: str, heart_rate: int) -> str:
    return json.dumps({
        "topic":     "sensor.hr",
        "source":    f"hr_{moonfall_pid}",
        "timestamp": time.time(),
        "payload": {
            "player_id":  moonfall_pid,
            "heart_rate": heart_rate,
        },
    }, ensure_ascii=False)


async def _drain(ws):
    """Print any incoming messages from moonfall (state.event / error)."""
    async for raw in ws:
        msg = json.loads(raw)
        topic = msg.get("topic", "")
        if topic in {"error", "state.event", "state.world"}:
            if topic == "error":
                print(f"[bridge] moonfall error: {msg['payload'].get('message')}")
            elif topic == "state.event":
                print(f"[bridge] event: {msg['payload']}")
            # state.world is noisy — only print moon_rage
            elif topic == "state.world":
                rage = msg["payload"].get("global", {}).get("moon_rage")
                if rage is not None:
                    print(f"[bridge] moon_rage={float(rage):.2f}")


async def main():
    print(f"[bridge] rPPG  → {RPPG_URL}/stats")
    print(f"[bridge] push  → {MOONFALL_WS}")
    print(f"[bridge] map   → {PLAYER_MAP}")
    print(f"[bridge] interval={POLL_INTERVAL}s\n")

    async with aiohttp.ClientSession() as http:
        while True:
            try:
                async with websockets.connect(MOONFALL_WS) as ws:
                    print("[bridge] connected to moonfall")
                    drain_task = asyncio.create_task(_drain(ws))
                    try:
                        while True:
                            # Poll rPPG stats
                            try:
                                async with http.get(
                                    f"{RPPG_URL}/stats", timeout=aiohttp.ClientTimeout(total=2)
                                ) as resp:
                                    stats = await resp.json()
                            except Exception as e:
                                print(f"[bridge] rPPG poll failed: {e}")
                                await asyncio.sleep(POLL_INTERVAL)
                                continue

                            now = time.time()
                            for rppg_pid, info in stats.items():
                                moonfall_pid = PLAYER_MAP.get(rppg_pid)
                                if moonfall_pid is None:
                                    continue
                                hr = info.get("hr")
                                if hr is None:
                                    continue
                                # skip stale readings older than 10 s
                                updated_at = info.get("updated_at") or 0
                                if now - updated_at > 10:
                                    continue
                                msg = _make_hr_message(moonfall_pid, int(round(hr)))
                                await ws.send(msg)
                                print(f"[bridge] {rppg_pid} → {moonfall_pid} hr={int(round(hr))} bpm")

                            await asyncio.sleep(POLL_INTERVAL)

                    except websockets.ConnectionClosed as e:
                        print(f"[bridge] moonfall WS closed: {e}, reconnecting…")
                    finally:
                        drain_task.cancel()

            except Exception as e:
                print(f"[bridge] connection failed: {e}, retry in 3s…")
                await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
