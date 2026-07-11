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

### 方式一：项目 venv（推荐，Python 3.11+）

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

### 方式二：Anaconda 环境（Python 3.9 + ultralytics）

如果需要同时使用 YOLOv8 / ultralytics（例如 rPPG 视觉检测场景），可以用 Anaconda 的 `yolov8` 环境运行后端：

```bat
cd backend
C:\Users\<用户名>\.conda\envs\yolov8\python.exe -m pip install -r requirements.txt
C:\Users\<用户名>\.conda\envs\yolov8\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

> **Python 3.9 兼容性**：项目代码使用了 `str | None` 等 Python 3.10+ 语法。在 Python 3.9 环境下需额外安装 `eval_type_backport`，否则启动时报 `TypeError: unsupported operand type(s) for |`：
>
> ```bat
> C:\Users\<用户名>\.conda\envs\yolov8\python.exe -m pip install eval_type_backport
> ```

### 端口选择

默认端口 `8000`。如果 8000 被其他服务占用，可改用 `8001` 或其他空闲端口：

```bash
# 命令行指定
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# 环境变量
set RUNTIME_PORT=8001
backend\run_server.bat
```

> 改了后端端口后，前端 `frontend/src/config.js` 的 `HOST` 也要同步修改，否则前端会降级到 mock 假数据。

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `RUNTIME_HOST` | `0.0.0.0` | Bind address for backend startup scripts. |
| `RUNTIME_PORT` | `8000` | Backend HTTP/WebSocket port. Use `8001` if 8000 is occupied. |
| `SQLITE_DB_PATH` | `backend/data/moonfall.db` locally, `/data/moonfall.db` in Docker | SQLite database path. |
| `LLM_PROVIDER` | `deepseek` | Voice/AI provider selector. |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek-compatible API base URL. |
| `DEEPSEEK_API_KEY` | empty | API key. Leave empty for local rule parsing only. |
| `DEEPSEEK_MODEL` | `deepseek-chat` | DeepSeek model name. |
| `NVIDIA_BASE_URL` | `http://localhost:8000/v1` | NVIDIA-compatible API base URL. |
| `NVIDIA_API_KEY` | empty | NVIDIA-compatible API key. |
| `NVIDIA_MODEL` | empty | NVIDIA-compatible model name. |
| `RPPG_URL` | `http://192.168.20.29:5050` | rPPG Server address (DGX). Used by `rppg_bridge.py`. |
| `MOONFALL_WS` | `ws://127.0.0.1:8000/ws` | Moonfall WebSocket address for `rppg_bridge.py` to push heart rate. Port must match `RUNTIME_PORT`. |
| `POLL_INTERVAL` | `1.0` | rPPG polling interval in seconds. |

## Network Notes

- Frontend on the same machine can use `127.0.0.1`.
- Frontend on another machine must use the backend machine IPv4 address.
- Open TCP port `8000` (or `8001` if using alternate port) on the backend machine firewall for LAN testing.
- WebSocket and REST share the same host and port.
- If the default port `8000` is occupied by another service, use `8001` and update `frontend/src/config.js` accordingly.
- rPPG Server (DGX) communicates with `rppg_bridge.py` via HTTP (`RPPG_URL`), not WebSocket. Ensure the bridge machine can reach the DGX IP on port 5050.

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
