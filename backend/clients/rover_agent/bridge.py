"""Runtime 桥接（M3）：上行 perception.pose，下行 cmd.robot，到达/不可达回报 state.event。

坐标口径（与 docs/websocket_topics.md 对齐）：
- perception.pose 的 x/y 使用厘米；
- theta 单位由 params.bridge.theta_unit 决定（rad|deg），
  与引擎确认后定稿 —— plan §8 开放问题 1，转换只发生在本层。
- cmd.robot 的 x/y 视为厘米坐标；无 x/y 时用 target_zone。
"""
from __future__ import annotations

import asyncio
import json
import math
import threading
import time

import websockets

from rover_agent.controller import validate_speed_level

SOURCE = "rover_agent"


def _msg(topic: str, payload: dict) -> str:
    return json.dumps(
        {"topic": topic, "source": SOURCE, "timestamp": time.time(),
         "payload": payload},
        ensure_ascii=False,
    )


async def _sender(ws, fleet, rate_hz: float, theta_unit: str,
                  pending: dict) -> None:
    period = 1.0 / rate_hz
    while True:
        for rid, rover in fleet.rovers.items():
            pose = rover.pose
            status = rover.status
            if pose is not None:
                theta = (math.degrees(pose.theta) if theta_unit == "deg"
                         else pose.theta)
                await ws.send(_msg("perception.pose", {
                    "car_id": rid,
                    "robot_id": rid,
                    "x": round(pose.x, 3),
                    "y": round(pose.y, 3),
                    "theta": round(theta, 4),
                    "status": status,
                }))
            if status == "arrived" and rid in pending:
                arrival = rover.position
                event = {
                    "event_type": "robot_arrived",
                    "message": f"{rid} 到达目标",
                    "command_id": pending.pop(rid),
                    "car_id": rid,
                    "robot_id": rid,
                    "landmark_id": arrival.get("target_landmark_id"),
                    "landmark_gap_cm": arrival.get("landmark_gap_cm"),
                }
                await ws.send(_msg("state.event", event))
                rover.acknowledge_arrival()
        await asyncio.sleep(period)


async def _receiver(ws, fleet, pending: dict) -> None:
    async for raw in ws:
        try:
            message = json.loads(raw)
        except ValueError:
            continue
        topic = message.get("topic")
        payload = message.get("payload", {})
        if topic == "cmd.rover_map":
            action = payload.get("action")
            try:
                if action == "get_landmarks":
                    result = fleet.get_landmarks()
                elif action == "replace_transient":
                    result = fleet.replace_transient_obstacles(
                        payload.get("obstacles") or [])
                elif action == "clear_transient":
                    result = fleet.clear_transient_obstacles()
                else:
                    raise ValueError(f"未知地图动作: {action}")
                await ws.send(_msg("state.rover_map", result))
            except (KeyError, RuntimeError, TypeError, ValueError) as exc:
                await ws.send(_msg("error", {
                    "code": "invalid_rover_map_command",
                    "message": str(exc),
                    "command_id": payload.get("command_id"),
                }))
            continue
        if topic != "cmd.robot":
            continue
        car_id = payload.get("car_id")
        robot_id = payload.get("robot_id")
        if car_id and robot_id and car_id != robot_id:
            await ws.send(_msg("error", {
                "code": "conflicting_car_id",
                "message": "car_id 与 robot_id 不一致",
                "command_id": payload.get("command_id"),
                "car_id": car_id,
                "robot_id": robot_id,
            }))
            continue
        rid = car_id or robot_id
        try:
            rover = fleet.rover(rid)
        except KeyError:
            continue
        if payload.get("action") == "stop":
            fleet.stop_all()
            continue
        try:
            speed = validate_speed_level(payload.get("speed", 10))
        except ValueError as exc:
            await ws.send(_msg("error", {
                "code": "invalid_robot_speed",
                "message": str(exc),
                "command_id": payload.get("command_id"),
                "car_id": rid,
                "robot_id": rid,
            }))
            continue
        if speed == 0:
            rover.stop()
            pending.pop(rid, None)
            continue
        avoid = payload.get("avoid") or ()
        target = None
        if payload.get("x") is not None and payload.get("y") is not None:
            target = (float(payload["x"]), float(payload["y"]))
        if target is not None:
            ok = rover.set_goal(target, avoid=avoid, speed=speed)
        elif payload.get("landmark_id"):
            ok = rover.set_landmark_goal(
                payload["landmark_id"], avoid=avoid, speed=speed)
        else:
            if payload.get("target_zone"):
                target = rover.zone_center_world(payload["target_zone"])
            if target is None:
                print(f"[bridge] cmd.robot 无可解析目标: {payload}")
                continue
            ok = rover.set_goal(target, avoid=avoid, speed=speed)
        if ok:
            pending[rid] = payload.get("command_id")
        else:
            await ws.send(_msg("state.event", {
                "event_type": "robot_unreachable",
                "message": f"{rid} 无法到达目标",
                "command_id": payload.get("command_id"),
                "car_id": rid,
                "robot_id": rid,
            }))


async def _run(fleet, url: str, rate_hz: float, theta_unit: str) -> None:
    pending: dict[str, str] = {}
    async with websockets.connect(url) as ws:
        print(f"[bridge] 已连接 {url}")
        await asyncio.gather(
            _sender(ws, fleet, rate_hz, theta_unit, pending),
            _receiver(ws, fleet, pending),
        )


def start_bridge_thread(fleet, url: str, rate_hz: float = 10,
                        theta_unit: str = "rad") -> threading.Thread:
    """独立线程跑桥接，断线 3s 后自动重连。"""

    def runner() -> None:
        while True:
            try:
                asyncio.run(_run(fleet, url, rate_hz, theta_unit))
            except Exception as exc:  # noqa: BLE001 —— 断线/拒连统一走重连
                print(f"[bridge] 连接中断: {exc}，3s 后重连")
                time.sleep(3)

    thread = threading.Thread(target=runner, name="bridge", daemon=True)
    thread.start()
    return thread
