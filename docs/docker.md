# Docker Unified Runtime

This file describes the local Docker environment for the `back-end` branch.

## Files

| File | Purpose |
|---|---|
| `Dockerfile` | Builds the FastAPI backend image with Python 3.12. |
| `docker-compose.yml` | Starts the backend on port `8000` with a persistent SQLite volume. |
| `.dockerignore` | Keeps local virtualenvs, cache, SQLite data, and git metadata out of the image. |

## Start

```bash
docker compose up --build
```

The backend will be available at:

- REST: `http://127.0.0.1:8000/api`
- WebSocket: `ws://127.0.0.1:8000/ws`
- Health: `http://127.0.0.1:8000/api/health`

## Stop

```bash
docker compose down
```

To remove the SQLite volume too:

```bash
docker compose down -v
```

## Environment

The compose file accepts these optional variables from the shell or an `.env` file:

| Variable | Default |
|---|---|
| `DEEPSEEK_API_KEY` | empty |
| `DEEPSEEK_MODEL` | `deepseek-chat` |
| `NVIDIA_BASE_URL` | `http://localhost:8000/v1` |
| `NVIDIA_API_KEY` | empty |
| `NVIDIA_MODEL` | empty |

SQLite is stored in the named Docker volume `moonfall-data` at `/data/moonfall.db`.

## Verify

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/state
curl http://127.0.0.1:8000/api/config
```
