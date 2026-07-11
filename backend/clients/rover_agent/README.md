# rover_agent —— 视觉定位 + 小车导航

俯拍相机解出全场坐标 → A* 绕障规划 → UDP 闭环驱动 Deskbot 小车。
完整技术说明与接口见 `docs/rover_navigation.md`；历史设计与任务分解见
`docs/superpowers/plans/2026-07-10-vision-nav-rover-agent.md`。

## 现场部署清单

1. **组网**：电脑与所有小车连同一个热点；在热点管理里给每台车**固定 DHCP 租约**（车的 IP 显示在车载 OLED 上），填进 `params.yaml` 的 `robots.<id>.ip`。
2. **贴标记**（字典和 ID 以 `params.yaml` 为准，打印后平整粘贴）：
   - 桌面四角各一张；`auto_assign=true` 时系统自动分配左下原点、右下、右上、左上；
   - 每台车顶一张：标记 0/1/2/3 固定对应 `car_id` r0/r1/r2/r3，**标记上边缘朝车头**。
3. **相机**：架在桌面正上方，画面完整覆盖 4 个角标记；固定牢靠（标定只做一次，相机被碰后在 viz 里按 `c` 重标定）。
4. **场地初始化（一站式）**：跑 `setup_field`——绑新车、测贴码方向、鼠标圈约 5 个固定目标或按 `a` 输入 `id x_cm y_cm radius_cm`，按 `w` 落盘。
5. **依赖**：`pip install -r requirements.txt`。

## 常用命令（都在 repo 根目录执行；带相机的须在自己终端跑）

```bash
# M0 通信冒烟：车走-停-转，验证协议与看门狗
PYTHONPATH=backend/clients python -m rover_agent.smoke_drive <车IP>

# M1 定位调试：实景画面叠加厘米坐标、障碍、路径和轨迹
PYTHONPATH=backend/clients python -m rover_agent.viz --camera 0

# 场地初始化：绑车 + 测贴码方向 + 鼠标圈固定目标 → 落盘 params.yaml
PYTHONPATH=backend/clients python -m rover_agent.setup_field --camera 0
# 键位: b 绑新车 | a 输入固定目标 | 鼠标圈选 | u 撤销 | o 清空 | w 写回

# r0 直行标定：自动测 speed 5/10，各跑 3 次并输出中位数
PYTHONPATH=backend/clients python -m rover_agent.calibrate_straight \
    --camera 0 --car r0

# r0 转向标定：25% 功率左右各转 3 次并输出中位数
PYTHONPATH=backend/clients python -m rover_agent.calibrate_turn \
    --camera 0 --car r0

# M2/M3 主程序：CLI 下发厘米目标；--viz 开实景叠加；--bridge 接 Runtime
PYTHONPATH=backend/clients python -m rover_agent.agent --camera 0 --viz \
    --config docs/schema/examples/moonfall_mvp.game.json \
    [--bridge ws://127.0.0.1:8000/ws]
# CLI: "r0 30 40 6"=去坐标 | "r0 @base 3"=去固定目标 | p r0=查位置
```

## 上层接入：fleet（一个 Agent 握一辆车）

初始化落盘后，上层不用管障碍/路径/丢码，一辆车一个句柄，说去哪就去哪：

```python
from rover_agent.fleet import Fleet

with Fleet(camera=0) as fleet:        # 拉起视觉 + 控制线程
    fleet.wait_ready()                # 等标定完成、各车位姿可见
    r0 = fleet.car("r0")
    print(fleet.get_landmarks())       # 开场手动画入的固定目标
    fleet.replace_transient_obstacles([
        {"id": "dust-1", "shape": "circle",
         "x_cm": 20, "y_cm": 20, "radius_cm": 2},
    ])                                # 只在内存中，不写 params.yaml
    ok = r0.goto_landmark("base", speed=3, wait=True)
    fleet.clear_transient_obstacles() # 下一回合显式清空
    print(fleet.get_position("r0"))      # 返回内容含 car_id
    r0.stop()                            # 只停这一辆
```

引擎走 WebSocket 时用 `--bridge`（bridge.py），进程内 Python 直接用 Fleet。
两种入口操作的是同一组 `Rover` 对象：共享 `FieldTracker` 提供的场地位姿，
每辆车独立持有路线、速度、控制状态与 UDP 驱动。

## params.yaml 调参说明

| 键 | 含义 | 何时动它 |
| --- | --- | --- |
| `robots.<id>.ip / marker_id` | 车的 IP 与车顶标记号 | 现场必填 |
| `table.width_cm / height_cm / cell_cm` | `80 / 60 / 1` 厘米地图 | 棋盘尺寸变化时修改 |
| `landmarks` | 开场手动画入的固定目标 | 由 `setup_field` 写入并长期保存 |
| `planner.robot_radius_cm` | 障碍规划外扩距离，当前 2cm | 车蹭到圆柱 → 调大 |
| `vision.ema_alpha` | 位姿平滑，1=不平滑 | 坐标抖 → 调小（如 0.3） |
| `vision.stale_sec` | 位姿过期即刹车 | 检测帧率低 → 适当放大 |
| `vision.command_pose_wait_sec` | 发令瞬间丢码时等待恢复，默认 2 秒 | 现场识别闪烁时保留默认值 |
| `control.correction_period_ms` | 用最新位姿重算轮速的周期 | 默认 500ms；调小更灵敏，调大更平滑 |
| `drive.keepalive_period_ms` | 重发最近轮速的周期 | 默认 250ms；现场实测 80ms 会拥塞弱链路 |
| `drive.command_ttl_ms` | 控制线程不再刷新后，旧轮速还能保持多久 | 默认 1000ms；到期后保活线程改发停车 |
| `control.min/max_cruise_pct` | speed 1/10 的直行轮速 | 低速不动 → 提高 min；整体过快 → 降 max |
| `control.min/max_turn_pct` | speed 1/10 的原地转轮速 | 低速转不动或转向过猛时调整 |
| `control.k_heading` | 直行航向修正增益 | 走S形 → 调小；跑偏收敛慢 → 调大 |
| `control.turn_enter_rad / turn_exit_rad` | 进入/退出原地转的两个阈值 | 频繁反转 → 拉大两阈值间距 |
| `control.arrive_tol_cm` | 终点允许误差，默认 2cm | 支持最短 5cm 移动 |
| `control.landmark_gap_min/max_cm` | 到固定目标的最终车体间隙，默认 1–2cm | 贴得过近或不够近时调整 |
| `planner.inflate_cells` | zone 类障碍（游戏配置）的膨胀圈数 | 蹭 zone 障碍 → 加 1 |
| `bridge.theta_unit` | 上行 theta 单位 rad/deg | 按与引擎确认的口径改 |

## 常见故障对照

| 现象 | 排查 |
| --- | --- |
| 车完全不动 | 电脑与车是否同热点；IP 对不对（看 OLED）；`smoke_drive` 能不能动 |
| 车动一下就停 | 查 250ms 保活是否运行、固件是否为 1000ms 看门狗、网络是否有长阻塞 |
| viz 一直 CALIBRATING | 4 个角标记必须同时可见：查遮挡、反光、画面范围 |
| 坐标跳变/漂移 | 角标记被局部遮挡；相机被碰过 → 按 `c` 重标定 |
| θ 差 90°/180° | 车顶标记贴的方向不对（上边缘要朝车头） |
| x 或 y 方向反了 | 四角标记 id 顺序贴错（0 必须在左下，逆时针 0→1→2→3） |
| 到点后来回蹭 | 短距离命令使用 speed 1–3；核对 `arrive_tol_cm=2` |
| 车蹭到圆柱障碍 | 核对实景红圈；或调大 `robot_radius_cm` |
| 明明有路却报不可达 | 膨胀后通道被封死 → 减小安全半径或挪开障碍 |

`calibrate_straight` 只启动指定车辆，不会连接其他未开机车辆。每次按回车
前把车放回无遮挡直线路段，车头前方至少留 25cm；脚本使用 150ms UDP
保活以适配当前 300ms 固件看门狗。测试结束后，把终端最后两行 median
结果发给控制器调参人员即可。

`calibrate_turn` 同样只启动指定车辆。每次按回车前把车放在地图中间，
周围至少留 15cm；默认以 25% 功率执行 0.3s 脉冲，左转、右转各 3 次，
输出转角、角速度和中心位移的中位数。

坐标目标若落入固定目标的规划占用格，会自动转换为靠近该固定目标的任务；
临时障碍只参与绕行，不会成为目的地。

## 与 Runtime 的契约（M3）

- 上行 `perception.pose`：含 `car_id`，`x/y` 为厘米坐标；
- 下行 `cmd.robot`：用 `car_id` 指定 r0..r3，`x/y` 为厘米坐标，也可用 `landmark_id`；
- `cmd.rover_map`：`get_landmarks`、`replace_transient`、`clear_transient`；
- 到达固定目标时，`state.event` 附带 `landmark_id` 与 `landmark_gap_cm`。

## 测试

```bash
python -m unittest discover -s tests -p 'test_rover_*.py' -v
```

全部纯软件可跑：视觉链路用合成 ArUco 图像验证，控制律用理想差速模型仿真收敛，UDP 驱动用本地回环端口验证（含 clamp、保活、退出停车）。
