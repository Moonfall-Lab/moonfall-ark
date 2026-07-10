# Functional Logs

Functional logs record backend-visible actions: REST inputs, WebSocket inputs, control commands, debug commands, state events, and device commands.

## Query

```http
GET /api/logs/functional
GET /api/logs/functional?limit=50
```

## Fields

| Field | Meaning |
|---|---|
| `id` | SQLite auto-increment id. |
| `session_id` | Runtime session id. |
| `timestamp` | Unix timestamp in seconds. |
| `action` | Topic or backend action name. |
| `source` | `http`, `runtime`, `frontend`, device id, or other message source. |
| `payload` | JSON payload recorded for the action. |

## Current Write Points

- REST: health-changing inputs, config load, control start/reset, debug calls.
- WebSocket: accepted input topics and generated `state.event` records.
- Runtime: rule/director events and command broadcasts.

Functional logs are also mirrored to the older `event_logs` table for compatibility with existing tools.
