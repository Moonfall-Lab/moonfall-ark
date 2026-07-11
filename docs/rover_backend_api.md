# Rover Agent 后端调用接口

这份文档只描述通用后端与视觉导航小车之间的稳定接口。路径规划、视觉
定位、障碍绕行和 UDP 电机控制都封装在 `rover_agent` 进程内，后端不需要
直接连接摄像头或 ESP32。

## 1. 启动与连接

先启动 Runtime，再在连接摄像头和小车热点的电脑上运行：

```bash
PYTHONPATH=backend/clients python -m rover_agent.agent \
  --camera 0 \
  --bridge ws://127.0.0.1:8000/ws \
  --viz
```

所有 WebSocket 消息使用 Runtime 统一信封：

```json
{
  "topic": "cmd.robot",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {}
}
```

坐标统一为厘米，角度默认使用弧度。车顶标记 `0/1/2/3` 固定对应
`car_id` `r0/r1/r2/r3`；车辆 IP 变化不改变 `car_id`。

## 2. 后端下发移动命令

Topic：`cmd.robot`

```json
{
  "topic": "cmd.robot",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "command_id": "move-001",
    "car_id": "r0",
    "x": 30,
    "y": 20,
    "speed": 5,
    "avoid": []
  }
}
```

字段：

| 字段 | 必填 | 含义 |
| --- | --- | --- |
| `command_id` | 建议 | 后端命令 ID；到达/失败事件原样带回 |
| `car_id` | 是 | `r0..r3`；兼容旧字段 `robot_id` |
| `x/y` | 目标三选一 | 世界坐标，单位厘米 |
| `landmark_id` | 目标三选一 | 前往开场固定目标 |
| `target_zone` | 目标三选一 | 前往游戏配置中的区域中心 |
| `speed` | 否 | 严格整数 `0..10`，默认 `10`；`0` 表示只停指定车 |
| `avoid` | 否 | 额外需要避开的 zone ID 列表 |

目标解析优先级：`landmark_id` → `x/y` → `target_zone`。坐标落在固定
目标的规划占用格时，会自动转换为“靠近该固定目标”，最终停在目标表面
附近；临时障碍只用于绕行，不会成为目的地。

兼容规则：

- 后端迁移期间可继续发送 `robot_id`。
- 如果同时发送 `car_id` 和 `robot_id`，两者必须相同，否则返回
  `error.code = conflicting_car_id`。
- `action: "stop"` 是全场急停；只停一辆车请发送该车 `speed: 0`。

按固定目标移动：

```json
{
  "topic": "cmd.robot",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "command_id": "move-base-001",
    "car_id": "r0",
    "landmark_id": "obstacle-3",
    "speed": 5
  }
}
```

## 3. 后端接收当前位置

Topic：`perception.pose`

Rover Agent 按配置频率持续发送仍然新鲜的位姿：

```json
{
  "topic": "perception.pose",
  "source": "rover_agent",
  "timestamp": 1720000000.0,
  "payload": {
    "car_id": "r0",
    "robot_id": "r0",
    "x": 30.125,
    "y": 20.875,
    "theta": 1.5708,
    "status": "moving"
  }
}
```

- `x/y`：厘米坐标。
- `theta`：默认弧度；可由 `params.yaml > bridge.theta_unit` 改成度。
- `status`：常见值包括 `idle`、`moving`、`approaching`、`arrived`、
  `lost`、`unreachable`、`too_close`。
- `robot_id` 是兼容字段，值始终与 `car_id` 相同。

通用后端应保存每辆车最后一条 `perception.pose`，作为当前位置查询结果。

## 4. 后端接收到达或失败事件

Topic：`state.event`

到达：

```json
{
  "topic": "state.event",
  "source": "rover_agent",
  "timestamp": 1720000000.0,
  "payload": {
    "event_type": "robot_arrived",
    "command_id": "move-001",
    "car_id": "r0",
    "robot_id": "r0",
    "landmark_id": null,
    "landmark_gap_cm": null,
    "message": "r0 到达目标"
  }
}
```

不可达：

```json
{
  "topic": "state.event",
  "source": "rover_agent",
  "timestamp": 1720000000.0,
  "payload": {
    "event_type": "robot_unreachable",
    "command_id": "move-001",
    "car_id": "r0",
    "robot_id": "r0",
    "message": "r0 无法到达目标"
  }
}
```

前往固定目标时，到达事件会额外返回 `landmark_id` 和车体到目标表面的
估算间隙 `landmark_gap_cm`。

## 5. 回合间更新障碍地图

地图只允许在没有车辆执行路线时更新。

查询五个固定目标：

```json
{"topic":"cmd.rover_map","source":"runtime","timestamp":1720000000.0,"payload":{"action":"get_landmarks","command_id":"map-1"}}
```

替换本回合临时障碍：

```json
{
  "topic": "cmd.rover_map",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "action": "replace_transient",
    "command_id": "map-2",
    "obstacles": [
      {
        "id": "dust-1",
        "shape": "circle",
        "x_cm": 42,
        "y_cm": 18,
        "radius_cm": 2.5
      }
    ]
  }
}
```

清空临时障碍：

```json
{"topic":"cmd.rover_map","source":"runtime","timestamp":1720000000.0,"payload":{"action":"clear_transient","command_id":"map-3"}}
```

成功回复 Topic 为 `state.rover_map`。失败回复 Topic 为 `error`，错误码为
`invalid_rover_map_command`。

## 6. Runtime 接入检查表

通用后端需要：

1. 广播 `cmd.robot` 和 `cmd.rover_map`。
2. 接受 `perception.pose`，用 `car_id` 更新世界状态中的车辆位置。
3. 接受 `state.event` 中的 `robot_arrived` / `robot_unreachable`。
4. 接受或记录 `state.rover_map` 与 `error`。
5. 保持单位为厘米、角度为弧度、速度为整数 `0..10`。

当前 Runtime 的消息路由如果尚未处理 `perception.pose` 和设备侧
`state.event`，需要按上面两类 payload 加入路由；Rover Agent 已经按该
契约发送。

## 7. 同进程 Python 接口（可选）

如果通用后端与视觉导航运行在同一 Python 进程，也可以直接使用：

```python
from rover_agent.fleet import Fleet

with Fleet(camera=0) as fleet:
    fleet.wait_ready(robots=["r0"])
    car = fleet.car("r0")
    car.goto(30, 20, speed=5)
    print(fleet.get_position("r0"))
    print(fleet.get_landmarks())
    fleet.replace_transient_obstacles([
        {"id": "dust-1", "shape": "circle",
         "x_cm": 42, "y_cm": 18, "radius_cm": 2.5},
    ])
```

生产部署推荐保持 Rover Agent 为独立进程，通过 WebSocket 接入 Runtime。
