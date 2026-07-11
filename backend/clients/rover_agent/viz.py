"""单窗口实景叠加调试（M1 验收工具）。

用法（repo 根目录）:
    PYTHONPATH=backend/clients python -m rover_agent.viz [--camera 0] [--params 路径]
键位: q 退出 | c 重标定

M1 物理验收（plan Task 4 Step 3）：
手推车沿 x 正方向 → 读数 x 增；沿 y 正方向 → y 增；原地逆时针拧 → θ 增；
车摆到已知格线交点 → 读数误差 < 2cm。
"""
from __future__ import annotations

import argparse
import math
import pathlib  # noqa: F401 —— load_params 使用

import cv2
import numpy as np
import yaml

from rover_agent.vision import PoseStore

FONT = cv2.FONT_HERSHEY_SIMPLEX


def load_params(path: str | None = None) -> dict:
    p = pathlib.Path(path) if path else pathlib.Path(__file__).with_name("params.yaml")
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def render_topview(store: PoseStore, params: dict, grid=None,
                   canvas_w: int = 600, calibrated: bool = True,
                   trails: dict | None = None,
                   paths: dict | None = None) -> np.ndarray:
    """世界坐标 → 俯视画布（矩形场地；y 轴翻转在此处理，画布下方 = 世界 y=0）。"""
    table = params["table"]
    w = float(table["width_cm"])
    h_cm = float(table["height_cm"])
    cell = float(table.get("cell_cm", 1))
    nx, ny = int(round(w / cell)), int(round(h_cm / cell))
    scale = canvas_w / w
    canvas_h = int(round(h_cm * scale))
    img = np.full((canvas_h, canvas_w, 3), 255, np.uint8)

    def to_px(x: float, y: float) -> tuple[int, int]:
        return int(round(x * scale)), int(round(canvas_h - y * scale))

    if grid is not None:  # 障碍格填灰
        for ix in range(grid.nx):
            for iy in range(grid.ny):
                if grid.occupied(ix, iy):
                    x0, y0 = to_px(ix * cell, (iy + 1) * cell)
                    x1, y1 = to_px((ix + 1) * cell, iy * cell)
                    cv2.rectangle(img, (x0, y0), (x1, y1), (205, 205, 205), -1)
    for i in range(nx + 1):
        p = int(round(i * cell * scale))
        cv2.line(img, (p, 0), (p, canvas_h), (230, 230, 230), 1)
    for j in range(ny + 1):
        p = int(round(canvas_h - j * cell * scale))
        cv2.line(img, (0, p), (canvas_w, p), (230, 230, 230), 1)

    # 写死的圆柱障碍：实体填红，外圈细线是含车体半径的膨胀边界（路径不会进入）
    margin = float(params.get("planner", {}).get("robot_radius_cm", 0.0))
    for obs in params.get("obstacles") or ():
        center = to_px(float(obs["x_cm"]), float(obs["y_cm"]))
        cv2.circle(img, center,
                   max(1, int(round((float(obs["radius_cm"]) + margin) * scale))),
                   (170, 170, 240), 1)
        cv2.circle(img, center,
                   max(1, int(round(float(obs["radius_cm"]) * scale))),
                   (60, 60, 200), -1)

    # 坐标系标注：原点红点 + x/y 轴箭头 + 每格的格号刻度
    origin = to_px(0, 0)
    cv2.circle(img, origin, 5, (0, 0, 255), -1)
    cv2.putText(img, "(0,0)", (origin[0] + 8, origin[1] - 8),
                FONT, 0.5, (0, 0, 255), 1, cv2.LINE_AA)
    cv2.arrowedLine(img, origin, to_px(5, 0), (0, 0, 255), 2, tipLength=0.2)
    cv2.putText(img, "x", (to_px(6, 0)[0], origin[1] - 6),
                FONT, 0.55, (0, 0, 255), 1, cv2.LINE_AA)
    cv2.arrowedLine(img, origin, to_px(0, 5), (0, 0, 255), 2, tipLength=0.2)
    cv2.putText(img, "y", (origin[0] + 6, to_px(0, 6)[1]),
                FONT, 0.55, (0, 0, 255), 1, cv2.LINE_AA)
    for i in range(2, nx, 2):   # 格号刻度（每 2 格标一个，读格坐标用）
        cv2.putText(img, str(i), (to_px(i * cell, 0)[0] - 4, canvas_h - 4),
                    FONT, 0.35, (150, 150, 150), 1, cv2.LINE_AA)
    for j in range(2, ny, 2):
        cv2.putText(img, str(j), (3, to_px(0, j * cell)[1] + 4),
                    FONT, 0.35, (150, 150, 150), 1, cv2.LINE_AA)

    # 预期路径（规划器输出的路径点连线）：绿色，◎=终点
    if paths:
        for pts in paths.values():
            pts = [p for p in pts]
            if len(pts) < 2:
                continue
            arr = np.array([to_px(x, y) for x, y in pts], np.int32)
            cv2.polylines(img, [arr.reshape(-1, 1, 2)], False,
                          (0, 170, 0), 2, cv2.LINE_AA)
            for p in arr:  # 路径点小圈，便于核对格中心
                cv2.circle(img, tuple(p), 3, (0, 170, 0), 1)
            cv2.circle(img, tuple(arr[-1]), 9, (0, 170, 0), 2)

    # 轨迹（如 obstacle_test 记录的实际行驶路线）：空心圈=起点，实心点=终点
    if trails:
        colors = [(200, 120, 0), (0, 150, 220), (130, 0, 200), (0, 180, 90)]
        for i, (name, pts) in enumerate(list(trails.items())):
            pts = list(pts)  # 拷贝：工作线程可能正在 append
            if len(pts) < 2:
                continue
            color = colors[i % len(colors)]
            arr = np.array([to_px(x, y) for x, y in pts], np.int32)
            cv2.polylines(img, [arr.reshape(-1, 1, 2)], False, color, 2, cv2.LINE_AA)
            cv2.circle(img, tuple(arr[0]), 6, color, 2)
            cv2.circle(img, tuple(arr[-1]), 6, color, -1)
            cv2.putText(img, name, (arr[-1][0] + 8, arr[-1][1] + 4),
                        FONT, 0.45, color, 1, cv2.LINE_AA)

    status = "CALIBRATED" if calibrated else "CALIBRATING: need 4 corner markers"
    cv2.putText(img, status, (10, 20), FONT, 0.5,
                (0, 140, 0) if calibrated else (0, 0, 220), 1, cv2.LINE_AA)

    for rid, pose in store.all_fresh().items():
        cx, cy = to_px(pose.x, pose.y)
        tip = to_px(pose.x + 5 * math.cos(pose.theta),
                    pose.y + 5 * math.sin(pose.theta))
        cv2.circle(img, (cx, cy), 8, (180, 60, 0), -1)
        cv2.arrowedLine(img, (cx, cy), tip, (180, 60, 0), 2, tipLength=0.4)
        label = (f"{rid} ({pose.x:.1f},{pose.y:.1f})cm "
                 f"{math.degrees(pose.theta):.0f}deg")
        cv2.putText(img, label, (min(cx + 10, canvas_w - 260), max(cy - 10, 14)),
                    FONT, 0.4, (60, 60, 60), 1, cv2.LINE_AA)
    return img


def main() -> None:
    from rover_agent.fleet import Fleet
    from rover_agent.overlay import draw_overlay

    ap = argparse.ArgumentParser(description="rover_agent 实景定位调试")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--params", default=None)
    args = ap.parse_args()

    params = load_params(args.params)
    fleet = Fleet(camera=args.camera, params=params, health=False)
    print("viz: q 退出 | c 重标定（单窗口实景叠加）")
    cam_w = 960
    cv2.namedWindow("camera", cv2.WINDOW_AUTOSIZE)
    cv2.moveWindow("camera", 20, 20)
    try:
        while True:
            frame, found = fleet.field.visual_snapshot()
            if frame is None:
                view = np.full((540, cam_w, 3), 30, np.uint8)
                cv2.putText(view, f"NO FRAME from --camera {args.camera}",
                            (40, 250), FONT, 1.3, (0, 0, 255), 3, cv2.LINE_AA)
                cv2.putText(view, "check: index? in use by another app? permission?",
                            (40, 310), FONT, 0.8, (200, 200, 200), 2, cv2.LINE_AA)
            else:
                frame = frame.copy()
                for mid, quad in found.items():
                    pts = quad.astype(int).reshape(-1, 1, 2)
                    cv2.polylines(frame, [pts], True, (0, 255, 0), 3)
                    cv2.putText(frame, str(mid), tuple(quad[0].astype(int)),
                                FONT, 1.2, (0, 0, 255), 3, cv2.LINE_AA)
                    # 黄色箭头 = 码的"上边缘"方向（系统当作车头的方向）
                    center = quad.mean(axis=0)
                    up_mid = (quad[0] + quad[1]) / 2.0
                    tip = center + (up_mid - center) * 2.2
                    cv2.arrowedLine(frame, tuple(center.astype(int)),
                                    tuple(tip.astype(int)),
                                    (0, 255, 255), 3, tipLength=0.35)
                frame = draw_overlay(
                    frame, fleet.field.calibrator, fleet.get_obstacles(),
                    robot_states=fleet.rovers, paths=fleet.paths,
                    trails=fleet.trails,
                    robot_radius_cm=params["planner"]["robot_radius_cm"])
                h = int(frame.shape[0] * cam_w / frame.shape[1])
                view = cv2.resize(frame, (cam_w, h))
            cv2.imshow("camera", view)
            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                break
            if key == ord("c"):
                fleet.field.calibrator.reset()
                print("viz: 重标定…")
    finally:
        fleet.shutdown()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
