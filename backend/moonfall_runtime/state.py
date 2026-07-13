from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from typing import Any


FRONTEND_SCALE = 10.0
WIN_FUEL = 5


@dataclass
class Pose:
    x_cm: float
    y_cm: float
    theta: float = 0.0

    def frontend(self) -> dict[str, float]:
        return {
            "x": round(self.x_cm / FRONTEND_SCALE, 3),
            "y": round(self.y_cm / FRONTEND_SCALE, 3),
            "theta": self.theta,
        }


@dataclass
class Landmark:
    id: str
    name: str
    kind: str
    type: str
    x_cm: float
    y_cm: float
    radius_cm: float
    fuel_blocks: int = 0
    relic_cards: int = 0

    def distance_to(self, pose: Pose | None) -> float:
        if pose is None:
            return 0.0
        return hypot(self.x_cm - pose.x_cm, self.y_cm - pose.y_cm)

    def has_stock_for(self, card_type: str) -> bool:
        if card_type == "explore_relic":
            return self.relic_cards > 0
        if card_type == "energy_priority":
            return self.fuel_blocks > 0
        return False

    def frontend_config(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "type": self.type,
            "center": [
                round(self.x_cm / FRONTEND_SCALE, 3),
                round(self.y_cm / FRONTEND_SCALE, 3),
            ],
            "center_cm": [self.x_cm, self.y_cm],
            "radius": round(self.radius_cm / FRONTEND_SCALE, 3),
            "radius_cm": self.radius_cm,
        }

    def frontend_state(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "type": self.type,
            "active": True,
            "intensity": 1.0,
            "fuel_blocks": self.fuel_blocks,
            "relic_cards": self.relic_cards,
        }

    def frontend_target(self) -> dict[str, Any]:
        return {
            "landmark_id": self.id,
            "type": self.type,
            "kind": self.kind,
            "name": self.name,
            "x": round(self.x_cm / FRONTEND_SCALE, 3),
            "y": round(self.y_cm / FRONTEND_SCALE, 3),
            "x_cm": self.x_cm,
            "y_cm": self.y_cm,
        }


@dataclass
class Faction:
    id: str
    name: str
    player_id: str
    fuel: int = 0
    hp: int = 3
    relic_cards: int = 0
    heart_rate: int = 0
    stress: float = 0.0
    rank: int | None = None

    def frontend(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "players": [self.player_id],
            "rank": self.rank,
            "vars": {
                "fuel": self.fuel,
                "energy_blocks": self.fuel,
                "hp": self.hp,
                "ship_hp": self.hp,
                "relic_cards": self.relic_cards,
                "heart_rate": self.heart_rate,
                "stress": self.stress,
                "declaring_launch": 0,
                "launched": 1 if self.rank else 0,
                "crashed": 0,
                "jammed": 0,
                "shield": 0,
            },
        }


@dataclass
class Unit:
    id: str
    faction_id: str
    pose: Pose
    target: Landmark | None = None
    status: str = "idle"
    carrying: str | None = None
    settled_target_id: str | None = None

    def frontend(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "faction": self.faction_id,
            "kind": "rover",
            "pose": self.pose.frontend(),
            "status": self.status,
            "carrying": self.carrying,
        }
        if self.target is not None:
            data["target"] = self.target.frontend_target()
        return data


@dataclass
class GameState:
    phase: str = "playing"
    turn: int = 1
    current_player_id: str = "p1"
    winner: str | None = None
    last_landmark_id: str | None = None
    factions: dict[str, Faction] = field(default_factory=dict)
    player_to_faction: dict[str, str] = field(default_factory=dict)
    player_to_unit: dict[str, str] = field(default_factory=dict)
    units: dict[str, Unit] = field(default_factory=dict)
    landmarks: dict[str, Landmark] = field(default_factory=dict)

    @classmethod
    def initial(cls) -> "GameState":
        landmarks = {
            "obstacle-1": Landmark("obstacle-1", "西能源站", "resource", "energy_station", 19.22, 52.58, 5.82, fuel_blocks=5),
            "obstacle-2": Landmark("obstacle-2", "东北遗迹", "relic", "ruins", 61.51, 51.09, 5.44, relic_cards=2),
            "obstacle-3": Landmark("obstacle-3", "中央高能站", "resource", "high_energy_station", 37.37, 29.88, 5.77, fuel_blocks=3),
            "obstacle-4": Landmark("obstacle-4", "西南遗迹", "relic", "ruins", 12.71, 10.16, 5.94, relic_cards=2),
            "obstacle-5": Landmark("obstacle-5", "东南能源站", "resource", "energy_station", 61.83, 13.90, 5.41, fuel_blocks=5),
        }
        factions = {
            "pa": Faction("pa", "PIONEER A", "p1"),
            "pb": Faction("pb", "PIONEER B", "p2"),
        }
        units = {
            "r0": Unit("r0", "pa", Pose(5.0, 30.0)),
            "r1": Unit("r1", "pb", Pose(75.0, 30.0)),
        }
        return cls(
            factions=factions,
            player_to_faction={"p1": "pa", "p2": "pb"},
            player_to_unit={"p1": "r0", "p2": "r1"},
            units=units,
            landmarks=landmarks,
        )

    def reset(self) -> None:
        fresh = self.initial()
        self.__dict__.update(fresh.__dict__)

    def config_for_frontend(self) -> dict[str, Any]:
        return {
            "game_id": "moonfall_two_rover",
            "schema_version": "2.0",
            "mode": "duel",
            "flow": {"phases": ["playing", "ended"]},
            "map": {
                "field": {"width_cm": 80, "height_cm": 60},
                "grid": [8, 6],
                "zones": [landmark.frontend_config() for landmark in self.landmarks.values()],
            },
            "factions": [
                {"id": faction.id, "name": faction.name, "players": [faction.player_id]}
                for faction in self.factions.values()
            ],
            "inputs": {"cards": []},
        }

    def world_for_frontend(self) -> dict[str, Any]:
        return {
            "session_id": "local",
            "game_id": "moonfall_two_rover",
            "schema_version": "2.0",
            "phase": self.phase,
            "turn": self.turn,
            "current_player_id": self.current_player_id,
            "current_faction": self.player_to_faction.get(self.current_player_id),
            "global": {"moon_rage": 0, "moon_tier": "sleep"},
            "factions": [faction.frontend() for faction in self.factions.values()],
            "units": [unit.frontend() for unit in self.units.values()],
            "zones": [landmark.frontend_state() for landmark in self.landmarks.values()],
            "rank_order": [f.id for f in self.factions.values() if f.rank],
            "winner": self.winner,
        }

    def next_turn(self) -> None:
        players = list(self.player_to_unit.keys())
        if not players:
            return
        try:
            idx = players.index(self.current_player_id)
        except ValueError:
            idx = 0
        self.current_player_id = players[(idx + 1) % len(players)]
        self.turn += 1

    def update_pose(self, car_id: str, x_cm: float, y_cm: float, theta: float = 0.0, status: str | None = None) -> None:
        unit = self.units.get(car_id)
        if unit is None:
            return
        unit.pose = Pose(x_cm, y_cm, theta)
        if status:
            unit.status = status

    def update_heart_rate(self, player_id: str, heart_rate: int) -> dict[str, Any] | None:
        faction_id = self.player_to_faction.get(player_id)
        if faction_id is None:
            return None
        faction = self.factions.get(faction_id)
        if faction is None:
            return None
        hr = max(0, int(heart_rate))
        faction.heart_rate = hr
        faction.stress = round(max(0.0, min(1.0, (hr - 80) / 40.0)), 3)
        return {
            "player_id": player_id,
            "faction": faction_id,
            "heart_rate": faction.heart_rate,
            "stress": faction.stress,
        }

    def settle_arrival(self, unit_id: str, landmark_id: str) -> dict[str, Any] | None:
        unit = self.units.get(unit_id)
        landmark = self.landmarks.get(landmark_id)
        if unit is None or landmark is None or unit.settled_target_id == landmark_id:
            return None
        faction = self.factions.get(unit.faction_id)
        if faction is None:
            return None

        reward = 0
        if landmark.type == "energy_station" and landmark.fuel_blocks > 0:
            reward = 1
            landmark.fuel_blocks -= 1
            faction.fuel += 1
        elif landmark.type == "high_energy_station" and landmark.fuel_blocks > 0:
            reward = min(2, landmark.fuel_blocks)
            landmark.fuel_blocks -= reward
            faction.fuel += reward
        elif landmark.type == "ruins" and landmark.relic_cards > 0:
            reward = 1
            landmark.relic_cards -= 1
            faction.relic_cards += 1

        unit.settled_target_id = landmark_id
        unit.status = "arrived"
        unit.carrying = None
        if faction.fuel >= WIN_FUEL and self.winner is None:
            faction.rank = 1
            self.winner = faction.id
            self.phase = "ended"
        if reward > 0:
            self.last_landmark_id = landmark_id

        return {
            "unit_id": unit_id,
            "faction": faction.id,
            "landmark_id": landmark_id,
            "landmark_type": landmark.type,
            "reward": reward,
            "fuel": faction.fuel,
            "relic_cards": faction.relic_cards,
            "winner": self.winner,
        }
