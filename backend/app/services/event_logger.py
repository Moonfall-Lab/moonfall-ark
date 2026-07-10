from __future__ import annotations

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
            conn.execute(
                """
                INSERT INTO functional_logs (session_id, timestamp, action, source, payload)
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
            conn.execute(
                """
                INSERT INTO ai_logs (
                    session_id, timestamp, action, provider, input_text, output_json, success, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    unix_ts(),
                    "llm_call",
                    provider,
                    input_text,
                    output_json,
                    1 if success else 0,
                    error,
                ),
            )
    except Exception as exc:
        print(f"[event_logger] log_llm_call failed: {exc}")


def log_ai(
    session_id: str,
    action: str,
    input_text: str,
    output: dict[str, Any],
    provider: str = "runtime-rule-parser",
    success: bool = True,
    error: str | None = None,
) -> None:
    try:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO ai_logs (
                    session_id, timestamp, action, provider, input_text, output_json, success, error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    unix_ts(),
                    action,
                    provider,
                    input_text,
                    json.dumps(output, ensure_ascii=False),
                    1 if success else 0,
                    error,
                ),
            )
    except Exception as exc:
        print(f"[event_logger] log_ai failed: {exc}")


def list_ai_logs(limit: int = 100) -> list[dict[str, Any]]:
    return _list_logs(
        "SELECT id, session_id, timestamp, action, provider, input_text, output_json, success, error "
        "FROM ai_logs ORDER BY id DESC LIMIT ?",
        limit,
    )


def list_functional_logs(limit: int = 100) -> list[dict[str, Any]]:
    return _list_logs(
        "SELECT id, session_id, timestamp, action, source, payload FROM functional_logs ORDER BY id DESC LIMIT ?",
        limit,
    )


def _list_logs(sql: str, limit: int) -> list[dict[str, Any]]:
    try:
        with get_conn() as conn:
            rows = conn.execute(sql, (limit,)).fetchall()
    except Exception as exc:
        print(f"[event_logger] list logs failed: {exc}")
        return []

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key in ("payload", "output_json"):
            if item.get(key):
                try:
                    item[key] = json.loads(item[key])
                except (TypeError, json.JSONDecodeError):
                    pass
        items.append(item)
    return items
