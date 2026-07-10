# AI Logs

AI logs record runtime decisions produced from text or AI-like rule parsing.

## Query

```http
GET /api/logs/ai
GET /api/logs/ai?limit=20
```

## Fields

| Field | Meaning |
|---|---|
| `id` | SQLite auto-increment id. |
| `session_id` | Runtime session id. |
| `timestamp` | Unix timestamp in seconds. |
| `action` | AI action name, such as `voice_command`. |
| `provider` | Decision source, currently `runtime-rule-parser` for local parsing. |
| `input_text` | Raw voice/prayer text. |
| `output_json` | Parsed intent and generated command. |
| `success` | `1` for success, `0` for failure. |
| `error` | Error text when parsing or command generation fails. |

## Current Write Points

- `POST /api/input/voice`
- WebSocket `input.voice`

Each voice input writes one AI log with the parsed `VoiceIntent` and generated `cmd.robot` payload.
