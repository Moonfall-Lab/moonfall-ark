# Moonfall Runtime 工程说明

这份文档写给后端维护者和要改代码的队友。Runtime 的原则是：内存里的 `WorldState` 是唯一实时状态中心；SQLite 只记录日志，不参与实时判定；所有外部设备都只和 Runtime 通信。

## 根目录

- `README.md`：启动、测试、队友接入的主教程。
- `.env.example`：环境变量样例，不包含真实 API Key。
- `.gitignore`：忽略 `.env`、虚拟环境、SQLite 数据库、缓存目录。
- `docs/`：接口、topic、协作接入和工程说明。
- `backend/`：FastAPI 后端代码和示例客户端。
- `scripts/`：给 Windows 队友用的辅助脚本。

## docs/

- `docs/engineering_guide.md`：当前文件，说明目录和文件职责。
- `docs/api_contract.md`：HTTP API 与 WebSocket 消息格式。
- `docs/websocket_topics.md`：每个 topic 的输入输出示例。
- `docs/teammate_quickstart.md`：给前端、小车、机械臂、心率、语音同学的连接教程。
- `docs/generation_log.md`：Codex 生成工程、自检和验收记录。

## backend/

- `backend/requirements.txt`：任务书指定依赖。
- `backend/run_server.bat`：Windows 启动后端。
- `backend/run_server.sh`：Linux/macOS 启动后端。
- `backend/configs/moonfall.yaml`：地图、玩家、规则、机械臂动作、语音动作空间、心率参数。
- `backend/data/`：运行时自动生成 SQLite 数据库，已被 `.gitignore` 忽略。

## backend/app/

- `backend/app/main.py`：创建 FastAPI app，注册 HTTP/WebSocket 路由，启动 SQLite 和 GameLoop。
- `backend/app/core/constants.py`：topic 名称、路径、允许动作/区域/机器人等常量。
- `backend/app/core/settings.py`：用 `pydantic-settings` 读取 `.env` 和环境变量。
- `backend/app/core/time_utils.py`：Unix 时间戳和 UTC 时间工具。

## backend/app/models/

- `common.py`：`Position`、`Zone`、`ErrorPayload`。
- `world.py`：`RobotState`、`PlayerState`、`WorldState`。
- `messages.py`：统一 WebSocket 消息 `RuntimeMessage`、`ErrorMessage` 和构造函数。
- `commands.py`：`RobotCommand`、`ArmCommand`、`HumanoidCommand`、`VoiceIntent`。

## backend/app/db/

- `schema.sql`：`game_sessions`、`event_logs`、`llm_calls`、`config_versions` 四张表。
- `sqlite.py`：创建 `backend/data/moonfall.db`、初始化 schema、提供连接。

SQLite 失败时只打印错误，不阻断 Runtime 启动。

## backend/app/services/

- `event_logger.py`：写入 `event_logs` 和 `llm_calls`，所有写入都有 `try/except`。
- `heart_rate.py`：心率、stress、moon_rage 计算。
- `llm_provider.py`：DeepSeek / NVIDIA NIM / OpenAI-compatible 服务切换。
- `voice_parser.py`：语音指令解析，优先 LLM，失败后关键词兜底。

## backend/app/runtime/

- `world_state.py`：内存 WorldState 管理器，负责 reset、更新小车位姿、更新心率、设置燃料、Boss 模式等。
- `rule_engine.py`：燃料胜利、Boss 进入、核心损坏失败、月尘风暴规则。
- `director.py`：根据 moon_rage 和 boss_mode 生成机械臂命令。
- `behavior_ai.py`：小车 MVP 行为策略。
- `game_loop.py`：每秒广播 `state.world`，每 2 秒跑规则和 Director。

## backend/app/api/

- `deps.py`：全局单例和 intent 到 RobotCommand 的转换。
- `http_routes.py`：`/api/*` 接口。
- `websocket_routes.py`：`/ws`、连接管理、topic 路由、错误消息返回。

## backend/clients/

- `robot_client_example.py`：小车接入示例。
- `arm_client_example.py`：机械臂接入示例。
- `hr_client_example.py`：心率假数据示例。
- `voice_client_example.py`：命令行语音文本输入示例。
- `frontend_ws_example.html`：浏览器 WebSocket 大屏接入示例。

## 修改建议

- 新设备接入优先新增 topic 或 payload 字段，不要让设备互相直连。
- 实时逻辑只改 `runtime/` 和 `services/`，不要把判定写进 SQLite。
- 对外消息统一用 `RuntimeMessage` 格式。
- 新增 HTTP API 后同步更新 `docs/api_contract.md`。
- 新增或修改 topic 后同步更新 `docs/websocket_topics.md` 和 `docs/teammate_quickstart.md`。
