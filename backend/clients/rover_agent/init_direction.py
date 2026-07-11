"""小车方向初始化程序——新车上场先跑这个。

功能：
1. 实时画面：所有码画绿框 + 黄色方向箭头（码的"上边缘"朝向），
   车码旁标注 世界角度 与所属车辆，四角码标 corner；
2. 按数字键 1..9 选一辆车 → 自动流程：静止采样 → 前进脉冲 0.9s →
   停车采样 → 对比【车实际位移方向】和【码箭头方向】，算出该车的
   theta_offset_deg（码贴歪/贴反多少度，一次测清）；
3. 按 w 把测得的偏移写回 params.yaml（只改对应车那一行的数字）。

用法（repo 根目录，须在你自己的终端跑——相机权限）:
    PYTHONPATH=backend/clients python -m rover_agent.init_direction --camera 0
键位: 1..9 测对应车方向 | w 写回 params.yaml | c 重标定 | q 退出
"""
from __future__ import annotations

import argparse
import math
import pathlib
import time

import cv2
import numpy as np

from rover_agent import calibration as _calib_mod
from rover_agent.calibration import Calibrator, aruco_detect, dict_id_by_name
from rover_agent.drive import RoverDrive
from rover_agent.vision import CameraSource, detect_rovers

FONT = cv2.FONT_HERSHEY_SIMPLEX
PULSE_PCT = 55        # 前进脉冲轮速（%）——太低时单侧电机克服不了静摩擦，车会跑偏
PULSE_SEC = 0.8       # 脉冲时长
SAMPLE_SEC = 0.6      # 前后静止采样时长
SETTLE_SEC = 0.5      # 停车后等惯性消散
MIN_MOVE_CM = 3.0     # 位移低于此值视为"车没走"，不出结论


def norm_rad(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def circ_mean(angles) -> float:
    return math.atan2(sum(math.sin(a) for a in angles) / len(angles),
                      sum(math.cos(a) for a in angles) / len(angles))


def suggest_offset_deg(motion_theta: float, marker_theta_raw: float) -> float:
    """theta_offset_deg = 车实际前进方向 − 码原始朝向（世界系，度）。"""
    return math.degrees(norm_rad(motion_theta - marker_theta_raw))


def snap_deg(deg: float) -> int:
    """最接近的直角贴纸方位（0/±90/180）——通常码就是贴歪了个直角。"""
    return min((0, 90, -90, 180),
               key=lambda s: abs(norm_rad(math.radians(deg - s))))


# 写回逻辑统一收进 params_io；此处再导出保持旧导入路径可用
from rover_agent.params_io import update_params_offset  # noqa: E402,F401


def load_params(path: str | None):
    p = (pathlib.Path(path) if path
         else pathlib.Path(_calib_mod.__file__).with_name("params.yaml"))
    import yaml
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f), p


def main() -> None:
    ap = argparse.ArgumentParser(description="小车方向初始化（箭头 + 自动测偏移）")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--params", default=None)
    args = ap.parse_args()

    params, params_path = load_params(args.params)
    calib = Calibrator(params)
    robots = list(params["robots"].items())          # [(rid, cfg)] 数字键顺序
    marker_to_robot = {int(cfg["marker_id"]): rid for rid, cfg in robots}
    corner_ids = set(int(m) for m in params["corners"]["marker_ids"])
    fallback = params.get("aruco_dict", "DICT_4X4_50")
    dicts = tuple(dict.fromkeys((
        dict_id_by_name(params.get("cars", {}).get("dict") or fallback),
        dict_id_by_name(params["corners"].get("dict") or fallback))))

    drives: dict[str, RoverDrive] = {}
    suggestions: dict[str, float] = {}
    state, t0, target = "IDLE", 0.0, None
    samples_a: list = []
    samples_b: list = []
    msg = "按 1..9 选车测方向 | w 写回 | c 重标定 | q 退出"

    source = CameraSource(args.camera)
    print(__doc__)
    print(f"车辆列表: " + " ".join(f"[{i+1}]{rid}" for i, (rid, _) in
                                   enumerate(robots)))
    cv2.namedWindow("init_direction", cv2.WINDOW_AUTOSIZE)
    try:
        while True:
            frame = source.read()
            if frame is None:
                view = np.full((540, 960, 3), 30, np.uint8)
                cv2.putText(view, f"NO FRAME from --camera {args.camera}",
                            (40, 270), FONT, 1.2, (0, 0, 255), 3, cv2.LINE_AA)
                cv2.imshow("init_direction", view)
                if cv2.waitKey(30) & 0xFF == ord("q"):
                    break
                continue

            if not calib.calibrated:
                calib.calibrate(frame)
            # 原始位姿：theta_offsets 传空 → 测出的才是"码相对车头"的真实偏差
            poses = (detect_rovers(frame, calib, marker_to_robot,
                                   dict_id=dicts, theta_offsets={})
                     if calib.calibrated else {})

            # ---------- 测量状态机（无线程，跟着帧循环走） ----------
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
                    dist = math.hypot(bx - ax, by - ay)
                    if dist < MIN_MOVE_CM:
                        msg = (f"{target}: 只走了 {dist:.1f}cm(<3cm)，"
                               f"无法判向——查车电量/IP")
                    else:
                        motion = math.atan2(by - ay, bx - ax)
                        raw = circ_mean([s[2] for s in samples_b])
                        off = suggest_offset_deg(motion, raw)
                        suggestions[target] = off
                        msg = (f"{target}: 走了{dist:.0f}cm 实际朝向"
                               f"{math.degrees(motion):.0f}° 码朝向"
                               f"{math.degrees(raw):.0f}° → offset="
                               f"{off:.1f}° (≈{snap_deg(off)}°)  按w写回")
                        print("[init] " + msg)

            # ---------- 叠加层：绿框 + 黄箭头 + 角度标注 ----------
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            found = {}
            for did in dict.fromkeys((calib.dict_id, *dicts)):
                found.update(aruco_detect(gray, did))
            for mid, quad in found.items():
                pts = quad.astype(int).reshape(-1, 1, 2)
                cv2.polylines(frame, [pts], True, (0, 255, 0), 3)
                center = quad.mean(axis=0)
                up_mid = (quad[0] + quad[1]) / 2.0
                tip = center + (up_mid - center) * 2.2
                cv2.arrowedLine(frame, tuple(center.astype(int)),
                                tuple(tip.astype(int)),
                                (0, 255, 255), 3, tipLength=0.35)
                rid = marker_to_robot.get(int(mid))
                if rid and rid in poses:
                    tag = (f"{mid}:{rid} {math.degrees(poses[rid].theta):.0f}deg")
                elif int(mid) in corner_ids:
                    tag = f"{mid}:corner"
                else:
                    tag = str(mid)
                cv2.putText(frame, tag, tuple((quad[0] + (0, -10)).astype(int)),
                            FONT, 0.9, (0, 0, 255), 2, cv2.LINE_AA)

            status = ("CALIBRATED" if calib.calibrated
                      else "CALIBRATING: need 4 corner markers")
            cv2.putText(frame, status, (10, 40), FONT, 1.0,
                        (0, 200, 0) if calib.calibrated else (0, 0, 255),
                        2, cv2.LINE_AA)
            cv2.putText(frame, msg, (10, 80), FONT, 0.7,
                        (0, 255, 255), 2, cv2.LINE_AA)
            for i, (rid, off) in enumerate(sorted(suggestions.items())):
                cv2.putText(frame, f"{rid}: offset {off:.1f} deg"
                            f" (~{snap_deg(off)})",
                            (10, 115 + 28 * i), FONT, 0.7,
                            (255, 200, 0), 2, cv2.LINE_AA)

            h = int(frame.shape[0] * 960 / frame.shape[1])
            cv2.imshow("init_direction", cv2.resize(frame, (960, h)))
            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                break
            if key == ord("c"):
                calib.reset()
                msg = "重标定…"
            elif key == ord("w"):
                if not suggestions:
                    msg = "还没有测量结果，先按数字键测一辆车"
                else:
                    for rid, off in suggestions.items():
                        ok = update_params_offset(params_path, rid, off)
                        print(f"[init] 写回 {rid} theta_offset_deg="
                              f"{off:.1f} → {'OK' if ok else 'FAIL'}")
                    msg = f"已写回 {params_path.name}: " + " ".join(
                        f"{r}={o:.1f}" for r, o in suggestions.items())
            elif ord("1") <= key <= ord("9") and state == "IDLE":
                idx = key - ord("1")
                if idx < len(robots) and calib.calibrated:
                    target = robots[idx][0]
                    if target not in drives:
                        cfg = dict(robots)[target]
                        drives[target] = RoverDrive(
                            cfg["ip"], reverse=bool(cfg.get("reverse", False)))
                    samples_a, samples_b = [], []
                    state, t0 = "SAMPLE_A", time.time()
                    msg = f"{target}: 静止采样中，别碰车…"
                    print(f"[init] 开始测 {target}（脉冲 {PULSE_PCT}% "
                          f"{PULSE_SEC}s）")
    finally:
        for d in drives.values():
            d.close()
        source.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
