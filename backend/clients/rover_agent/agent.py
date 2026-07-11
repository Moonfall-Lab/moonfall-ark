"""rover_agent 命令行入口：启动 Fleet，并接入 CLI、可视化和消息桥。

用法（repo 根目录）:
    PYTHONPATH=backend/clients python -m rover_agent.agent --camera 0
    PYTHONPATH=backend/clients python -m rover_agent.agent --camera 0 \
        --bridge ws://127.0.0.1:8000/ws --viz

CLI 命令:
    r0 30 40 [speed] 让 r0 去厘米坐标 (30, 40)，速度 0..10，默认 10
    r0 @base [speed]  让 r0 去固定目标 base
    p r0              查询 r0 最后位置
    s                 全场急停
    q                 退出（退出时自动对所有车发停车指令）
"""
from __future__ import annotations

import argparse
import threading

from rover_agent.controller import validate_speed_level
from rover_agent.fleet import Fleet, load_zones  # noqa: F401
from rover_agent.overlay import draw_overlay
from rover_agent.viz import load_params


def parse_cli_command(line: str) -> dict | None:
    """把一行 CLI 输入解析成稳定命令结构；不执行任何硬件动作。"""
    parts = line.strip().split()
    if not parts:
        return None
    if parts[0] in ("q", "quit"):
        if len(parts) != 1:
            raise ValueError("退出命令不接受参数")
        return {"action": "quit"}
    if parts[0] in ("s", "stop"):
        if len(parts) != 1:
            raise ValueError("急停命令不接受参数")
        return {"action": "stop_all"}
    if parts[0] in ("p", "position"):
        if len(parts) != 2:
            raise ValueError("位置查询用法: p <车id>")
        return {"action": "position", "robot_id": parts[1]}
    if len(parts) in (2, 3) and parts[1].startswith("@"):
        landmark_id = parts[1][1:].strip()
        if not landmark_id:
            raise ValueError("固定目标 id 不能为空")
        try:
            speed = int(parts[2]) if len(parts) == 3 else 10
        except ValueError as exc:
            raise ValueError("速度须为 0..10 的整数") from exc
        validate_speed_level(speed)
        return {
            "action": "move_landmark",
            "robot_id": parts[0],
            "landmark_id": landmark_id,
            "speed": speed,
        }
    if len(parts) not in (3, 4):
        raise ValueError(
            "命令: '<车id> <x_cm> <y_cm> [速度0..10]' | p <车id> | s | q")
    try:
        gx, gy = float(parts[1]), float(parts[2])
    except ValueError as exc:
        raise ValueError("厘米坐标须为数字") from exc
    try:
        speed = int(parts[3]) if len(parts) == 4 else 10
    except ValueError as exc:
        raise ValueError("速度须为 0..10 的整数") from exc
    validate_speed_level(speed)
    return {
        "action": "move",
        "robot_id": parts[0],
        "x_cm": gx,
        "y_cm": gy,
        "speed": speed,
    }


def format_position(position: dict) -> str:
    """格式化 Fleet/CLI 共用的位置快照。"""
    rid = position.get("car_id") or position["robot_id"]
    if position["x"] is None:
        return f"{rid}: 从未识别到位姿，status={position['status']}"
    age_ms = position["age_ms"]
    freshness = (f"新鲜 {age_ms}ms" if position["fresh"]
                 else f"过期 {age_ms}ms")
    target = position.get("target_landmark_id")
    gap = position.get("landmark_gap_cm")
    landmark = (f" target={target} gap={gap:.3f}cm"
                if target is not None and gap is not None else "")
    return (f"{rid}: position_cm=({position['x']:.3f}, {position['y']:.3f}) "
            f"theta={position['theta']:.4f}rad status={position['status']} "
            f"{freshness}{landmark}")


def dispatch_cli_command(fleet: Fleet, command: dict | None) -> bool:
    """执行一条已解析命令；返回 False 表示 CLI 应退出。"""
    if command is None:
        return True
    action = command["action"]
    if action == "quit":
        return False
    if action == "stop_all":
        fleet.stop_all()
        return True
    if action == "position":
        print(format_position(fleet.get_position(command["robot_id"])))
        return True
    if action == "move":
        rover = fleet.rover(command["robot_id"])
        goal = (command["x_cm"], command["y_cm"])
        rover.set_goal(goal, speed=command["speed"])
        return True
    if action == "move_landmark":
        rover = fleet.rover(command["robot_id"])
        rover.set_landmark_goal(
            command["landmark_id"], speed=command["speed"])
        return True
    raise ValueError(f"未知命令动作: {action}")


def viz_loop(fleet: Fleet, stop_event: threading.Event) -> None:
    """在主线程展示相机检测结果、车辆状态、规划路径与实际轨迹。"""
    import cv2
    import numpy as np

    font = cv2.FONT_HERSHEY_SIMPLEX
    cam_w = 960
    field = fleet.field
    cv2.namedWindow("camera", cv2.WINDOW_AUTOSIZE)
    cv2.moveWindow("camera", 20, 20)
    while not stop_event.is_set():
        frame, found = field.visual_snapshot()
        if frame is None:
            view = np.full((540, cam_w, 3), 30, np.uint8)
            cv2.putText(view, "NO FRAME", (40, 270), font, 1.3,
                        (0, 0, 255), 3, cv2.LINE_AA)
        else:
            frame = frame.copy()
            for marker_id, quad in found.items():
                points = quad.astype(int).reshape(-1, 1, 2)
                cv2.polylines(frame, [points], True, (0, 255, 0), 3)
                cv2.putText(frame, str(marker_id),
                            tuple(quad[0].astype(int)), font, 1.1,
                            (0, 0, 255), 3, cv2.LINE_AA)
                center = quad.mean(axis=0)
                tip = center + ((quad[0] + quad[1]) / 2.0 - center) * 2.2
                cv2.arrowedLine(frame, tuple(center.astype(int)),
                                tuple(tip.astype(int)), (0, 255, 255), 3,
                                tipLength=0.35)
            frame = draw_overlay(
                frame, field.calibrator, fleet.get_obstacles(),
                robot_states=fleet.rovers, paths=fleet.paths,
                trails=fleet.trails,
                robot_radius_cm=fleet.params["planner"]["robot_radius_cm"])
            height = int(frame.shape[0] * cam_w / frame.shape[1])
            view = cv2.resize(frame, (cam_w, height))
        cv2.imshow("camera", view)
        if (cv2.waitKey(30) & 0xFF) == ord("q"):
            stop_event.set()
    cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser(description="rover_agent 主程序")
    parser.add_argument("--params", default=None, help="params.yaml 路径")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--config", default=None,
                        help="游戏配置 json（读 map.zones 作障碍）")
    parser.add_argument("--bridge", default=None,
                        help="Runtime WebSocket 地址，如 ws://127.0.0.1:8000/ws")
    parser.add_argument("--viz", action="store_true",
                        help="开单窗口实景叠加（坐标/障碍/路径/轨迹）")
    args = parser.parse_args()

    params = load_params(args.params)
    fleet = Fleet(camera=args.camera, params=params, config=args.config)
    stop_event = threading.Event()

    if args.bridge:
        from rover_agent.bridge import start_bridge_thread
        start_bridge_thread(
            fleet,
            args.bridge,
            rate_hz=params["bridge"]["rate_hz"],
            theta_unit=params["bridge"]["theta_unit"],
        )

    def cli_loop() -> None:
        try:
            while not stop_event.is_set():
                try:
                    line = input("> ")
                except EOFError:
                    break
                try:
                    command = parse_cli_command(line)
                    if not dispatch_cli_command(fleet, command):
                        break
                except (KeyError, ValueError) as exc:
                    print(f"命令无效: {exc}")
        except KeyboardInterrupt:
            pass
        finally:
            stop_event.set()

    print(__doc__)
    try:
        if args.viz:
            threading.Thread(
                target=cli_loop, name="cli", daemon=True).start()
            viz_loop(fleet, stop_event)
        else:
            cli_loop()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        fleet.shutdown()
        print("[agent] 已退出，所有车已停")


if __name__ == "__main__":
    main()
