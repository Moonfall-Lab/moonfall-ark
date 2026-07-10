from threading import RLock
from typing import Any
from uuid import uuid4

import yaml

from app.core.constants import CONFIG_PATH
from app.models.world import PlayerState, RobotState, WorldState
from app.services.heart_rate import HeartRateService


class WorldStateManager:
    def __init__(self, config_path=CONFIG_PATH) -> None:
        self.config_path = config_path
        self.config = self._load_config()
        self._lock = RLock()
        self._heart_rate = HeartRateService()
        self._state = self._new_state()

    def reset(self) -> WorldState:
        with self._lock:
            self._state = self._new_state()
            return self._state

    def get_state(self) -> WorldState:
        with self._lock:
            return self._state

    def get_state_dict(self) -> dict[str, Any]:
        with self._lock:
            return self._state.model_dump(mode="json")

    def update_robot_pose(
        self,
        robot_id: str,
        x: float,
        y: float,
        theta: float,
        status: str | None = None,
    ) -> RobotState:
        with self._lock:
            robot = self._state.robots.get(robot_id)
            if robot is None:
                robot = RobotState(robot_id=robot_id, hp=self._default_robot_hp())
                self._state.robots[robot_id] = robot
            robot.x = float(x)
            robot.y = float(y)
            robot.theta = float(theta)
            if status is not None:
                robot.status = status
            return robot

    def update_player_hr(self, player_id: str, heart_rate: int) -> PlayerState:
        with self._lock:
            return self._heart_rate.update_player_hr(self._state, player_id, heart_rate)

    def update_fuel(self, value: float | None = None, delta: float | None = None) -> float:
        with self._lock:
            if value is not None:
                self._state.fuel = float(value)
            if delta is not None:
                self._state.fuel += float(delta)
            return self._state.fuel

    def set_fuel(self, fuel: float) -> float:
        with self._lock:
            self._state.fuel = float(fuel)
            return self._state.fuel

    def set_moon_rage(self, value: float) -> float:
        with self._lock:
            self._state.moon_rage = max(0.0, min(1.0, float(value)))
            return self._state.moon_rage

    def damage_core(self, amount: int) -> int:
        with self._lock:
            self._state.core_hp = max(0, self._state.core_hp - int(amount))
            return self._state.core_hp

    def add_event(self, message: str) -> None:
        with self._lock:
            self._state.current_events.append(message)
            self._state.current_events = self._state.current_events[-20:]

    def clear_events(self) -> None:
        with self._lock:
            self._state.current_events.clear()

    def set_boss_mode(self, value: bool) -> bool:
        with self._lock:
            self._state.boss_mode = bool(value)
            return self._state.boss_mode

    def _load_config(self) -> dict[str, Any]:
        with open(self.config_path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    def _new_state(self) -> WorldState:
        session_id = str(uuid4())
        rules = self.config.get("rules", {})
        state = WorldState(session_id=session_id, core_hp=int(rules.get("core_hp", 100)))

        baseline_hr = int(rules.get("baseline_hr", 80))
        for player_config in self.config.get("players", []):
            player_id = player_config["id"]
            robot_id = player_config.get("robot_id")
            state.players[player_id] = PlayerState(
                player_id=player_id,
                name=player_config.get("name"),
                robot_id=robot_id,
                baseline_hr=baseline_hr,
                heart_rate=baseline_hr,
            )
            if robot_id:
                state.robots[robot_id] = RobotState(robot_id=robot_id, hp=self._default_robot_hp())

        for index in range(1, 5):
            robot_id = f"r{index}"
            state.robots.setdefault(robot_id, RobotState(robot_id=robot_id, hp=self._default_robot_hp()))

        return state

    def _default_robot_hp(self) -> int:
        return int(self.config.get("robots", {}).get("default_hp", 50))
