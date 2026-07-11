"""用俯拍视觉自动测量小车 speed=5/10 的直行速度与漂移。

每次测试前，把指定小车放在无遮挡的直线路段，车头前方至少留 25cm，
然后在终端按回车。脚本自动采样静止位姿、发送直行脉冲、停车并再次
采样，最后输出每档三次结果及中位数。

用法（repo 根目录）::

    PYTHONPATH=backend/clients ../venv/bin/python \
      -m rover_agent.calibrate_straight --camera 0 --car r0
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
import statistics
import time

from rover_agent.controller import cruise_pct_for_speed
from rover_agent.drive import RoverDrive
from rover_agent.field_tracker import FieldTracker
from rover_agent.geometry import Pose
from rover_agent.init_direction import load_params


@dataclass(frozen=True)
class TrialMeasurement:
    distance_cm: float
    speed_cm_s: float
    motion_drift_deg: float
    heading_change_deg: float
    lateral_per_20_cm: float


def _norm_angle(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def average_pose(poses) -> Pose:
    values = list(poses)
    if not values:
        raise ValueError("至少需要一张位姿")
    count = len(values)
    theta = math.atan2(
        sum(math.sin(p.theta) for p in values) / count,
        sum(math.cos(p.theta) for p in values) / count,
    )
    return Pose(
        sum(p.x for p in values) / count,
        sum(p.y for p in values) / count,
        theta,
        max(p.ts for p in values),
    )


def summarize_trial(start: Pose, end: Pose,
                    pulse_sec: float) -> TrialMeasurement:
    if pulse_sec <= 0:
        raise ValueError("pulse_sec 必须大于 0")
    dx, dy = end.x - start.x, end.y - start.y
    distance = math.hypot(dx, dy)
    if distance <= 0:
        raise ValueError("未测得有效位移")
    motion_heading = math.atan2(dy, dx)
    drift = math.degrees(_norm_angle(motion_heading - start.theta))
    heading_change = math.degrees(_norm_angle(end.theta - start.theta))
    lateral = -dx * math.sin(start.theta) + dy * math.cos(start.theta)
    return TrialMeasurement(
        distance_cm=distance,
        speed_cm_s=distance / pulse_sec,
        motion_drift_deg=drift,
        heading_change_deg=heading_change,
        lateral_per_20_cm=lateral / distance * 20.0,
    )


def median_measurement(values) -> TrialMeasurement:
    trials = list(values)
    if not trials:
        raise ValueError("至少需要一次测量")
    fields = TrialMeasurement.__dataclass_fields__
    medians = {
        name: statistics.median(getattr(item, name) for item in trials)
        for name in fields
    }
    return TrialMeasurement(**medians)


def forward_clearance_cm(pose: Pose, width_cm: float, height_cm: float,
                         margin_cm: float = 5.0) -> float:
    """沿车头射线计算到棋盘内缩边界的距离。"""
    xmin, xmax = margin_cm, float(width_cm) - margin_cm
    ymin, ymax = margin_cm, float(height_cm) - margin_cm
    if not (xmin <= pose.x <= xmax and ymin <= pose.y <= ymax):
        return 0.0
    dx, dy = math.cos(pose.theta), math.sin(pose.theta)
    candidates = []
    if dx > 1e-9:
        candidates.append((xmax - pose.x) / dx)
    elif dx < -1e-9:
        candidates.append((xmin - pose.x) / dx)
    if dy > 1e-9:
        candidates.append((ymax - pose.y) / dy)
    elif dy < -1e-9:
        candidates.append((ymin - pose.y) / dy)
    positive = [value for value in candidates if value >= 0]
    return min(positive) if positive else 0.0


def collect_poses(field: FieldTracker, car_id: str, seconds: float,
                  min_samples: int = 3) -> list[Pose]:
    deadline = time.monotonic() + seconds
    poses: list[Pose] = []
    last_ts = None
    while time.monotonic() < deadline:
        pose = field.get_pose(car_id)
        if pose is not None and pose.ts != last_ts:
            poses.append(pose)
            last_ts = pose.ts
        time.sleep(0.02)
    if len(poses) < min_samples:
        raise RuntimeError(
            f"{car_id} 只采到 {len(poses)} 张新位姿，至少需要 {min_samples} 张")
    return poses


def _print_measurement(prefix: str, result: TrialMeasurement) -> None:
    print(
        f"{prefix} 位移={result.distance_cm:.2f}cm "
        f"估算速度={result.speed_cm_s:.2f}cm/s "
        f"运动偏向={result.motion_drift_deg:+.1f}° "
        f"车头变化={result.heading_change_deg:+.1f}° "
        f"每20cm横偏={result.lateral_per_20_cm:+.2f}cm"
    )


def _prompt_safe_pose(field: FieldTracker, car_id: str, params: dict,
                      minimum_clearance_cm: float) -> Pose:
    while True:
        answer = input(
            f"把 {car_id} 放到空旷直线路段，车头前方至少 "
            f"{minimum_clearance_cm:.0f}cm；回车开始，q 退出: "
        ).strip().lower()
        if answer in {"q", "quit"}:
            raise KeyboardInterrupt
        pose = field.get_pose(car_id)
        if pose is None:
            print(f"[calibrate] 当前看不到 {car_id}，调整标记后重试")
            continue
        clearance = forward_clearance_cm(
            pose,
            params["table"]["width_cm"],
            params["table"]["height_cm"],
        )
        print(
            f"[calibrate] 起点=({pose.x:.1f},{pose.y:.1f})cm "
            f"方向={math.degrees(pose.theta):.0f}° "
            f"前方边界余量={clearance:.1f}cm"
        )
        if clearance < minimum_clearance_cm:
            print("[calibrate] 前方空间不足，请换方向或挪到更空的位置")
            continue
        return pose


def main() -> int:
    parser = argparse.ArgumentParser(description="自动测量 speed 5/10 直行速度")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--car", default="r0")
    parser.add_argument("--params", default=None)
    parser.add_argument("--speeds", type=int, nargs="+", default=[5, 10])
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--pulse-sec", type=float, default=0.8)
    parser.add_argument("--keepalive-ms", type=int, default=150)
    parser.add_argument("--minimum-clearance-cm", type=float, default=25)
    args = parser.parse_args()

    if args.trials < 1 or args.pulse_sec <= 0:
        parser.error("--trials 和 --pulse-sec 必须大于 0")
    params, _ = load_params(args.params)
    if args.car not in params["robots"]:
        parser.error(f"未知车辆 {args.car}: {sorted(params['robots'])}")
    for speed in args.speeds:
        cruise_pct_for_speed(params["control"], speed)

    field = FieldTracker(params, camera=args.camera)
    robot_config = params["robots"][args.car]
    drive = None
    results: dict[int, list[TrialMeasurement]] = {
        speed: [] for speed in args.speeds
    }
    try:
        field.start()
        print("[calibrate] 等待四角标定和车辆位姿…")
        if not field.wait_ready([args.car], timeout=30):
            print("[calibrate] 30s 内未就绪，请检查四角标记和车顶标记")
            return 2
        drive = RoverDrive(
            robot_config["ip"],
            period_ms=args.keepalive_ms,
            command_ttl_ms=max(
                int(params["drive"].get("command_ttl_ms", 1000)),
                int((args.pulse_sec + 0.5) * 1000),
            ),
            reverse=bool(robot_config.get("reverse", False)),
        )
        print(
            f"[calibrate] {args.car}@{robot_config['ip']} 已就绪；"
            f"测试速度={args.speeds}，每档 {args.trials} 次，"
            f"脉冲 {args.pulse_sec:.1f}s"
        )
        for speed in args.speeds:
            wheel_pct = cruise_pct_for_speed(params["control"], speed)
            while len(results[speed]) < args.trials:
                trial_no = len(results[speed]) + 1
                _prompt_safe_pose(
                    field, args.car, params, args.minimum_clearance_cm)
                try:
                    before = average_pose(collect_poses(
                        field, args.car, seconds=0.45))
                    print(
                        f"[calibrate] speed={speed} 第{trial_no}/{args.trials}次 "
                        f"轮速=({wheel_pct},{wheel_pct})，开始"
                    )
                    drive.set_wheels(wheel_pct, wheel_pct)
                    time.sleep(args.pulse_sec)
                    drive.stop()
                    time.sleep(0.6)
                    after = average_pose(collect_poses(
                        field, args.car, seconds=0.45))
                    measurement = summarize_trial(
                        before, after, args.pulse_sec)
                    if measurement.distance_cm < 2:
                        raise RuntimeError(
                            f"只移动 {measurement.distance_cm:.1f}cm，"
                            "可能未收到指令或电量不足")
                except RuntimeError as exc:
                    drive.stop()
                    print(f"[calibrate] 本次无效，重新测试：{exc}")
                    continue
                results[speed].append(measurement)
                _print_measurement(
                    f"[result] speed={speed} trial={trial_no}", measurement)

        print("\n=== 请把下面结果发给 Codex ===")
        for speed in args.speeds:
            median = median_measurement(results[speed])
            _print_measurement(f"speed={speed} median", median)
        return 0
    except (EOFError, KeyboardInterrupt):
        print("\n[calibrate] 已停止")
        return 130
    finally:
        if drive is not None:
            drive.stop()
            drive.close()
        field.stop()


if __name__ == "__main__":
    raise SystemExit(main())
