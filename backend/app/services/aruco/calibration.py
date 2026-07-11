"""标定与坐标变换：四角定位标记 → 单应矩阵 H（像素 → 世界厘米）。

桌面四角贴 ArUco 标记，校准后得到单应矩阵，摄像头坐标自动转为世界坐标。
"""
from __future__ import annotations

import math

import cv2
import numpy as np

DEFAULT_DICT_ID = cv2.aruco.DICT_4X4_50


def dict_id_by_name(name: str) -> int:
    dict_id = getattr(cv2.aruco, name, None)
    if not isinstance(dict_id, int):
        raise ValueError(f"未知 ArUco 字典名: {name}")
    return dict_id


def _get_dictionary(dict_id: int = DEFAULT_DICT_ID):
    return cv2.aruco.getPredefinedDictionary(dict_id)


def aruco_detect(gray, dict_id: int = DEFAULT_DICT_ID) -> dict[int, np.ndarray]:
    dictionary = _get_dictionary(dict_id)
    try:
        detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
        corners, ids, _ = detector.detectMarkers(gray)
    except AttributeError:
        corners, ids, _ = cv2.aruco.detectMarkers(gray, dictionary)
    if ids is None:
        return {}
    out: dict[int, np.ndarray] = {}
    for quad, mid in zip(corners, ids.flatten()):
        out[int(mid)] = quad.reshape(4, 2).astype(np.float64)
    return out


def detect_corners(frame, marker_ids, dict_id: int = DEFAULT_DICT_ID):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    found = aruco_detect(gray, dict_id)
    out = {}
    for mid in marker_ids:
        if mid not in found:
            return None
        out[mid] = found[mid].mean(axis=0)
    return out


def compute_homography(px_points, world_points) -> np.ndarray:
    src = np.asarray(px_points, dtype=np.float64).reshape(-1, 1, 2)
    dst = np.asarray(world_points, dtype=np.float64).reshape(-1, 1, 2)
    H, _ = cv2.findHomography(src, dst, 0)
    if H is None:
        raise ValueError("findHomography 失败：对应点退化（共线或重复）")
    return H


def apply_h(H: np.ndarray, pt) -> tuple[float, float]:
    src = np.asarray([[pt]], dtype=np.float64)
    out = cv2.perspectiveTransform(src, H)
    return float(out[0, 0, 0]), float(out[0, 0, 1])


def assign_corners(centers: dict) -> list:
    items = [(mid, float(p[0]), float(p[1])) for mid, p in centers.items()]
    cx = sum(x for _, x, _ in items) / len(items)
    cy = sum(y for _, _, y in items) / len(items)
    items.sort(key=lambda it: -math.atan2(it[2] - cy, it[1] - cx))
    start = max(range(len(items)),
                key=lambda i: (items[i][2] - items[i][1], items[i][2]))
    ordered = items[start:] + items[:start]
    return [mid for mid, _, _ in ordered]


class Calibrator:
    def __init__(self, params: dict):
        corners_cfg = params["corners"]
        self.marker_ids = list(corners_cfg["marker_ids"])
        self.auto_assign = bool(corners_cfg.get("auto_assign", False))
        dict_name = corners_cfg.get("dict") or params.get("aruco_dict", "DICT_4X4_50")
        self.dict_id = dict_id_by_name(dict_name)
        w = float(params["table"]["width_cm"])
        h = float(params["table"]["height_cm"])
        self.world_pts = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]
        self.H: np.ndarray | None = None
        self.assigned: list | None = None

    @property
    def calibrated(self) -> bool:
        return self.H is not None

    def calibrate(self, frame, found: dict | None = None) -> bool:
        if found is None:
            centers = detect_corners(frame, self.marker_ids, self.dict_id)
            if centers is None:
                return False
        else:
            if any(mid not in found for mid in self.marker_ids):
                return False
            centers = {mid: found[mid].mean(axis=0) for mid in self.marker_ids}
        if self.auto_assign:
            if self.assigned is None:
                self.assigned = assign_corners(centers)
            order = self.assigned
        else:
            order = self.marker_ids
        px = [centers[mid] for mid in order]
        self.H = compute_homography(px, self.world_pts)
        return True

    def reset(self) -> None:
        self.H = None
        self.assigned = None

    def px_to_world(self, px) -> tuple[float, float]:
        if self.H is None:
            raise RuntimeError("尚未标定：先调用 calibrate()")
        return apply_h(self.H, px)
