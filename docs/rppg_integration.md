# rPPG 心率接入说明

本文档说明如何将多人 rPPG 心率监测系统接入 Moonfall Runtime，实现玩家心率驱动游戏月怒值（moon_rage）的实时联动。

## 系统架构

```
Insta360 摄像头 (USB)
        │
        ▼
  rPPG Server (DGX @ :5050)
  ├── YOLO5Face 人脸检测
  ├── MobileNetV2 身份识别
  └── POS/CHROM 等非监督心率算法
        │
        │  GET /stats  每秒轮询
        ▼
  rppg_bridge.py  (可在任意局域网机器上运行)
        │
        │  WebSocket  topic: sensor.hr
        ▼
  Moonfall Runtime (:8000)
  ├── HeartRateService.update_player_hr()
  ├── 计算 stress = (hr - baseline) / 40
  └── 计算 moon_rage = avg(stress)
        │
        ▼
  前端 / 机器人 / 机械臂
```

## 依赖

`backend/requirements.txt` 已包含所需依赖，无需额外安装：

```
websockets>=12.0
aiohttp>=3.9.0
```

## 部署步骤

### 1. 启动 rPPG Server（在 DGX 上）

```bash
cd ~/rPPG
MPLCONFIGDIR=/tmp/mpl nohup python3 demo_app/app.py > /tmp/rppg.log 2>&1 &
```

确认启动成功：

```bash
tail -5 /tmp/rppg.log
# 应看到: Running on http://0.0.0.0:5050
```

### 2. 注册玩家

在浏览器打开 `http://<DGX_IP>:5050`：

1. Camera Index 填 `0` → 点 **Open Camera**
2. 上传包含所有玩家的合影 → 点 **Register Players**
3. 系统会从左到右自动绑定 `player_1, player_2...`，顶部一行展示每位玩家的参考头像

### 3. 启动 Moonfall Backend（在本机）

#### 方式一：使用项目自带 venv（Python 3.11+）

```bash
cd backend
./run_server.sh
# 看到 Application startup complete 后进行下一步
```

#### 方式二：使用 Anaconda yolov8 环境（Python 3.9 + ultralytics）

如果需要同时使用 YOLOv8 / ultralytics（例如视觉检测场景），可以用 Anaconda 的 `yolov8` 环境运行后端：

```bash
cd backend
# 用 yolov8 环境的 python 启动（路径按实际 conda 安装位置调整）
C:\Users\<用户名>\.conda\envs\yolov8\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

安装依赖（首次）：

```bash
C:\Users\<用户名>\.conda\envs\yolov8\python.exe -m pip install -r requirements.txt
```

> **Python 3.9 兼容性注意**：项目代码使用了 `str | None` 等 Python 3.10+ 语法，在 Python 3.9 环境下需额外安装 `eval_type_backport` 包，否则 pydantic 模型加载会报 `TypeError: unsupported operand type(s) for |`：
>
> ```bash
> C:\Users\<用户名>\.conda\envs\yolov8\python.exe -m pip install eval_type_backport
> ```

#### 端口选择

默认端口 `8000`。如果 8000 已被其他服务占用（例如返回的不是 Moonfall Runtime 页面），改用 `8001` 或其他空闲端口：

```bash
# 方式一：命令行直接指定
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# 方式二：通过环境变量
set RUNTIME_PORT=8001
backend\run_server.bat
```

> 如果改了后端端口，**前端 `frontend/src/config.js` 也要同步修改**，否则前端连不上 WebSocket 会自动降级到 mock 假数据：
>
> ```js
> // frontend/src/config.js
> export const HOST = params.get('host') || '127.0.0.1:8001'
> ```

### 4. 启动桥接脚本（在本机，另开一个终端）

使用项目 venv：

```bash
cd backend
RPPG_URL=http://<DGX_IP>:5050 \
MOONFALL_WS=ws://127.0.0.1:8000/ws \
python3 rppg_bridge.py
```

使用 Anaconda yolov8 环境（Windows）：

```bat
cd backend
set RPPG_URL=http://192.168.20.29:5050
set MOONFALL_WS=ws://127.0.0.1:8001/ws
set POLL_INTERVAL=1.0
C:\Users\<用户名>\.conda\envs\yolov8\python.exe rppg_bridge.py
```

> **注意**：`MOONFALL_WS` 的端口必须与后端实际监听端口一致。如果后端跑在 8001，这里也要写 8001。

> **进程稳定性**：`rppg_bridge.py` 在网络波动或后端重启时可能退出。如果发现前端心率数字不再变化，先检查后端 `/api/state` 里的 `heart_rate` 是否更新——如果后端也不更新，说明 bridge 进程已停止，需要重新启动。

启动后终端会持续打印心率推送情况：

```
[bridge] rPPG  → http://192.168.20.29:5050/stats
[bridge] push  → ws://127.0.0.1:8000/ws
[bridge] connected to moonfall
[bridge] player_1 → p1 hr=72 bpm
[bridge] player_2 → p2 hr=85 bpm
[bridge] moon_rage=0.23
```

### 5. 验证

#### 后端状态验证

```bash
curl http://127.0.0.1:8000/api/state | python3 -m json.tool | grep -E 'heart_rate|stress|moon_rage'
```

预期输出：

```json
"heart_rate": 72,
"stress": 0.30,
"moon_rage": 0.23
```

如果后端跑在 8001 端口：

```bash
curl http://127.0.0.1:8001/api/state | python3 -m json.tool | grep -E 'heart_rate|stress|moon_rage'
```

#### 心率是否实时更新

隔 3 秒请求两次，对比 `heart_rate` 值是否变化：

```bash
# 第 1 次
curl -s http://127.0.0.1:8001/api/state | grep -o '"heart_rate":[0-9]*'
# 等 3 秒
sleep 3
# 第 2 次
curl -s http://127.0.0.1:8001/api/state | grep -o '"heart_rate":[0-9]*'
```

如果两次值完全相同且 rPPG Server 端数据在变化，说明 `rppg_bridge.py` 进程可能已停止，需要重启。

#### rPPG Server 直连验证

直接请求 DGX 上的 rPPG Server，确认数据源正常：

```bash
curl http://192.168.20.29:5050/stats | python3 -m json.tool
```

#### 前端验证

打开 `http://127.0.0.1:5173`（Vite dev server），底部 4 个玩家状态条应实时显示心率 BPM 和波形动画。玩家映射关系：

| rPPG player | Moonfall player | Faction | 前端显示 |
|---|---|---|---|
| player_1 | p1 | pa | A |
| player_2 | p2 | pb | B |
| player_3 | p3 | pc | C |
| player_4 | p4 | pd | D |

如果前端显示 `--` 而非数字，检查：
1. `frontend/src/config.js` 里的端口是否与后端一致。
2. 浏览器控制台是否有 WebSocket 连接错误。
3. 后端 `/api/state` 是否返回了 `heart_rate` 字段。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RPPG_URL` | `http://192.168.20.29:5050` | rPPG Server 地址 |
| `MOONFALL_WS` | `ws://127.0.0.1:8000/ws` | Moonfall WebSocket 地址 |
| `POLL_INTERVAL` | `1.0` | 轮询间隔（秒） |

也可以写在 `.env` 文件里：

```env
RPPG_URL=http://192.168.20.29:5050
MOONFALL_WS=ws://127.0.0.1:8000/ws
POLL_INTERVAL=1.0
```

## Player ID 映射

rPPG 按参考照片从左到右排序，绑定 `player_1, player_2...`；moonfall 使用 `p1, p2...`。

映射关系在 `rppg_bridge.py` 第 30 行：

```python
PLAYER_MAP = {
    "player_1": "p1",
    "player_2": "p2",
    "player_3": "p3",
    "player_4": "p4",
}
```

按实际座位顺序调整。

## WebSocket 消息格式

桥接脚本每秒向 moonfall 推送一条 `sensor.hr` 消息：

```json
{
  "topic": "sensor.hr",
  "source": "hr_p1",
  "timestamp": 1720000000.0,
  "payload": {
    "player_id": "p1",
    "heart_rate": 72
  }
}
```

moonfall 收到后自动计算：

```
stress     = max(0, min(1, (heart_rate - baseline_hr) / 40))
moon_rage  = avg(stress) across all players
```

`baseline_hr` 默认 80 bpm，可在 `backend/configs/moonfall.yaml` 调整。

## 注意事项

- **心率缓冲**：rPPG 需要约 10 秒（300 帧 @ 30fps）积累足够数据后才能输出心率。游戏开始前建议提前 15 秒启动摄像头。
- **玩家离开画面**：桥接脚本会跳过超过 10 秒未更新的心率，moonfall 侧该玩家的 `stress` 维持最后一次有效值。
- **相机旋转**：rPPG 使用人脸特征向量（MobileNetV2）而非坐标匹配，支持摄像头旋转后仍能正确识别玩家身份。
- **推流延迟**：端到端延迟约 10–12 秒（10 秒缓冲 + 1 秒轮询 + WebSocket 推送）。
- **方法选择**：默认使用 POS 算法。光照变化较大时可在 rPPG 控制台切换为 CHROM，效果更稳定。
- **bridge 进程稳定性**：`rppg_bridge.py` 是一个常驻轮询脚本，在网络中断或后端重启时会自动重试（3 秒间隔），但如果后端长时间不可用可能导致进程退出。建议通过 `scripts/run_fake_demo.bat` 或进程管理工具（如 `pm2`、`supervisor`）守护。如果前端心率停止更新，优先检查 bridge 进程是否存活。
- **端口一致性**：如果后端使用了非默认端口（如 8001），必须确保 `rppg_bridge.py` 的 `MOONFALL_WS` 和前端 `config.js` 的 `HOST` 都指向同一端口，否则数据链路会断开。
- **视频画面**：rPPG Server 提供 MJPEG 实时视频流 `GET /video_feed`，可在浏览器中直接打开查看摄像头画面和人脸检测框。当前前端面板未嵌入该视频流，如需同时查看画面和游戏状态，可单独打开 `http://<DGX_IP>:5050/video_feed`。

## rPPG Server API

| 端点 | 说明 |
|------|------|
| `GET /stats` | 返回所有玩家当前心率、BVP 信号、缓冲进度 |
| `POST /register` | 上传参考照片注册玩家 |
| `POST /open_camera` | 打开摄像头 |
| `POST /settings` | 修改 rPPG 方法、相似度阈值、窗口大小 |
| `GET /video_feed` | MJPEG 实时视频流 |

`/stats` 响应示例：

```json
{
  "player_1": {
    "hr": 72.3,
    "bvp": [0.12, -0.05, ...],
    "updated_at": 1720000000.0,
    "fill": 1.0,
    "computing": false
  }
}
```
