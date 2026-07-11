"""两段式运动控制律（纯函数 + 可选滞回状态，完全可离线测试）。

航向误差很大 → 原地转对准；其余 → 直行 + 按误差比例差速修正（画弧）。
原地转向带滞回：误差 > turn_enter_rad 才进入，降到 turn_exit_rad 以下才退出。
必须滞回的原因：车的弱 WiFi 指令链路与视觉平滑会带来明显延迟，
单阈值下原地转必然转过头、误差反号又超阈值、随即反向重转——现场表现为
车在原地来回打转不前进。

车无里程计，闭环收敛依赖视觉位姿的持续反馈。大角度转向另使用
“短脉冲－停车－重新观察”的离散控制，并按左右方向分别标定角速度，
避免网络延迟把连续转向放大成左右振荡。
"""
from __future__ import annotations

from rover_agent.geometry import Pose, dist, heading_error


def _clamp(v: float) -> int:
    return max(-100, min(100, int(round(v))))


def validate_speed_level(speed) -> int:
    """校验对外速度等级。bool 虽是 int 子类，也不能当作速度。"""
    if (isinstance(speed, bool) or not isinstance(speed, int)
            or not 0 <= speed <= 10):
        raise ValueError("speed 必须是 0..10 的整数")
    return speed


def _speed_output(params: dict, level: int, minimum: str, maximum: str,
                  legacy: str) -> float:
    max_value = float(params.get(maximum, params.get(legacy, 0)))
    min_value = float(params.get(minimum, max_value / 10.0))
    return min_value + (level - 1) / 9.0 * (max_value - min_value)


def cruise_pct_for_speed(params: dict, speed: int) -> int:
    """返回速度档在直行且无航向误差时实际使用的量化轮速百分比。"""
    speed = validate_speed_level(speed)
    if speed == 0:
        raise ValueError("speed=0 没有巡航轮速")
    value = _speed_output(
        params, speed, "min_cruise_pct", "max_cruise_pct", "cruise_pct")
    quantum = max(1, int(params.get("wheel_step_pct", 5)))
    return _clamp(round(value / quantum) * quantum)


def turn_pulse_for_error(error_rad: float, motion_model: dict,
                         params: dict) -> tuple[tuple[int, int], float]:
    """把航向误差换算成一次有上限的原地转向脉冲。

    只消除 ``turn_pulse_fraction`` 比例的误差，刻意保留余量给下一次
    视觉观测修正；左右方向使用各自实测角速度，吸收电机/摩擦差异。
    """
    power = int(round(float(motion_model["turn_power_pct"])))
    if not 0 < power <= 100:
        raise ValueError("turn_power_pct 必须在 1..100")
    left = error_rad > 0
    rate_key = "left_turn_deg_s" if left else "right_turn_deg_s"
    rate = abs(float(motion_model[rate_key]))
    if rate <= 0:
        raise ValueError(f"{rate_key} 必须大于 0")
    fraction = float(params.get("turn_pulse_fraction", 0.7))
    minimum = float(params.get("turn_pulse_min_sec", 0.08))
    maximum = float(params.get("turn_pulse_max_sec", 0.35))
    if not 0 < fraction <= 1 or minimum <= 0 or maximum < minimum:
        raise ValueError("转向脉冲参数无效")
    seconds = abs(error_rad) * 180.0 / 3.141592653589793
    seconds = max(minimum, min(maximum, seconds * fraction / rate))
    wheels = (-power, power) if left else (power, -power)
    return wheels, seconds


def step(pose: Pose, waypoints, params: dict, state: dict | None = None,
         speed: int = 10):
    """一拍控制。

    params 取 params.yaml 的 control 段。
    state: 每辆车各自持有的 dict，跨拍记住是否处于原地转向模式（滞回）；
    不传则退化为无记忆单阈值（阈值 = turn_enter_rad）。
    返回 (l, r, remaining_waypoints, done)。
    """
    speed = validate_speed_level(speed)
    if speed == 0:
        raise ValueError("speed=0 是停车命令，不能进入运动控制器")
    wps = list(waypoints)
    # 依次消费已到达的路径点（中间点用 waypoint_tol，末点用更严的 arrive_tol）
    while wps:
        tol = (params["arrive_tol_cm"] if len(wps) == 1
               else params["waypoint_tol_cm"])
        if dist((pose.x, pose.y), wps[0]) <= tol:
            wps.pop(0)
        else:
            break
    if not wps:
        if state is not None:
            state["turning"] = False
        return 0, 0, [], True

    enter = params.get("turn_enter_rad", params.get("turn_thresh_rad", 0.9))
    exit_ = params.get("turn_exit_rad", 0.25)
    err = heading_error(pose, wps[0])
    turning = bool(state and state.get("turning"))
    if turning and abs(err) <= exit_:
        turning = False
    elif not turning and abs(err) > enter:
        turning = True
    if state is not None:
        state["turning"] = turning

    if turning:
        t = _speed_output(params, speed, "min_turn_pct", "max_turn_pct",
                          "turn_pct")
        if err > 0:   # 目标在左侧 → 原地左转（左轮倒转、右轮正转）
            return _clamp(-t), _clamp(t), wps, False
        return _clamp(t), _clamp(-t), wps, False

    c = _speed_output(params, speed, "min_cruise_pct", "max_cruise_pct",
                      "cruise_pct")
    max_c = float(params.get("max_cruise_pct", params.get("cruise_pct", c)))
    k = float(params["k_heading"]) * (c / max_c if max_c else 0)
    # 输出量化到 wheel_step_pct 一档：视觉噪声引起的 ±1~2% 抖动不再改变指令，
    # 配合 drive 层"没变不发"，巡航直线时几乎不产生新包
    q = max(1, int(params.get("wheel_step_pct", 5)))
    l = round((c - k * err) / q) * q
    r = round((c + k * err) / q) * q
    return _clamp(l), _clamp(r), wps, False
