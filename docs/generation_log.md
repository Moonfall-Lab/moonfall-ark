# Moonfall Runtime 生成日志

> 本日志记录 Codex 按任务书生成工程代码、每一步做了什么、自检命令和结果。

## 2026-07-05 10:17 第 1 步：工程骨架

- 创建 `docs/`、`backend/`、`backend/app/`、`backend/clients/`、`scripts/` 等目录。
- 写入 `.gitignore`、`.env.example`、`backend/requirements.txt`。
- 写入 `backend/configs/moonfall.yaml`，包含地图、玩家、规则、小车、机械臂、语音和心率配置。
- 写入 Windows/Linux 启动脚本和 fake demo 批处理脚本。
- 写入 Python 包初始化文件。

自检结果：通过。

- `STRUCTURE_STAGE_1_OK`：关键目录、配置、脚本和初始化文件已存在。
- `NO_FORBIDDEN_DEPS_OK`：依赖清单不包含 Redis、Celery、Postgres、LangChain、LangGraph。

## 2026-07-05 10:24 第 2 步：核心模型、设置、SQLite 和基础服务

- 写入 `backend/app/core/constants.py`、`settings.py`、`time_utils.py`。
- 写入 `backend/app/models/common.py`、`world.py`、`messages.py`、`commands.py`。
- 写入 `backend/app/db/schema.sql`、`sqlite.py`，SQLite 只用于日志和记录。
- 写入 `backend/app/services/event_logger.py`、`heart_rate.py`、`llm_provider.py`、`voice_parser.py`。
- 先用默认 `python` 创建虚拟环境时发现是 Python 3.8，不满足任务书 Python 3.11+ 要求；已删除该环境并用 Python 3.12 重新创建 `backend/.venv`。
- 已安装 `backend/requirements.txt` 中的依赖。

自检结果：通过。

- `python -m compileall -q app`：核心代码语法编译通过。
- `CORE_STAGE_2_OK`：心率 stress/moon_rage 计算通过；语音兜底可把“让一号车绕开月尘去东北资源区采集燃料”解析为 `r1`、`resource_ne`、避开 `dust_center`、动作 `collect`。
- `init_db()` 已自动创建 `backend/data/moonfall.db`，`log_event()` 已向 `event_logs` 写入自检记录。

## 2026-07-05 10:34 第 3 步：Runtime、HTTP API、WebSocket API 和 GameLoop

- 写入 `backend/app/runtime/world_state.py`，实现内存唯一 WorldState 中心。
- 写入 `rule_engine.py`、`director.py`、`behavior_ai.py`、`game_loop.py`。
- 写入 `backend/app/api/deps.py`，统一管理 Runtime 单例和语音 intent 到小车命令的转换。
- 写入 `backend/app/api/http_routes.py`，实现任务书要求的全部 HTTP API。
- 写入 `backend/app/api/websocket_routes.py`，实现 `/ws`、连接管理、广播、topic 路由和错误消息。
- 写入 `backend/app/main.py`，启动时初始化 SQLite 并启动 GameLoop。

自检结果：通过。

- `python -m compileall -q app`：Runtime/API 代码语法编译通过。
- `RUNTIME_API_STAGE_3_OK`：`/api/health`、`/api/state`、`/api/input/hr`、`/api/input/voice`、`/api/debug/trigger_arm`、`/api/debug/trigger_boss` 均通过 TestClient 检查。
- WebSocket `/ws` 可收到初始 `state.world`；缺字段消息返回 `error` / `INVALID_MESSAGE`；`debug.echo` 可原样回传。
- 自检过程中出现 FastAPI/TestClient 依赖栈的 Starlette deprecation warning，不影响运行。

## 2026-07-05 10:44 第 4 步：示例客户端和教程文档

- 写入 `backend/clients/robot_client_example.py`：小车连接、发送 `perception.pose`、监听 `cmd.robot`。
- 写入 `backend/clients/arm_client_example.py`：机械臂监听 `cmd.arm`、模拟执行、回传 `state.event` / `arm_done`。
- 写入 `backend/clients/hr_client_example.py`：每秒随机发送 `sensor.hr`。
- 写入 `backend/clients/voice_client_example.py`：命令行输入文本并发送 `input.voice`。
- 写入 `backend/clients/frontend_ws_example.html`：浏览器连接 WebSocket、显示 `state.world`、事件和命令。
- 重写 `README.md`，包含项目说明、系统环境配置、3 分钟接入、安装依赖、复制 `.env`、启动后端、打开 `/docs`、WebSocket 地址、fake client 运行方法。
- 写入 `docs/engineering_guide.md`、`docs/api_contract.md`、`docs/websocket_topics.md`、`docs/teammate_quickstart.md`。
- 根据机械臂示例需要，在 WebSocket 路由中允许客户端回传 `state.event` 并广播。

自检结果：通过。

- `python -m compileall -q app clients`：后端代码和示例客户端语法编译通过。
- `DOCS_CLIENTS_FILES_OK`：任务书要求的文档和示例客户端文件均存在。
- `TOPIC_DOCS_OK`：`docs/websocket_topics.md` 覆盖任务书列出的全部 topic。
- `README_QUICKSTART_TUTORIAL_OK`：README 和 teammate quickstart 包含系统环境配置、fake client、前端/小车/机械臂/心率/语音接入步骤，以及不要用 `localhost` 连接别人电脑的提醒。

## 2026-07-05 运行脚本修复：`backend/run_server.bat`

- 按用户要求实际运行 `C:\Users\x\Desktop\git\探月\backend\run_server.bat`。
- 首次发现旧验收进程占用 `8000` 端口：Uvicorn reload 父进程 PID `10884` 已退出但 worker PID `872` 仍存活，占用端口。
- 已停止该旧 worker，确认 `8000` 端口释放。
- 修复 `backend/run_server.bat`：现在脚本会优先使用 `backend\.venv`，不存在则尝试创建 Python 3.12/3.11 虚拟环境；缺依赖时自动安装 `requirements.txt`；支持 `RUNTIME_HOST` / `RUNTIME_PORT` 环境变量。
- 已用 PowerShell 调用符实际运行：`& "C:\Users\x\Desktop\git\探月\backend\run_server.bat"`。

自检结果：通过。

- `http://127.0.0.1:8000/api/health` 返回 `{"ok":true,"service":"moonfall-runtime"}`。
- `http://127.0.0.1:8000/api/state` 返回当前 WorldState 和 session id。
- `curl http://127.0.0.1:8000/docs` 返回 HTTP `200`。
