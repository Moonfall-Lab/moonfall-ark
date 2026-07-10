from pydantic import BaseModel, Field


class RobotState(BaseModel):
    robot_id: str
    hp: int = 50
    battery: float = 100.0
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0
    status: str = "idle"
    target_zone: str | None = None
    carrying: str | None = None


class PlayerState(BaseModel):
    player_id: str
    name: str | None = None
    robot_id: str | None = None
    heart_rate: int = 80
    baseline_hr: int = 80
    stress: float = 0.0
    energy: float = 0.0


class WorldState(BaseModel):
    game_id: str = "moonfall"
    session_id: str
    phase: str = "prepare"
    fuel: float = 0.0
    core_hp: int = 100
    moon_rage: float = 0.0
    boss_mode: bool = False
    winner: str | None = None
    robots: dict[str, RobotState] = Field(default_factory=dict)
    players: dict[str, PlayerState] = Field(default_factory=dict)
    current_events: list[str] = Field(default_factory=list)
