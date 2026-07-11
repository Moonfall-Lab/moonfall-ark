"""用俯拍视觉测量小车最低功率下的左右转向角速度。

默认以 25% 功率分别左转、右转，各执行 3 次 0.3s 脉冲。每次测试前
把车辆放在地图中间、周围留出约 15cm 空间，然后在终端按回车。

用法（repo 根目录）::

    PYTHONPATH=backend/clients ../venv/bin/python \
      -m rover_agent.calibrate_turn --camera 0 --car r0
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
import statistics
import time

from rover_agent.calibrate_straight import average_pose, collect_poses
from rover_agent.drive import RoverDrive
from rover_agent.field_tracker import FieldTracker
from rover_agent.geometry import Pose
from rover_agent.init_direction import load_params


@dataclass(frozen=True)
class TurnMeasurement:
    angle_deg: float
    rate_deg_s: float
    translation_cm: float


def _norm_angle(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def summarize_turn(start: Pose, end: Pose,
                   pulse_sec: float) -> TurnMeasurement:
    if pulse_sec <= 0:
        raise ValueError("pulse_sec 必须大于 0")
    angle = math.degrees(_norm_angle(end.theta - start.theta))
    return TurnMeasurement(
        angle_deg=angle,
        rate_deg_s=angle / pulse_sec,
        translation_cm=math.hypot(end.x - start.x, end.y - start.y),
    )


def median_turn_measurement(values) -> TurnMeasurement:
    trials = list(values)
    if not trials:
        raise ValueError("至少需要一次测量")
    return TurnMeasurement(
        angle_deg=statistics.median(item.angle_deg for item in trials),
        rate_deg_s=statistics.median(item.rate_deg_s for item in trials),
        translation_cm=statistics.median(
            item.translation_cm for item in trials),
    )


def _print_measurement(prefix: str, result: TurnMeasurement) -> None:
    print(
        f"{prefix} 转角={result.angle_deg:+.1f}° "
        f"角速度={result.rate_deg_s:+.1f}°/s "
        f"中心位移={result.translation_cm:.2f}cm"
    )


def _prompt_center_pose(field: FieldTracker, car_id: str, params: dict,
                        margin_cm: float) -> Pose:
    width = float(params["table"]["width_cm"])
    height = float(params["table"]["height_cm"])
    while True:
        answer = input(
            f"把 {car_id} 放到地图中间，周围至少留 {margin_cm:.0f}cm；"
            "回车开始，q 退出: "
        ).strip().lower()
        if answer in {"q", "quit"}:
            raise KeyboardInterrupt
        pose = field.get_pose(car_id)
        if pose is None:
            print(f"[calibrate] 当前看不到 {car_id}，调整标记后重试")
            continue
        if not (margin_cm <= pose.x <= width - margin_cm
                and margin_cm <= pose.y <= height - margin_cm):
            print(
                f"[calibrate] 当前位置=({pose.x:.1f},{pose.y:.1f})cm "
                "离地图边缘太近，请挪到中间"
            )
            continue
        print(
            f"[calibrate] 起点=({pose.x:.1f},{pose.y:.1f})cm "
            f"方向={math.degrees(pose.theta):.0f}°"
        )
        return pose


def main() -> int:
    parser = argparse.ArgumentParser(description="自动测量最低功率左右转向角速度")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--car", default="r0")
    parser.add_argument("--params", default=None)
    parser.add_argument("--power", type=int, default=25)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--pulse-sec", type=float, default=0.3)
    parser.add_argument("--keepalive-ms", type=int, default=150)
    parser.add_argument("--margin-cm", type=float, default=15)
    args = parser.parse_args()

    if not 1 <= args.power <= 100:
        parser.error("--power 必须是 1..100")
    if args.trials < 1 or args.pulse_sec <= 0:
        parser.error("--trials 和 --pulse-sec 必须大于 0")
    params, _ = load_params(args.params)
    if args.car not in params["robots"]:
        parser.error(f"未知车辆 {args.car}: {sorted(params['robots'])}")

    field = FieldTracker(params, camera=args.camera)
    robot_config = params["robots"][args.car]
    drive = None
    directions = {
        "left": (-args.power, args.power),
        "right": (args.power, -args.power),
    }
    results: dict[str, list[TurnMeasurement]] = {
        direction: [] for direction in directions
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
            f"转向功率={args.power}%，左右各 {args.trials} 次，"
            f"脉冲 {args.pulse_sec:.1f}s"
        )
        for direction, wheels in directions.items():
            expected_sign = 1 if direction == "left" else -1
            while len(results[direction]) < args.trials:
                trial_no = len(results[direction]) + 1
                _prompt_center_pose(field, args.car, params, args.margin_cm)
                try:
                    before = average_pose(collect_poses(
                        field, args.car, seconds=0.45))
                    print(
                        f"[calibrate] {direction} 第{trial_no}/{args.trials}次 "
                        f"轮速={wheels}，开始"
                    )
                    drive.set_wheels(*wheels)
                    time.sleep(args.pulse_sec)
                    drive.stop()
                    time.sleep(0.6)
                    after = average_pose(collect_poses(
                        field, args.car, seconds=0.45))
                    measurement = summarize_turn(
                        before, after, args.pulse_sec)
                    if abs(measurement.angle_deg) < 5:
                        raise RuntimeError(
                            f"只转了 {measurement.angle_deg:+.1f}°，"
                            "可能未收到指令或功率不足")
                except RuntimeError as exc:
                    drive.stop()
                    print(f"[calibrate] 本次无效，重新测试：{exc}")
                    continue
                if measurement.angle_deg * expected_sign < 0:
                    print(
                        "[calibrate] ⚠️ 实际转向与预期相反，请记录；"
                        "可能需要检查电机接线/reverse 配置"
                    )
                results[direction].append(measurement)
                _print_measurement(
                    f"[result] {direction} trial={trial_no}", measurement)

        print("\n=== 请把下面结果发给 Codex ===")
        for direction in directions:
            median = median_turn_measurement(results[direction])
            _print_measurement(
                f"power={args.power} {direction} median", median)
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
