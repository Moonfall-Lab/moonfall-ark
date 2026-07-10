# Project Deployment Environment

This document describes the deployment environment for the `back-end` branch.

## Runtime Profile

| Item | Value |
|---|---|
| Service name | `moonfall-runtime` |
| Runtime | Python 3.12 recommended |
| Web framework | FastAPI + Uvicorn |
| REST base URL | `http://127.0.0.1:8000/api` |
| WebSocket URL | `ws://127.0.0.1:8000/ws` |
| Health check | `GET /api/health` |
| Default host | `0.0.0.0` in deployment, `127.0.0.1` for local access |
| Default port | `8000` |
| Persistent data | SQLite database |

## Deployment Options

| Mode | Use when | Command |
|---|---|---|
| Docker Compose | Team members need the same runtime environment | `docker compose up --build` |
| Local Python | Backend developer is iterating on code | `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Windows helper | Windows local development | `backend/run_server.bat` |
| Linux/macOS helper | Shell-based local development | `backend/run_server.sh` |

## Docker Environment

Docker Compose uses these files:

| File | Purpose |
|---|---|
| `Dockerfile` | Builds the backend image with Python 3.12. |
| `docker-compose.yml` | Starts the backend service and maps port `8000`. |
| `.dockerignore` | Excludes local cache, virtualenv, database, and git metadata. |

Docker stores SQLite in the named volume `moonfall-data` at:

```text
/data/moonfall.db
```

Start:

```bash
docker compose up --build
```

Stop:

```bash
docker compose down
```

Remove persistent data too:

```bash
docker compose down -v
```

## Local Python Environment

From the repository root:

```bash
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On Linux/macOS:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `RUNTIME_HOST` | `0.0.0.0` | Bind address for backend startup scripts. |
| `RUNTIME_PORT` | `8000` | Backend HTTP/WebSocket port. |
| `SQLITE_DB_PATH` | `backend/data/moonfall.db` locally, `/data/moonfall.db` in Docker | SQLite database path. |
| `LLM_PROVIDER` | `deepseek` | Voice/AI provider selector. |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek-compatible API base URL. |
| `DEEPSEEK_API_KEY` | empty | API key. Leave empty for local rule parsing only. |
| `DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek model name. |
| `NVIDIA_BASE_URL` | `http://localhost:8000/v1` | NVIDIA-compatible API base URL. |
| `NVIDIA_API_KEY` | empty | NVIDIA-compatible API key. |
| `NVIDIA_MODEL` | empty | NVIDIA-compatible model name. |

## Network Notes

- Frontend on the same machine can use `127.0.0.1`.
- Frontend on another machine must use the backend machine IPv4 address.
- Open TCP port `8000` on the backend machine firewall for LAN testing.
- WebSocket and REST share the same host and port.

## Verification Checklist

After deployment, verify these endpoints:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/config
curl http://127.0.0.1:8000/api/state
```

Expected health response:

```json
{"ok":true,"service":"moonfall-runtime"}
```

Expected state markers:

- `game_id` is `moonfall_mvp`
- `schema_version` is `1.0`
- `global.moon_rage` uses `0-100`
- `factions`, `units`, `zones`, and `rank_order` exist

## Logs

| Log type | Query |
|---|---|
| AI logs | `GET /api/logs/ai` |
| Functional logs | `GET /api/logs/functional` |

See `docs/ai_logs.md` and `docs/functional_logs.md` for field definitions.
