"""把厘米世界坐标投影到实景相机帧。"""
from __future__ import annotations

import math

import cv2
import numpy as np

FONT = cv2.FONT_HERSHEY_SIMPLEX


def project_world_points(H, points) -> np.ndarray:
    """H 为像素到世界的矩阵；返回世界点在原相机画面中的像素。"""
    if H is None:
        raise RuntimeError("尚未标定")
    values = np.asarray(list(points), dtype=np.float64).reshape(-1, 1, 2)
    if not len(values):
        return np.empty((0, 2), dtype=np.float64)
    return cv2.perspectiveTransform(values, np.linalg.inv(H)).reshape(-1, 2)


def circle_world_points(cx: float, cy: float, radius: float,
                        samples: int = 48) -> list[tuple[float, float]]:
    return [
        (cx + radius * math.cos(2 * math.pi * index / samples),
         cy + radius * math.sin(2 * math.pi * index / samples))
        for index in range(samples)
    ]


def _polyline(image, H, points, color, thickness=2, closed=False):
    projected = np.rint(project_world_points(H, points)).astype(np.int32)
    if len(projected) >= 2:
        cv2.polylines(image, [projected.reshape(-1, 1, 2)], closed,
                      color, thickness, cv2.LINE_AA)
    return projected


def draw_overlay(frame, calibrator, map_snapshot: dict,
                 robot_states=None, paths=None, trails=None,
                 robot_radius_cm: float = 0,
                 preview_obstacle: dict | None = None) -> np.ndarray:
    """返回带坐标、障碍、路线和轨迹的帧副本；输入帧不修改。"""
    output = frame.copy()
    if not calibrator.calibrated:
        return output
    H = calibrator.H
    width = float(map_snapshot["width_cm"])
    height = float(map_snapshot["height_cm"])

    try:
        _polyline(output, H, [(0, 0), (width, 0), (width, height),
                              (0, height)], (245, 245, 245), 2, True)
        for x in range(10, int(width), 10):
            _polyline(output, H, [(x, 0), (x, height)],
                      (150, 150, 150), 1)
        for y in range(10, int(height), 10):
            _polyline(output, H, [(0, y), (width, y)],
                      (150, 150, 150), 1)
        origin = np.rint(project_world_points(H, [(0, 0)])[0]).astype(int)
        cv2.putText(output, "(0,0)", (origin[0] + 6, origin[1] - 6),
                    FONT, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
    except (ValueError, RuntimeError, np.linalg.LinAlgError):
        pass

    layered = ("landmarks" in map_snapshot
               or "transient_obstacles" in map_snapshot)
    layers = (
        ((map_snapshot.get("landmarks", ()), (40, 40, 240), "L"),
         (map_snapshot.get("transient_obstacles", ()), (220, 80, 220), "T"))
        if layered else
        ((map_snapshot.get("obstacles", ()), (40, 40, 240), ""),)
    )
    for obstacles, physical_color, prefix in layers:
        for obstacle in obstacles:
            try:
                cx = float(obstacle["x_cm"])
                cy = float(obstacle["y_cm"])
                radius = float(obstacle["radius_cm"])
                physical = _polyline(
                    output, H, circle_world_points(cx, cy, radius),
                    physical_color, 3, True)
                fill = output.copy()
                if len(physical) >= 3:
                    cv2.fillPoly(fill, [physical.reshape(-1, 1, 2)],
                                 physical_color)
                    output = cv2.addWeighted(fill, 0.18, output, 0.82, 0)
                _polyline(
                    output, H,
                    circle_world_points(cx, cy, radius + robot_radius_cm),
                    (0, 170, 255), 2, True)
                center = np.rint(project_world_points(
                    H, [(cx, cy)])[0]).astype(int)
                label = f"{prefix}:{obstacle['id']}" if prefix else str(
                    obstacle["id"])
                cv2.putText(output, label, tuple(center), FONT,
                            0.45, (255, 255, 255), 1, cv2.LINE_AA)
            except (KeyError, ValueError, RuntimeError, np.linalg.LinAlgError):
                continue

    if preview_obstacle is not None:
        try:
            _polyline(
                output, H,
                circle_world_points(
                    float(preview_obstacle["x_cm"]),
                    float(preview_obstacle["y_cm"]),
                    float(preview_obstacle["radius_cm"]),
                ),
                (200, 0, 200), 2, True,
            )
        except (KeyError, ValueError, RuntimeError, np.linalg.LinAlgError):
            pass

    for collection, color, thickness in (
            (paths or {}, (60, 220, 80), 3),
            (trails or {}, (255, 180, 40), 2)):
        for points in collection.values():
            try:
                if len(points) >= 2:
                    _polyline(output, H, list(points), color, thickness)
            except (ValueError, RuntimeError, np.linalg.LinAlgError):
                continue

    for rid, rover in (robot_states or {}).items():
        pose = rover.pose
        if pose is None:
            continue
        try:
            point = np.rint(project_world_points(
                H, [(pose.x, pose.y)])[0]).astype(int)
            cv2.circle(output, tuple(point), 6, (255, 120, 30), -1)
            label = f"{rid} {pose.x:.1f},{pose.y:.1f} {rover.status}"
            cv2.putText(output, label, (point[0] + 8, point[1] - 8),
                        FONT, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        except (ValueError, RuntimeError, np.linalg.LinAlgError):
            continue

    fixed_count = len(map_snapshot.get("landmarks", ()))
    transient_count = len(map_snapshot.get("transient_obstacles", ()))
    if not layered:
        fixed_count = len(map_snapshot.get("obstacles", ()))
    status = (f"CALIBRATED  MAP v{map_snapshot.get('version', 0)}  "
              f"landmarks={fixed_count} transient={transient_count}")
    cv2.putText(output, status, (10, 24), FONT, 0.6,
                (70, 230, 70), 2, cv2.LINE_AA)
    return output
