# 探月方舟 · Moonfall Runtime

Moonfall Runtime 是“探月方舟”后端游戏大脑。它是唯一的实时状态中心：前端、小车、机械臂、心率设备、语音输入都只连接 Runtime，不互相直连。第一版目标是简单、稳定、方便队友在同一个局域网里快速接入。

## 队友 3 分钟接入

1. 后端同学启动 Runtime。
2. 后端电脑运行 `scripts\show_ip.bat`，把 IPv4 地址发到群里，例如 `192.168.1.23`。
3. 队友连接地址统一写成：
   - HTTP 文档：`http://192.168.1.23:8000/docs`
   - WebSocket：`ws://192.168.1.23:8000/ws`
4. 如果是在后端电脑自己测试，可以用 `127.0.0.1`；如果是在别人电脑、树莓派、小车电脑、前端电脑上连接，不能用 `localhost` 或 `127.0.0.1`，必须用后端电脑 IP。

## 安装依赖

Windows 推荐使用 Python 3.11+。本机如果有多个 Python，可以用 `py -3.12` 或 `py -3.11`。

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

如果 `python --version` 不是 3.11+，用：

```bash
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 配置 .env

从项目根目录复制一份环境变量文件：

```bash
copy .env.example .env
```

系统环境配置已经集中在 `.env.example` 和 `backend/app/core/settings.py`。Runtime 会按下面这些变量读取配置：

| 变量 | 用途 | 默认值 |
| --- | --- | --- |
| `RUNTIME_HOST` | 后端监听地址 | `0.0.0.0` |
| `RUNTIME_PORT` | 后端端口 | `8000` |
| `LLM_PROVIDER` | `deepseek` 或 `nvidia` | `deepseek` |
| `DEEPSEEK_BASE_URL` | DeepSeek OpenAI-compatible 地址 | `https://api.deepseek.com` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | `replace_me` |
| `DEEPSEEK_MODEL` | DeepSeek 模型 | `deepseek-chat` |
| `NVIDIA_BASE_URL` | NVIDIA NIM / OpenAI-compatible 地址 | `http://localhost:8000/v1` |
| `NVIDIA_API_KEY` | NVIDIA NIM API Key | `replace_me` |
| `NVIDIA_MODEL` | NVIDIA NIM 模型 | `replace_me` |
| `SQLITE_DB_PATH` | SQLite 日志数据库路径 | `backend/data/moonfall.db` |

第一版没有 API Key 也能跑，语音会自动走关键词规则兜底。要接 DeepSeek 时，把 `.env` 里的 `DEEPSEEK_API_KEY` 改成真实 key。要切 NVIDIA NIM / OpenAI-compatible 服务，把：

```env
LLM_PROVIDER=nvidia
NVIDIA_BASE_URL=http://你的服务地址/v1
NVIDIA_API_KEY=你的key
NVIDIA_MODEL=你的模型名
```

## 启动后端

任务书指定启动命令：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

已经装过依赖后，日常启动只需要：

```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

也可以双击或运行：

```bash
backend\run_server.bat
```

`run_server.bat` 会优先使用 `backend\.venv`。如果 `.venv` 不存在，它会尝试用 Python 3.12/3.11 创建；如果依赖没装，它会自动执行 `pip install -r requirements.txt`。要临时换端口，可以先设置：

```bat
set RUNTIME_PORT=8010
backend\run_server.bat
```

启动后打开：

- FastAPI 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/health`
- 当前状态：`http://127.0.0.1:8000/api/state`

## WebSocket 地址

后端电脑自己测：

```text
ws://127.0.0.1:8000/ws
```

队友电脑、小车电脑、机械臂电脑、心率电脑连接：

```text
ws://后端电脑IPv4:8000/ws
```

所有消息必须是统一格式：

```json
{
  "topic": "sensor.hr",
  "source": "hr_p1",
  "timestamp": 1720000000.0,
  "payload": {}
}
```

## 运行 fake client

先启动后端，再打开新的终端：

```bash
cd backend
.venv\Scripts\activate
python clients\hr_client_example.py
```

语音测试：

```bash
cd backend
.venv\Scripts\activate
python clients\voice_client_example.py
```

输入：

```text
让一号车绕开月尘去东北资源区采集燃料
```

小车客户端：

```bash
cd backend
.venv\Scripts\activate
python clients\robot_client_example.py
```

机械臂客户端：

```bash
cd backend
.venv\Scripts\activate
python clients\arm_client_example.py
```

一键打开多个 fake client：

```bash
scripts\run_fake_demo.bat
```

如果 fake client 在另一台电脑上运行，先设置 WebSocket 地址：

```bash
set MOONFALL_WS_URL=ws://192.168.1.23:8000/ws
python clients\hr_client_example.py
```

## 队友连接入口

- 前端：打开 `backend/clients/frontend_ws_example.html`，把输入框改成 `ws://后端电脑IPv4:8000/ws`，点击连接。
- 小车：参考 `backend/clients/robot_client_example.py`，发送 `perception.pose`，监听 `cmd.robot`。
- 机械臂：参考 `backend/clients/arm_client_example.py`，监听 `cmd.arm`，执行后回传 `state.event`。
- 心率：参考 `backend/clients/hr_client_example.py`，每秒发送 `sensor.hr`。
- 语音：参考 `backend/clients/voice_client_example.py`，发送 `input.voice`。

更细的接入步骤见 `docs/teammate_quickstart.md`。

真实视觉导航小车代码位于 `backend/clients/rover_agent/`。通用后端接入时，
直接遵循 [`docs/rover_backend_api.md`](docs/rover_backend_api.md) 的 WebSocket
消息契约；坐标统一使用厘米，速度统一使用整数 `0..10`。

## 目前 TODO

- `robot_client_example.py` 保留为最小消息示例；真实视觉导航实现见 `rover_agent`。
- `arm_client_example.py` 里需要队友接真实机械臂 SDK 或控制协议。
- 语音 LLM 默认没有 API Key 时走规则兜底；接入 DeepSeek/NVIDIA 后可增强自然语言理解。
- 第一版没有 Redis、Celery、PostgreSQL、Docker Compose，也没有复杂 Agent 框架。
