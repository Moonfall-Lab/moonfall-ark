from __future__ import annotations

from pydantic import BaseModel, Field


class RobotCommand(BaseModel):
    command_id: str
    robot_id: str
    action: str
    target_zone: str | None = None
    x: float | None = None
    y: float | None = None
    speed: float = 0.5
    priority: float = 1.0
    avoid: list[str] = Field(default_factory=list)


class ArmCommand(BaseModel):
    command_id: str
    action: str
    target_zone: str | None = None
    x: float | None = None
    y: float | None = None
    intensity: float = 1.0
    safe_mode: bool = True


class HumanoidCommand(BaseModel):
    command_id: str
    action: str
    text: str | None = None
    target: str | None = None


class VoiceIntent(BaseModel):
    intent_type: str
    player_id: str | None = None
    robot_id: str | None = None
    action: str
    target_zone: str | None = None
    avoid: list[str] = Field(default_factory=list)
    confidence: float = 0.5
