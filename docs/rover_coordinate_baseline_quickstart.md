# 小车坐标导航：换电脑快速启动

本文只覆盖已经验证成功的单一功能：打开俯拍棋盘摄像头，识别棋盘和小车位置，然后在命令行输入“小车、目标厘米坐标、速度”，让小车自动规划路径并移动。

本分支不启动卡牌摄像头、卡牌识别程序或完整游戏流程。

## 固定配置

分支：`test/rover-coordinate-baseline`

- 棋盘摄像头：OpenCV **0 号摄像头**，启动参数固定为 `--camera 0`
- 棋盘：`80 × 60cm`
- 路径规划网格：`1cm`
- r0：`10.202.241.122`，车顶标记 ID 0
- r1：`10.202.241.220`，车顶标记 ID 1
- 固定障碍物：从 `backend/configs/moonfall.yaml` 读取现有 5 个障碍物
- 其余定位、路径规划和运动控制参数：使用分支内 `backend/clients/rover_agent/params.yaml`，无需修改

## 新电脑第一次准备

切到这个分支本身还不够。每台新电脑第一次需要完成下面四件事：拉取代码、创建 Python 环境、安装依赖、授权摄像头。完成后，后续运行只需要一行命令。

### 1. 获取分支

还没有仓库时：

```bash
git clone https://github.com/Moonfall-Lab/moonfall-ark.git
cd moonfall-ark
git fetch origin
git switch --track origin/test/rover-coordinate-baseline
```

已经克隆仓库时，在仓库根目录执行：

```bash
git fetch origin
git switch --track origin/test/rover-coordinate-baseline
```

如果这台电脑以前已经创建过同名本地分支，则最后一行改成：

```bash
git switch test/rover-coordinate-baseline
```

### 2. 创建环境并安装依赖

需要 Python 3.11 或更新版本。在仓库根目录执行：

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r backend/clients/rover_agent/requirements.txt
```

这一步每台电脑只做一次。以后不要重复创建环境。

### 3. 授权摄像头

在 macOS 的“系统设置 → 隐私与安全性 → 相机”中，允许当前使用的终端程序访问摄像头。相机保持在当前硬件连接方式下，棋盘摄像头使用 **0 号**。

### 4. 连接现场网络

电脑和小车必须连接同一个热点。确认小车 OLED 显示的 IP 与本文“固定配置”一致。

## 日常启动：只运行这一行

以后每次进入仓库根目录，只运行下面这一行：

```bash
PYTHONPATH=backend/clients ./.venv/bin/python -m rover_agent.agent --camera 0 --landmarks-config backend/configs/moonfall.yaml --viz
```

程序会打开棋盘实时画面。保持四个角标记和车顶标记都在画面内。终端出现以下信息后即可操作：

```text
[calib] 自动角分配: ...
[agent] 标定完成
>
```

## 操作小车

坐标单位统一为厘米，速度范围为 0 到 10。

```text
p r0             查看 r0 当前位姿
r0 35 16 5       让 r0 以速度 5 前往 (35cm, 16cm)
r1 60 40 5       让 r1 以速度 5 前往 (60cm, 40cm)
s                所有小车急停
q                停车并退出程序
```

建议第一次先用 `p r0` 确认位置是“新鲜”状态，再下发一段较短、周围没有障碍的路线。

## IP 地址变化时怎么改

小车通过手机热点分配地址，IP 可能变化。以车载 OLED 显示的地址为准，只修改：

`backend/clients/rover_agent/params.yaml`

找到 `robots` 段：

```yaml
robots:
  r0: { ip: "10.202.241.122", marker_id: 0, theta_offset_deg: 0 }
  r1: { ip: "10.202.241.220", marker_id: 1, theta_offset_deg: 0 }
```

只替换对应车辆的 `ip`，不要改变 `marker_id` 或其他参数。保存后退出旧程序，再重新运行上面的一行启动命令。

## 最小故障排查

| 现象 | 处理 |
| --- | --- |
| 没有弹出棋盘画面 | 检查 macOS 相机权限，并确认命令使用 `--camera 0` |
| 一直没有“标定完成” | 调整摄像头，使棋盘四个角标记同时完整可见 |
| `p r0` 显示位姿丢失 | 保证车顶 ID 0 标记完整、无反光、没有被遮挡 |
| 有位姿但小车不动 | 查看 OLED IP；若变化，按上一节修改 `params.yaml` |
| 出现 `No route to host` | 电脑和小车没有处于同一热点，或配置中的 IP 已变化 |
| 提示缺少 `cv2`、`yaml` 等模块 | 重新执行依赖安装命令，并确保启动时使用 `./.venv/bin/python` |

## 换电脑时不能由代码自动完成的部分

代码分支会带上全部地图、障碍物和控制参数，但下面三项属于现场环境，无法随 Git 自动带过去：

1. macOS 对终端的摄像头权限；
2. 电脑与小车连接同一热点；
3. 热点重新分配后的小车 IP。

只要第一次安装完成、相机仍为 0 号、IP 没有变化，之后就是一行命令启动。
