from typing import Any

from pydantic import BaseModel, Field

from app.core.constants import RUNTIME_SOURCE, TOPIC_ERROR
from app.core.time_utils import unix_ts
from app.models.common import ErrorPayload


class RuntimeMessage(BaseModel):
    topic: str
    source: str
    timestamp: float
    payload: dict[str, Any]


class ErrorMessage(RuntimeMessage):
    topic: str = TOPIC_ERROR
    source: str = RUNTIME_SOURCE
    timestamp: float = Field(default_factory=unix_ts)
    payload: ErrorPayload


def make_message(topic: str, payload: dict[str, Any], source: str = RUNTIME_SOURCE) -> RuntimeMessage:
    return RuntimeMessage(topic=topic, source=source, timestamp=unix_ts(), payload=payload)


def make_error(code: str, message: str, raw: Any | None = None) -> ErrorMessage:
    return ErrorMessage(payload=ErrorPayload(code=code, message=message, raw=raw))
