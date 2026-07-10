from typing import Any

from pydantic import BaseModel


class Position(BaseModel):
    x: float
    y: float
    theta: float = 0.0


class Zone(BaseModel):
    zone_id: str
    name: str | None = None
    center: Position


class ErrorPayload(BaseModel):
    code: str
    message: str
    raw: Any | None = None
