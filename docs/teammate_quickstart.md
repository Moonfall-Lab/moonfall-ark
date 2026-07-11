# 队友快速接入教程

这份文档不是架构说明，是给队友照着连的操作手册。所有设备只连接 Runtime，不要让小车、机械臂、前端、心率设备互相直连。

## 0. 先确认后端电脑 IP

在后端电脑上运行：

```bat
scripts\show_ip.bat
```

找到当前局域网网卡的 IPv4，例如：

```text
IPv4 地址 . . . . . . . . . . . . : 192.168.1.23
```

之后所有队友都用这个地址：

```text
HTTP:      http://192.168.1.23:8000
WebSocket: ws://192.168.1.23:8000/ws
```

重要：如果你不是在后端电脑本机运行，就不要填 `localhost`，也不要填 `127.0.0.1`。这两个地址只代表你自己的电脑，不代表后端电脑。

## 1. 后端同学启动 Runtime

先确认系统环境：

- Python 版本：3.11 或更高。
- 后端监听地址：`RUNTIME_HOST=0.0.0.0`，这样队友电脑才能连进来。
- 后端端口：`RUNTIME_PORT=8000`。
- SQLite 日志路径：`SQLITE_DB_PATH=backend/data/moonfall.db`。
- LLM：没有 API Key 也能跑，语音会自动走关键词规则兜底。

项目根目录已有 `.env.example`。需要改端口、LLM 或数据库路径时，复制一份：

```bat
copy .env.example .env
```

然后编辑 `.env`。

```bat
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

浏览器检查：

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/api/health
http://127.0.0.1:8000/api/state
```

看到 `/api/health` 返回：

```json
{
  "ok": true,
  "service": "moonfall-runtime"
}
```

后端就可以给队友连了。

## 2. 前端同学怎么连

WebSocket 地址：

```text
ws://后端电脑IPv4:8000/ws
```

示例：

```text
ws://192.168.1.23:8000/ws
```

前端连接后会马上收到 `state.world`，之后 Runtime 每秒推一次完整世界状态。

前端需要监听：

- `state.world`：刷新大屏上的燃料、核心血量、月怒、小车位置、玩家心率。
- `state.event`：显示游戏事件。
- `cmd.robot`：如果前端要显示小车目标或指令。
- `cmd.arm`：如果前端要显示机械臂动作。
- `error`：显示调试错误。

可以直接打开示例页面：

```text
backend/clients/frontend_ws_example.html
```

打开后把输入框改成：

```text
ws://192.168.1.23:8000/ws
```

点“连接”。

发送语音输入示例：

```json
{
  "topic": "input.voice",
  "source": "frontend",
  "timestamp": 1720000000.0,
  "payload": {
    "player_id": "p1",
    "text": "让一号车绕开月尘去东北资源区采集燃料"
  }
}
```

## 3. 小车同学怎么连

先在小车电脑上装 Python 依赖，或直接把 WebSocket 逻辑移植到你的控制程序里。

如果小车电脑也有这个仓库：

```bat
cd backend
.venv\Scripts\activate
set MOONFALL_WS_URL=ws://192.168.1.23:8000/ws
set ROBOT_ID=r1
python clients\robot_client_example.py
```

小车启动后先发位置：

以下为通用消息示例。真实视觉导航小车统一使用厘米坐标、弧度角度和整数
`0..10` 速度；完整接口见 [`rover_backend_api.md`](./rover_backend_api.md)。

```json
{
  "topic": "perception.pose",
  "source": "robot_r1",
  "timestamp": 1720000000.0,
  "payload": {
    "car_id": "r1",
    "robot_id": "r1",
    "x": 32.0,
    "y": 51.0,
    "theta": 1.5708,
    "status": "moving"
  }
}
```

小车需要监听 `cmd.robot`：

```json
{
  "topic": "cmd.robot",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "command_id": "uuid",
    "car_id": "r1",
    "action": "collect",
    "target_zone": "resource_ne",
    "speed": 10,
    "priority": 1.2,
    "avoid": ["dust_center"]
  }
}
```

新客户端只处理 `payload.car_id` 等于自己编号的命令；迁移期间兼容
`payload.robot_id`。最小示例客户端仍可在 `robot_client_example.py` 的
TODO 注释处接入自定义控制，完整视觉导航实现位于 `clients/rover_agent/`。

小车动作建议：

- `move_to`：移动到 `target_zone`。
- `collect`：去目标区域采集。
- `avoid_and_move`：避开 `avoid` 列表里的区域再移动。
- `return_base`：返回 `base`。
- `stop`：停止。

## 4. 机械臂同学怎么连

运行示例：

```bat
cd backend
.venv\Scripts\activate
set MOONFALL_WS_URL=ws://192.168.1.23:8000/ws
python clients\arm_client_example.py
```

机械臂监听 `cmd.arm`：

```json
{
  "topic": "cmd.arm",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "command_id": "uuid",
    "action": "drop_dust",
    "target_zone": "dust_center",
    "intensity": 1.0,
    "safe_mode": true
  }
}
```

动作含义：

- `drop_dust`：投放月尘或制造障碍。
- `move_obstacle`：移动障碍。
- `strike`：Boss 阶段打击动作。
- `hover_warning`：悬停警告。
- `home`：回原点。
- `emergency_stop`：急停。

执行完后回传：

```json
{
  "topic": "state.event",
  "source": "arm",
  "timestamp": 1720000000.0,
  "payload": {
    "event_type": "arm_done",
    "message": "机械臂动作完成",
    "command_id": "uuid",
    "action": "drop_dust"
  }
}
```

真实机械臂 SDK 调用写在 `arm_client_example.py` 的 TODO 注释处。

## 5. 心率同学怎么连

### 方式一：模拟心率（调试用）

运行假心率客户端，每秒发送随机心率（80-125 bpm）：

```bat
cd backend
.venv\Scripts\activate
set MOONFALL_WS_URL=ws://192.168.1.23:8000/ws
set PLAYER_ID=p1
python clients\hr_client_example.py
```

### 方式二：真实 rPPG 心率（DGX 接入）

如果 DGX 上已运行 rPPG Server（端口 5050），使用 `rppg_bridge.py` 桥接真实心率：

```bat
cd backend
set RPPG_URL=http://192.168.20.29:5050
set MOONFALL_WS=ws://127.0.0.1:8001/ws
set POLL_INTERVAL=1.0
python rppg_bridge.py
```

> 如果用 Anaconda `yolov8` 环境而非 `.venv`：
>
> ```bat
> set RPPG_URL=http://192.168.20.29:5050
> set MOONFALL_WS=ws://127.0.0.1:8001/ws
> C:\Users\<用户名>\.conda\envs\yolov8\python.exe rppg_bridge.py
> ```

`rppg_bridge.py` 会每秒轮询 rPPG Server 的 `/stats` 接口，将 4 位玩家的心率自动映射后推送到后端：

| rPPG player | Moonfall player | Faction |
|---|---|---|
| player_1 | p1 | pa (A) |
| player_2 | p2 | pb (B) |
| player_3 | p3 | pc (C) |
| player_4 | p4 | pd (D) |

启动后终端会持续打印：

```text
[bridge] rPPG  → http://192.168.20.29:5050/stats
[bridge] push  → ws://127.0.0.1:8001/ws
[bridge] connected to moonfall
[bridge] player_1 → p1 hr=76 bpm
[bridge] player_2 → p2 hr=93 bpm
[bridge] moon_rage=0.12
```

> **注意**：`MOONFALL_WS` 的端口必须与后端实际监听端口一致。后端跑在 8001 就写 8001。
>
> **进程稳定性**：如果前端心率数字停止更新，先检查后端 `/api/state` 里的 `heart_rate` 是否变化。如果后端也不变，说明 `rppg_bridge.py` 进程已退出，需要重新启动。详见 `docs/rppg_integration.md`。

### 数据格式

真实心率设备每秒发送：

```json
{
  "topic": "sensor.hr",
  "source": "hr_p1",
  "timestamp": 1720000000.0,
  "payload": {
    "player_id": "p1",
    "heart_rate": 105
  }
}
```

Runtime 会计算：

```python
stress = max(0.0, min(1.0, (heart_rate - baseline_hr) / 40.0))
moon_rage = average(all_player_stress)
```

然后广播 `state.world`。前端底部 4 个玩家状态条会实时显示心率 BPM 和波形动画。

### rPPG 视频画面

rPPG Server 提供 MJPEG 实时视频流，可在浏览器中直接打开查看摄像头画面和人脸检测框：

```text
http://192.168.20.29:5050/video_feed
```

或打开 rPPG 控制台 `http://192.168.20.29:5050` 进行摄像头开启、玩家注册等操作。

## 6. 语音同学怎么连

运行命令行语音测试：

```bat
cd backend
.venv\Scripts\activate
set MOONFALL_WS_URL=ws://192.168.1.23:8000/ws
set PLAYER_ID=p1
python clients\voice_client_example.py
```

输入：

```text
让一号车绕开月尘去东北资源区采集燃料
```

发送格式：

```json
{
  "topic": "input.voice",
  "source": "voice_test",
  "timestamp": 1720000000.0,
  "payload": {
    "player_id": "p1",
    "text": "让一号车绕开月尘去东北资源区采集燃料"
  }
}
```

Runtime 会广播：

- `cmd.robot`
- `state.event`

没有 LLM API Key 时，Runtime 自动使用关键词规则兜底。接上 DeepSeek 或 NVIDIA NIM 后，语音解析会优先走 LLM。

## 7. 常见连接问题

问题：我在自己电脑上连 `ws://localhost:8000/ws` 连不上。

原因：`localhost` 是你自己的电脑，不是后端电脑。

改成：

```text
ws://后端电脑IPv4:8000/ws
```

问题：能打开 `/api/health`，但 WebSocket 失败。

检查：

- 地址是不是 `ws://.../ws`，不是 `http://.../ws`。
- 防火墙是否允许 8000 端口。
- 后端是否用 `--host 0.0.0.0` 启动。

问题：后端返回 `INVALID_MESSAGE`。

检查消息是不是有四个字段：

- `topic`
- `source`
- `timestamp`
- `payload`

问题：后端返回 `UNKNOWN_TOPIC`。

检查 topic 是否写错。可用 topic 见 `docs/websocket_topics.md`。
