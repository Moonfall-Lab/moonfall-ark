"""标定与坐标变换：四角定位标记 → 单应矩阵 H（像素 → 世界厘米）。

四角标记检测 detect_corners 是可插拔边界：现场若换定位物，
只重写该函数（签名不变），Calibrator 与下游全部不动。
默认实现：ArUco DICT_4X4_50。
"""
from __future__ import annotations

import math

import cv2
import numpy as np

DEFAULT_DICT_ID = cv2.aruco.DICT_4X4_50


def dict_id_by_name(name: str) -> int:
    """字典名（如 'DICT_4X4_50'、'DICT_APRILTAG_36h11'）→ OpenCV 常量。"""
    dict_id = getattr(cv2.aruco, name, None)
    if not isinstance(dict_id, int):
        raise ValueError(f"未知 ArUco 字典名: {name}")
    return dict_id


def _get_dictionary(dict_id: int = DEFAULT_DICT_ID):
    return cv2.aruco.getPredefinedDictionary(dict_id)


def aruco_detect(gray, dict_id: int = DEFAULT_DICT_ID) -> dict[int, np.ndarray]:
    """检测所有 ArUco 标记 → {id: 4x2 角点像素（tl,tr,br,bl，标记自身方向）}。

    兼容 OpenCV >=4.7 的 ArucoDetector 与旧版函数式 API。
    """
    dictionary = _get_dictionary(dict_id)
    try:
        detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
        corners, ids, _ = detector.detectMarkers(gray)
    except AttributeError:  # OpenCV < 4.7
        corners, ids, _ = cv2.aruco.detectMarkers(gray, dictionary)
    if ids is None:
        return {}
    out: dict[int, np.ndarray] = {}
    for quad, mid in zip(corners, ids.flatten()):
        out[int(mid)] = quad.reshape(4, 2).astype(np.float64)
    return out


def detect_corners(frame, marker_ids, dict_id: int = DEFAULT_DICT_ID):
    """检测桌面四角标记 → {id: 中心像素 (2,)}；缺任何一角返回 None。"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    found = aruco_detect(gray, dict_id)
    out = {}
    for mid in marker_ids:
        if mid not in found:
            return None
        out[mid] = found[mid].mean(axis=0)
    return out


def compute_homography(px_points, world_points) -> np.ndarray:
    """4+ 组对应点求单应矩阵（像素 → 世界）。"""
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
    """按画面几何自动分配四角标记：画面左下的为原点，再沿画面逆时针排序。

    相机俯视无镜像，画面上的逆时针就是世界逆时针，得到的顺序与
    世界四角 (0,0)→(w,0)→(w,h)→(0,h) 一一对应，坐标系手性正确。
    分配结果由调用方打印，便于现场确认哪个角是原点。
    """
    items = [(mid, float(p[0]), float(p[1])) for mid, p in centers.items()]
    cx = sum(x for _, x, _ in items) / len(items)
    cy = sum(y for _, _, y in items) / len(items)
    # 图像 y 向下，视觉逆时针 = atan2 角递减
    items.sort(key=lambda it: -math.atan2(it[2] - cy, it[1] - cx))
    # 左下 = y-x 最大；平票（菱形布局）取更靠下的
    start = max(range(len(items)),
                key=lambda i: (items[i][2] - items[i][1], items[i][2]))
    ordered = items[start:] + items[:start]
    return [mid for mid, _, _ in ordered]


class Calibrator:
    """持有 H；相机固定时 calibrate 一次即可，viz 里可按键触发重标定。"""

    def __init__(self, params: dict):
        corners_cfg = params["corners"]
        self.marker_ids = list(corners_cfg["marker_ids"])
        self.auto_assign = bool(corners_cfg.get("auto_assign", False))
        dict_name = corners_cfg.get("dict") or params.get("aruco_dict", "DICT_4X4_50")
        self.dict_id = dict_id_by_name(dict_name)
        w = float(params["table"]["width_cm"])
        h = float(params["table"]["height_cm"])
        # 与角标记顺序一一对应：左下 → 右下 → 右上 → 左上
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
                names = ["左下(原点)", "右下", "右上", "左上"]
                print("[calib] 自动角分配: " + "，".join(
                    f"id{mid}→{name}" for mid, name in zip(self.assigned, names)))
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
