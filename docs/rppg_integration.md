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

```bash
cd backend
./run_server.sh
# 看到 Application startup complete 后进行下一步
```

### 4. 启动桥接脚本（在本机，另开一个终端）

```bash
cd backend
RPPG_URL=http://<DGX_IP>:5050 \
MOONFALL_WS=ws://127.0.0.1:8000/ws \
python3 rppg_bridge.py
```

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

```bash
curl http://127.0.0.1:8000/api/state | python3 -m json.tool | grep -E 'heart_rate|stress|moon_rage'
```

预期输出：

```json
"heart_rate": 72,
"stress": 0.30,
"moon_rage": 0.23
```

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
