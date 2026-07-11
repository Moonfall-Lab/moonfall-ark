from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

import yaml

from app.core.constants import CONFIG_PATH
from app.models.world import FactionState, GlobalState, Pose, UnitState, WorldState, ZoneState


class WorldStateManager:
    def __init__(self, config_path: Path = CONFIG_PATH) -> None:
        self.config_path = Path(config_path)
        self._lock = RLock()
        self.config = self._load_config(self.config_path)
        self._running = False
        self._state = self._new_state()

    def load_config(self, config_path: str | None = None, config: dict[str, Any] | None = None) -> WorldState:
        with self._lock:
            if config is not None:
                self.config = deepcopy(config)
            elif config_path:
                self.config_path = Path(config_path)
                self.config = self._load_config(self.config_path)
            else:
                self.config = self._load_config(self.config_path)
            self._state = self._new_state()
            return self._state

    def reset(self) -> WorldState:
        with self._lock:
            self._state = self._new_state()
            self._running = False
            return self._state

    def start(self) -> WorldState:
        with self._lock:
            self._running = True
            if self._state.phase == "prepare":
                self._state.phase = self._first_runtime_phase()
            return self._state

    def get_state(self) -> WorldState:
        with self._lock:
            return self._state

    def get_state_dict(self) -> dict[str, Any]:
        with self._lock:
            return self._state.model_dump(mode="json", by_alias=True)

    def get_config_dict(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self.config)

    def update_player_hr(self, player_id: str, heart_rate: int) -> WorldState:
        with self._lock:
            baseline = 80
            stress = max(0, int(heart_rate) - baseline)
            self._state.global_.moon_rage = max(
                self._state.global_.moon_rage,
                min(100, int(stress * 1.5)),
            )
            self._state.global_.moon_tier = self._moon_tier(self._state.global_.moon_rage)
            faction = self.faction_for_player(player_id)
            if faction is not None:
                faction.vars["stress"] = stress
                faction.vars["heart_rate"] = int(heart_rate)
            return self._state

    def declare_launch(self, player_id: str) -> FactionState:
        with self._lock:
            faction = self._require_faction_for_player(player_id)
            faction.vars["declaring_launch"] = 1
            return faction

    def apply_card(self, player_id: str | None, card_id: str | None) -> dict[str, Any]:
        with self._lock:
            faction = self._require_faction_for_player(player_id or "p1")
            if card_id == "collect_priority":
                faction.vars["fuel"] = float(faction.vars.get("fuel", 0)) + 1
            elif card_id == "shield_boost":
                faction.vars["shield"] = float(faction.vars.get("shield", 0)) + 1
            return {"player_id": player_id, "faction": faction.id, "card_id": card_id}

    def set_var(self, scope: str, id_: str, var: str, value: Any) -> WorldState:
        with self._lock:
            if scope != "faction":
                raise ValueError("only faction scope is supported in MVP IR")
            faction = self._require_faction(id_)
            faction.vars[var] = value
            if var == "launched" and int(value) == 1:
                self._lock_rank(faction)
            return self._state

    def trigger_event(self, event_id: str, faction_id: str | None = None, data: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            payload = {
                "event_type": event_id,
                "message": self._event_message(event_id, faction_id),
            }
            if faction_id is not None:
                payload["faction"] = faction_id
            if data is not None:
                payload["data"] = data
            if event_id in {"ignition_success", "rank_locked"} and faction_id:
                faction = self._require_faction(faction_id)
                faction.vars["launched"] = 1
                self._lock_rank(faction)
                payload["data"] = {"rank": faction.rank}
            return payload

    def update_unit_from_command(self, robot_id: str, action: str, target_zone: str | None = None) -> None:
        with self._lock:
            unit = self.unit_by_id(robot_id)
            if unit is None:
                return
            unit.status = action
            if action == "collect":
                unit.carrying = "fuel"
            if action == "return":
                unit.carrying = None

    def update_unit_pose(
        self, car_id: str, x: float, y: float, theta: float, status: str,
    ) -> UnitState | None:
        """Store the rover's physical pose in the shared centimeter frame."""
        with self._lock:
            unit = self.unit_by_id(car_id)
            if unit is None:
                return None
            unit.pose = Pose(x=float(x), y=float(y), theta=float(theta))
            unit.status = str(status)
            return unit

    def card_destination(self, player_id: str, skill_id: str) -> tuple[str, str] | None:
        """Resolve a QR skill to an addressed rover and a configured landmark."""
        card_id = self.config.get("qr_cards", {}).get(skill_id)
        rover_id = self.config.get("players", {}).get(player_id)
        if not card_id or not rover_id:
            return None
        if card_id == "return_home":
            return None
        kind = "energy_station" if card_id == "collect" else "ruins" if card_id == "explore_ruin" else None
        if kind is None:
            return None
        unit = self.unit_by_id(rover_id)
        if unit is None:
            return None
        candidates = [item for item in self.config.get("landmarks", []) if item.get("type") == kind]
        if not candidates:
            return None
        landmark = min(candidates, key=lambda item: (
            (float(item["x_cm"]) - unit.pose.x) ** 2 + (float(item["y_cm"]) - unit.pose.y) ** 2,
            item["id"],
        ))
        return rover_id, str(landmark["id"])

    def faction_for_player(self, player_id: str | None) -> FactionState | None:
        if player_id is None:
            return None
        for faction in self._state.factions:
            if player_id in faction.players:
                return faction
        return None

    def unit_for_player(self, player_id: str | None) -> UnitState | None:
        faction = self.faction_for_player(player_id)
        if faction is None:
            return None
        for unit in self._state.units:
            if unit.faction == faction.id:
                return unit
        return None

    def unit_by_id(self, unit_id: str) -> UnitState | None:
        for unit in self._state.units:
            if unit.id == unit_id:
                return unit
        return None

    def _load_config(self, config_path: Path) -> dict[str, Any]:
        with open(config_path, "r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    def _new_state(self) -> WorldState:
        session_id = str(uuid4())
        state = WorldState(
            session_id=session_id,
            game_id=self.config.get("game_id", "moonfall_mvp"),
            schema_version=str(self.config.get("schema_version", "1.0")),
            phase=self.config.get("flow", {}).get("initial_phase", "action"),
            turn=1,
            global_=GlobalState(
                moon_rage=int(self.config.get("global", {}).get("moon_rage", 0)),
                moon_tier="sleep",
            ),
        )
        state.global_.moon_tier = self._moon_tier(state.global_.moon_rage)

        default_vars = deepcopy(self.config.get("vars", {}).get("faction", {}))
        for faction_config in self.config.get("factions", []):
            state.factions.append(
                FactionState(
                    id=faction_config["id"],
                    players=list(faction_config.get("players", [])),
                    rank=None,
                    vars=deepcopy(default_vars),
                )
            )

        for unit_config in self.config.get("units", []):
            pose = unit_config.get("pose", {})
            state.units.append(
                UnitState(
                    id=unit_config["id"],
                    faction=unit_config["faction"],
                    kind=unit_config.get("kind", "rover"),
                    pose=Pose(
                        x=float(pose.get("x", 0.0)),
                        y=float(pose.get("y", 0.0)),
                        theta=float(pose.get("theta", 0.0)),
                    ),
                    status=unit_config.get("status", "idle"),
                    carrying=unit_config.get("carrying"),
                )
            )

        for zone_config in self.config.get("map", {}).get("zones", []):
            state.zones.append(
                ZoneState(
                    id=zone_config["id"],
                    kind=zone_config.get("kind", "zone"),
                    active=bool(zone_config.get("active", True)),
                    intensity=float(zone_config.get("intensity", 1.0)),
                )
            )

        return state

    def _first_runtime_phase(self) -> str:
        phases = self.config.get("flow", {}).get("phases", [])
        return phases[1] if len(phases) > 1 else "action"

    def _require_faction_for_player(self, player_id: str) -> FactionState:
        faction = self.faction_for_player(player_id)
        if faction is None:
            raise ValueError(f"unknown player_id: {player_id}")
        return faction

    def _require_faction(self, faction_id: str) -> FactionState:
        for faction in self._state.factions:
            if faction.id == faction_id:
                return faction
        raise ValueError(f"unknown faction id: {faction_id}")

    def _lock_rank(self, faction: FactionState) -> None:
        if faction.id not in self._state.rank_order:
            self._state.rank_order.append(faction.id)
        faction.rank = self._state.rank_order.index(faction.id) + 1
        self._state.winner = self._state.rank_order[0] if self._state.rank_order else None

    def _moon_tier(self, moon_rage: int) -> str:
        if moon_rage >= 80:
            return "endgame"
        if moon_rage >= 50:
            return "anger"
        if moon_rage >= 25:
            return "alert"
        return "sleep"

    def _event_message(self, event_id: str, faction_id: str | None) -> str:
        if event_id == "dust_storm":
            return "月尘风暴增强"
        if event_id == "ignition_success" and faction_id:
            return f"{faction_id} 升空成功"
        if event_id == "card_input":
            return "收到卡牌输入"
        if event_id == "voice_command":
            return "语音指令已解析"
        return event_id
