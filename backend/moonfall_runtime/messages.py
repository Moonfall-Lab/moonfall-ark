from __future__ import annotations

import time
from uuid import uuid4

from moonfall_runtime.state import GameState, Landmark


def envelope(topic: str, payload: dict, source: str = "runtime") -> dict:
    return {
        "topic": topic,
        "source": source,
        "timestamp": time.time(),
        "payload": payload,
    }


def state_world_message(state: GameState) -> dict:
    return envelope("state.world", state.world_for_frontend())


def state_event_message(event_type: str, message: str, data: dict | None = None) -> dict:
    payload = {"event_type": event_type, "message": message}
    if data:
        payload["data"] = data
    return envelope("state.event", payload)


def robot_command_message(unit_id: str, target: Landmark, speed: int = 5) -> dict:
    return envelope(
        "cmd.robot",
        {
            "command_id": str(uuid4()),
            "car_id": unit_id,
            "robot_id": unit_id,
            "action": "move",
            "x": target.x_cm,
            "y": target.y_cm,
            "speed": speed,
            "landmark_id": target.id,
        },
    )
