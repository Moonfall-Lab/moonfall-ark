# Insta360 卡牌识别与月球车导航实现说明

## 已实现链路

当前实现将 Insta360 识别到的策略卡转换为 Runtime 中的移动命令；`rover_agent` 保持为独立的视觉定位、规划和 UDP 驱动进程。

```text
Insta360 Link 2C QR 客户端
  -> input.qr_skill
  -> Runtime 白名单校验
  -> QR 技能映射为游戏卡牌语义
  -> 按小车实时位姿选择最近目的地
  -> cmd.robot（厘米坐标 x/y，speed=5）
  -> rover_agent 路径规划与 UDP:8888 轮速驱动
```

所有物理坐标使用场地左下为原点的 `80 cm × 60 cm` 世界坐标系；角度使用弧度。

## QR 识别

`backend/clients/insta360_qr_client.py` 使用 OpenCV QR 解码，并由 `backend/app/services/qr_skill_scanner.py` 提供：

- 卡牌白名单加载；
- 多码/单码解码与备用解码策略；
- 同一卡牌持续出现时只触发一次；离开画面五次观察后可再次触发；
- `input.qr_skill` 消息封套。

Runtime 校验 `qr_text`、`skill_id` 和 `skill_name` 必须与配置中的白名单一致，避免伪造或错误二维码触发移动。

## 当前卡牌与目的地规则

规则位于 `backend/configs/moonfall.yaml` 的 `qr_cards`、`players` 和 `landmarks` 配置段。

| 识别卡牌 | QR skill ID | Runtime 语义 | 目标 |
| --- | --- | --- | --- |
| 采集优先 | `collect_priority` | `collect` | 距该玩家小车最近的普通能源站 |
| 探索遗迹 | `explore_relic` | `explore_ruin` | 距该玩家小车最近的遗迹 |
| 返航结算 | `return_settle` | `return_home` | 已完成语义映射；基地坐标下发待最简回合循环实现 |

当前玩家与车辆固定映射：`p1 -> r0`、`p2 -> r1`、`p3 -> r2`、`p4 -> r3`。

五个物理目的地保存在 Runtime 配置中：

| ID | 类型 | 圆心（cm） |
| --- | --- | --- |
| `obstacle-1` | 能源站 | `(19.22, 52.58)` |
| `obstacle-2` | 遗迹 | `(61.51, 51.09)` |
| `obstacle-3` | 高能能源站 | `(37.37, 29.88)` |
| `obstacle-4` | 遗迹 | `(12.71, 10.16)` |
| `obstacle-5` | 能源站 | `(61.83, 13.90)` |

## 小车接口对齐

`params.yaml` 的 `landmarks` 必须保持空，现场地标不写入小车配置。因此 Runtime 不能下发 `landmark_id=obstacle-*`；那会使 rover_agent 报“未知固定目标”。

当前 Runtime 改为下发目标圆心的直接厘米坐标：

```json
{
  "topic": "cmd.robot",
  "source": "runtime",
  "payload": {
    "command_id": "uuid",
    "car_id": "r0",
    "robot_id": "r0",
    "action": "move_to",
    "x": 19.22,
    "y": 52.58,
    "speed": 5
  }
}
```

Runtime 也已接收小车上行消息：

- `perception.pose`：用厘米坐标和弧度更新 `r0..r3` 的实时位姿；
- `state.event`：接受 `robot_arrived` 与 `robot_unreachable`，更新状态并转播；
- `input.qr_skill`：校验 QR 卡牌并生成识别事件与移动命令。

## 启动与测试

启动 Runtime：

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

启动小车 Agent（场地俯视相机示例为索引 0）：

```powershell
cd <repo-root>
$env:PYTHONPATH = "$PWD\backend\clients"
python -m rover_agent.agent --camera 0 --bridge ws://127.0.0.1:8000/ws --viz
```

启动 Insta360 QR 客户端（当前现场示例为索引 1）：

```powershell
cd backend
python clients/insta360_qr_client.py --camera-index 1 --ws-url ws://127.0.0.1:8000/ws --no-preview
```

软件契约测试：

```powershell
python -m unittest tests.test_min_runtime_contract -v
```

该测试覆盖 r0 位姿上行、到达事件、QR 校验，以及“采集优先”向最近能源站下发直接 `x/y` 坐标。

## 当前现场阻塞项

规划、视觉标定和 QR 识别均已验证。当前实车不动的原因是网络不可达：运行 agent 的环境只有 `192.168.197.133/24` 接口，而小车配置为 `10.151.217.122` / `10.151.217.220`。网络设备返回“目标主机不可达”，因此 UDP `8888` 控制命令无法到达小车。

在恢复实测前，需让运行 agent 的机器或虚拟机桥接到小车所在网络，并确认：

```powershell
ping 10.151.217.122
ping 10.151.217.220
```

能够收到来自各小车 IP 的回复。网络恢复后，先以低速短距离命令验证电机，再进行卡牌闭环测试。
