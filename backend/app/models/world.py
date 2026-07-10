from __future__ import annotations

from pydantic import BaseModel, Field


class Pose(BaseModel):
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0


class GlobalState(BaseModel):
    moon_rage: int = 0
    moon_tier: str = "sleep"


class FactionState(BaseModel):
    id: str
    players: list[str] = Field(default_factory=list)
    rank: int | None = None
    vars: dict[str, int | float | str] = Field(default_factory=dict)


class UnitState(BaseModel):
    id: str
    faction: str
    kind: str
    pose: Pose = Field(default_factory=Pose)
    status: str = "idle"
    carrying: str | None = None


class ZoneState(BaseModel):
    id: str
    kind: str
    active: bool = True
    intensity: float = 1.0


class WorldState(BaseModel):
    session_id: str
    game_id: str = "moonfall_mvp"
    schema_version: str = "1.0"
    phase: str = "action"
    turn: int = 1
    global_: GlobalState = Field(default_factory=GlobalState, alias="global")
    factions: list[FactionState] = Field(default_factory=list)
    units: list[UnitState] = Field(default_factory=list)
    zones: list[ZoneState] = Field(default_factory=list)
    rank_order: list[str] = Field(default_factory=list)
    winner: str | None = None

    model_config = {"populate_by_name": True}
