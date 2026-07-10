import json
from typing import Any

from app.core.time_utils import unix_ts
from app.db.sqlite import get_conn


def log_event(session_id: str, topic: str, source: str, payload: dict[str, Any]) -> None:
    try:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO event_logs (session_id, timestamp, topic, source, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, unix_ts(), topic, source, json.dumps(payload, ensure_ascii=False)),
            )
    except Exception as exc:
        print(f"[event_logger] log_event failed: {exc}")


def log_llm_call(
    session_id: str,
    provider: str,
    model: str,
    input_text: str,
    output_json: str | None,
    success: bool,
    error: str | None = None,
) -> None:
    try:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO llm_calls (
                    session_id, timestamp, provider, model, input_text, output_json, success, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    unix_ts(),
                    provider,
                    model,
                    input_text,
                    output_json,
                    1 if success else 0,
                    error,
                ),
            )
    except Exception as exc:
        print(f"[event_logger] log_llm_call failed: {exc}")
