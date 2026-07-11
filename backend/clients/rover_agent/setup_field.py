"""场地初始化程序——开场跑一次，把"这块场地的一切"落盘 params.yaml。

盘点三件事（全在一个窗口里完成）：
1. 每辆车的编号：画面里所有码实时标注归属（corner / r0 / 未绑定 NEW?）；
   按 b 把未绑定的码登记成新车——车顶码 0/1/2/3 固定对应 r0/r1/r2/r3；
2. 码贴得正不正：按 1..9 让对应车自动走一小段，对比"实际位移方向 vs
   码箭头方向"算出 theta_offset_deg（贴歪多少度一次测清）；
3. 固定目标：鼠标在画面上直接圈——按下=圆心、拖开=半径，或按 a 在终端
   输入 id/圆心/半径；它们既参与绕行，也可以成为车辆目的地。u 撤销，o 清空。

按 w 一次性写回 params.yaml（新车 + 方向偏移 + 固定目标）。
之后上层用 fleet.Fleet 拿每辆车的句柄，goto 到点即可——地图、路径、
丢码刹车都在下层，上层不用管。

用法（repo 根目录，须在你自己的终端跑——相机权限）:
    PYTHONPATH=backend/clients python -m rover_agent.setup_field --camera 0
键位: b 绑新车 | 1..9 测方向 | 鼠标拖拽圈固定目标 | a 数字输入固定目标
     | u 撤销圈 | o 清空圈 | w 写回 | c 重标定 | q 退出
"""
from __future__ import annotations

import argparse
import json
import math
import time

import cv2
import numpy as np

from rover_agent.calibration import (Calibrator, aruco_detect,
                                     dict_id_by_name)
from rover_agent.drive import RoverDrive
from rover_agent.planner import planning_margin_cm
from rover_agent.init_direction import (MIN_MOVE_CM, PULSE_PCT, PULSE_SEC,
                                        SAMPLE_SEC, SETTLE_SEC, circ_mean,
                                        load_params, snap_deg,
                                        suggest_offset_deg)
from rover_agent.obstacle_map import ObstacleMap
from rover_agent.params_io import (replace_landmarks, update_params_offset,
                                   upsert_robot)
from rover_agent.overlay import draw_overlay
from rover_agent.vision import CameraSource, detect_rovers

FONT = cv2.FONT_HERSHEY_SIMPLEX
VIEW_W = 960          # 显示窗口宽度（原始帧等比缩放）


def next_rid(existing) -> str:
    """r0/r1/… 里最小的空号（仅供兼容旧调用）。"""
    n = 0
    while f"r{n}" in existing:
        n += 1
    return f"r{n}"


def rid_for_marker(marker_id: int) -> str:
    """把四辆物理车的车顶码稳定映射为对外 car_id。"""
    marker_id = int(marker_id)
    if marker_id not in range(4):
        raise ValueError("车辆标记 id 必须是 0..3")
    return f"r{marker_id}"


def circle_world(px_to_world, center_px, edge_px, obstacle_id: str,
                 min_radius_cm: float = 1.0) -> dict:
    """鼠标圈转换为统一的厘米圆形障碍记录。"""
    cx, cy = px_to_world(center_px)
    ex, ey = px_to_world(edge_px)
    radius = max(min_radius_cm, math.hypot(ex - cx, ey - cy))
    return {"id": obstacle_id, "shape": "circle",
            "x_cm": round(cx, 3), "y_cm": round(cy, 3),
            "radius_cm": round(radius, 3)}


def drag_preview_obstacle(px_to_world, center_px, edge_px,
                          obstacle_id: str = "__preview__") -> dict:
    """把当前拖动转换为世界圆；画面形状交给透视投影决定。"""
    return circle_world(px_to_world, center_px, edge_px, obstacle_id)


def parse_obstacle_input(text: str) -> dict:
    parts = text.split()
    if len(parts) != 4:
        raise ValueError("输入格式: id x_cm y_cm radius_cm")
    obstacle_id, x, y, radius = parts
    try:
        return {"id": obstacle_id, "shape": "circle",
                "x_cm": float(x), "y_cm": float(y),
                "radius_cm": float(radius)}
    except ValueError as exc:
        raise ValueError("x_cm/y_cm/radius_cm 必须是数字") from exc


def next_obstacle_id(obstacles) -> str:
    used = {item["id"] for item in obstacles}
    index = 1
    while f"obstacle-{index}" in used:
        index += 1
    return f"obstacle-{index}"


def validate_obstacle_candidates(params: dict, obstacles) -> list[dict]:
    """用运行时相同规则校验整批候选；失败时调用方原列表不变。"""
    return ObstacleMap(params, landmarks=obstacles).landmarks_snapshot()[
        "landmarks"]


def obstacle_summary(obstacle: dict) -> str:
    return (f"{obstacle['id']}: "
            f"({obstacle['x_cm']:.1f},{obstacle['y_cm']:.1f})cm "
            f"r={obstacle['radius_cm']:.1f}cm")


def landmarks_json(landmarks) -> str:
    """输出可直接交给上层或写死到配置中的固定目标 JSON。"""
    records = []
    for item in landmarks:
        records.append({
            "id": item["id"],
            "shape": item["shape"],
            "x_cm": round(float(item["x_cm"]), 2),
            "y_cm": round(float(item["y_cm"]), 2),
            "radius_cm": round(float(item["radius_cm"]), 2),
            "properties": dict(item.get("properties", {})),
        })
    return json.dumps(records, ensure_ascii=False, indent=2)


def main() -> None:
    ap = argparse.ArgumentParser(description="场地初始化（绑车+测方向+圈障碍）")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--params", default=None)
    args = ap.parse_args()

    params, params_path = load_params(args.params)
    calib = Calibrator(params)
    robots: dict[str, dict] = dict(params["robots"])   # 有序，数字键按此排
    marker_to_robot = {int(cfg["marker_id"]): rid
                       for rid, cfg in robots.items()}
    corner_ids = set(int(m) for m in params["corners"]["marker_ids"])
    fallback = params.get("aruco_dict", "DICT_4X4_50")
    dicts = tuple(dict.fromkeys((
        dict_id_by_name(params.get("cars", {}).get("dict") or fallback),
        dict_id_by_name(params["corners"].get("dict") or fallback))))

    landmarks: list[dict] = [
        dict(item) for item in params.get(
            "landmarks", params.get("obstacles", ()))
    ]
    new_robots: list[str] = []                 # 本次登记、待落盘的车
    suggestions: dict[str, float] = {}         # rid → 测得的 theta_offset_deg
    drives: dict[str, RoverDrive] = {}
    state, t0, target = "IDLE", 0.0, None
    samples_a: list = []
    samples_b: list = []
    msg = "b 绑新车 | 1..9 测方向 | 鼠标圈障碍 | w 写回 | q 退出"

    # 鼠标状态（回调线程写、主循环读；坐标是显示坐标，乘 scale 还原原始像素）
    mouse = {"down": None, "cur": None, "scale": 1.0}

    def on_mouse(event, x, y, _flags, _ud) -> None:
        nonlocal msg
        if event == cv2.EVENT_LBUTTONDOWN:
            mouse["down"] = (x, y)
            mouse["cur"] = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and mouse["down"]:
            mouse["cur"] = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and mouse["down"]:
            done_msg = _finish_circle((x, y))
            if done_msg:
                msg = done_msg
            mouse["down"] = None
            mouse["cur"] = None

    def _finish_circle(up_xy) -> str | None:
        if not calib.calibrated:
            return "还没标定（四角码要都可见），先别圈"
        s = mouse["scale"]
        c = (mouse["down"][0] * s, mouse["down"][1] * s)
        e = (up_xy[0] * s, up_xy[1] * s)
        if math.hypot(e[0] - c[0], e[1] - c[1]) < 4:   # 只是点了一下
            return None
        obs = circle_world(calib.px_to_world, c, e,
                           next_obstacle_id(landmarks))
        try:
            validated = validate_obstacle_candidates(params, [*landmarks, obs])
        except ValueError as exc:
            return f"障碍无效: {exc}"
        landmarks[:] = validated
        print(f"[setup] 圈了固定目标 #{len(landmarks)}: {obs}")
        return f"{obstacle_summary(obs)}  u撤销 w写回"

    def bind_new_car(unbound: list[int]) -> str:
        """终端交互登记一辆新车（窗口此刻会短暂冻结，属正常）。"""
        print(f"[setup] 画面里未绑定的码: {unbound}")
        try:
            mid = int(input("要绑定的码 id: ").strip())
            ip = input("该车的 IP（看车载 OLED）: ").strip()
        except (ValueError, EOFError):
            return "输入无效，取消绑定"
        if mid in corner_ids or mid in marker_to_robot:
            return f"码 {mid} 已被占用（{marker_to_robot.get(mid, 'corner')}）"
        try:
            rid = rid_for_marker(mid)
        except ValueError as exc:
            return str(exc)
        if rid in robots:
            return f"{rid} 已绑定码 {robots[rid]['marker_id']}"
        robots[rid] = {"ip": ip, "marker_id": mid, "theta_offset_deg": 0}
        marker_to_robot[mid] = rid
        new_robots.append(rid)
        idx = list(robots).index(rid) + 1
        print(f"[setup] 已登记 {rid} ← 码{mid} @ {ip}")
        return f"已登记 {rid}（按 {idx} 测它的方向，w 落盘）"

    source = CameraSource(args.camera)
    print(__doc__)
    cv2.namedWindow("setup_field", cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback("setup_field", on_mouse)
    try:
        while True:
            frame = source.read()
            if frame is None:
                view = np.full((540, VIEW_W, 3), 30, np.uint8)
                cv2.putText(view, f"NO FRAME from --camera {args.camera}",
                            (40, 270), FONT, 1.2, (0, 0, 255), 3, cv2.LINE_AA)
                cv2.imshow("setup_field", view)
                if cv2.waitKey(30) & 0xFF == ord("q"):
                    break
                continue
            mouse["scale"] = frame.shape[1] / VIEW_W

            if not calib.calibrated:
                calib.calibrate(frame)
            # 原始位姿（offset 传空）：测方向要的是码本身的朝向
            poses = (detect_rovers(frame, calib, marker_to_robot,
                                   dict_id=dicts, theta_offsets={})
                     if calib.calibrated else {})

            # ---------- 方向测量状态机（同 init_direction，跟帧循环走）------
            now = time.time()
            if state in ("SAMPLE_A", "SAMPLE_B") and target in poses:
                p = poses[target]
                (samples_a if state == "SAMPLE_A" else samples_b).append(
                    (p.x, p.y, p.theta))
            if state == "SAMPLE_A" and now - t0 >= SAMPLE_SEC:
                if len(samples_a) < 3:
                    state, msg = "IDLE", f"{target}: 静止段没看到码，检查遮挡"
                else:
                    drives[target].set_wheels(PULSE_PCT, PULSE_PCT)
                    state, t0, msg = "DRIVE", now, f"{target}: 前进脉冲中…"
            elif state == "DRIVE" and now - t0 >= PULSE_SEC:
                drives[target].stop()
                state, t0 = "SETTLE", now
            elif state == "SETTLE" and now - t0 >= SETTLE_SEC:
                state, t0, msg = "SAMPLE_B", now, f"{target}: 停车后采样…"
            elif state == "SAMPLE_B" and now - t0 >= SAMPLE_SEC:
                state = "IDLE"
                if len(samples_b) < 3:
                    msg = f"{target}: 停车段没看到码，重试"
                else:
                    ax = sum(s[0] for s in samples_a) / len(samples_a)
                    ay = sum(s[1] for s in samples_a) / len(samples_a)
                    bx = sum(s[0] for s in samples_b) / len(samples_b)
                    by = sum(s[1] for s in samples_b) / len(samples_b)
                    moved = math.hypot(bx - ax, by - ay)
                    if moved < MIN_MOVE_CM:
                        msg = (f"{target}: 只走了 {moved:.1f}cm(<3cm)，"
                               f"无法判向——查车电量/IP")
                    else:
                        motion = math.atan2(by - ay, bx - ax)
                        raw = circ_mean([s[2] for s in samples_b])
                        off = suggest_offset_deg(motion, raw)
                        suggestions[target] = off
                        msg = (f"{target}: offset={off:.1f}deg"
                               f" (~{snap_deg(off)}deg)  按w写回")
                        print(f"[setup] {target} 走了{moved:.0f}cm → " + msg)

            # ---------- 叠加层 ----------
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            found = {}
            for did in dict.fromkeys((calib.dict_id, *dicts)):
                found.update(aruco_detect(gray, did))
            for mid, quad in found.items():
                pts = quad.astype(int).reshape(-1, 1, 2)
                cv2.polylines(frame, [pts], True, (0, 255, 0), 3)
                center = quad.mean(axis=0)
                tip = center + ((quad[0] + quad[1]) / 2.0 - center) * 2.2
                cv2.arrowedLine(frame, tuple(center.astype(int)),
                                tuple(tip.astype(int)),
                                (0, 255, 255), 3, tipLength=0.35)
                rid = marker_to_robot.get(int(mid))
                if rid and rid in poses:
                    tag = f"{mid}:{rid} {math.degrees(poses[rid].theta):.0f}deg"
                    color = (0, 0, 255)
                elif int(mid) in corner_ids:
                    tag, color = f"{mid}:corner", (0, 0, 255)
                else:
                    tag, color = f"{mid}:NEW? (b to bind)", (255, 0, 255)
                cv2.putText(frame, tag, tuple((quad[0] + (0, -10)).astype(int)),
                            FONT, 0.9, color, 2, cv2.LINE_AA)

            if calib.calibrated:
                preview = None
                if mouse["down"] and mouse["cur"]:
                    scale = mouse["scale"]
                    center_px = (mouse["down"][0] * scale,
                                 mouse["down"][1] * scale)
                    edge_px = (mouse["cur"][0] * scale,
                               mouse["cur"][1] * scale)
                    preview = drag_preview_obstacle(
                        calib.px_to_world, center_px, edge_px)
                frame = draw_overlay(
                    frame, calib,
                    {"version": 0,
                     "width_cm": params["table"]["width_cm"],
                     "height_cm": params["table"]["height_cm"],
                     "cell_cm": params["table"]["cell_cm"],
                     "landmarks": landmarks,
                     "transient_obstacles": [],
                     "obstacles": landmarks},
                    robot_radius_cm=planning_margin_cm(params),
                    preview_obstacle=preview)

            status = ("CALIBRATED" if calib.calibrated
                      else "CALIBRATING: need 4 corner markers")
            cv2.putText(frame, status, (10, 40), FONT, 1.0,
                        (0, 200, 0) if calib.calibrated else (0, 0, 255),
                        2, cv2.LINE_AA)
            cv2.putText(frame, msg, (10, 80), FONT, 0.7,
                        (0, 255, 255), 2, cv2.LINE_AA)
            info = [f"{rid}: marker={cfg['marker_id']} ip={cfg['ip'] or '?'}"
                    + (f" offset={suggestions[rid]:.1f}deg"
                       if rid in suggestions else "")
                    + (" [NEW]" if rid in new_robots else "")
                    for rid, cfg in robots.items()]
            for i, line in enumerate(info):
                cv2.putText(frame, f"[{i+1}] {line}", (10, 115 + 28 * i),
                            FONT, 0.65, (255, 200, 0), 2, cv2.LINE_AA)

            h = int(frame.shape[0] * VIEW_W / frame.shape[1])
            view = cv2.resize(frame, (VIEW_W, h))
            cv2.imshow("setup_field", view)

            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                break
            if key == ord("c"):
                calib.reset()
                msg = "重标定…"
            elif key == ord("b"):
                unbound = sorted(set(int(m) for m in found)
                                 - corner_ids - set(marker_to_robot))
                msg = (bind_new_car(unbound) if unbound
                       else "画面里没有未绑定的码")
            elif key == ord("a"):
                try:
                    obstacle = parse_obstacle_input(
                        input("障碍 id x_cm y_cm radius_cm: ").strip())
                    landmarks[:] = validate_obstacle_candidates(
                        params, [*landmarks, obstacle])
                    msg = f"已加入 {obstacle['id']}，w 写回"
                except (ValueError, EOFError) as exc:
                    msg = f"障碍输入无效: {exc}"
            elif key == ord("u"):
                if landmarks:
                    gone = landmarks.pop()
                    msg = f"已撤销 {obstacle_summary(gone)}"
            elif key == ord("o"):
                landmarks.clear()
                msg = "已清空全部障碍（w 写回后生效）"
            elif key == ord("w"):
                for rid in new_robots:
                    ok = upsert_robot(params_path, rid, robots[rid]["ip"],
                                      robots[rid]["marker_id"])
                    print(f"[setup] 写回新车 {rid} → {'OK' if ok else 'FAIL'}")
                new_robots.clear()
                for rid, off in suggestions.items():
                    ok = update_params_offset(params_path, rid, off)
                    print(f"[setup] 写回 {rid} theta_offset_deg={off:.1f} "
                          f"→ {'OK' if ok else 'FAIL'}")
                replace_landmarks(params_path, landmarks)
                print(f"[setup] 写回固定目标 ×{len(landmarks)}")
                print("[setup] 固定目标 JSON（可复制给上层/写死配置）:")
                print(landmarks_json(landmarks))
                msg = (f"已写回 {params_path.name}: 车×{len(robots)} "
                       f"固定目标×{len(landmarks)}——上层可用 fleet 接管了")
            elif ord("1") <= key <= ord("9") and state == "IDLE":
                idx = key - ord("1")
                rids = list(robots)
                if idx < len(rids) and calib.calibrated:
                    target = rids[idx]
                    cfg = robots[target]
                    if not cfg.get("ip"):
                        msg = f"{target} 还没填 IP，先按 b 或改 params.yaml"
                        continue
                    if target not in drives:
                        drives[target] = RoverDrive(
                            cfg["ip"], reverse=bool(cfg.get("reverse", False)))
                    samples_a, samples_b = [], []
                    state, t0 = "SAMPLE_A", time.time()
                    msg = f"{target}: 静止采样中，别碰车…"
                    print(f"[setup] 开始测 {target}（脉冲 {PULSE_PCT}% "
                          f"{PULSE_SEC}s）")
    finally:
        for d in drives.values():
            d.close()
        source.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
