"""rover_agent 测试共用工具：sys.path 注入、公共参数、合成 ArUco 图像。

约定的合成布局：900x900 画布，四角标记 id 0-3 的中心像素为 CORNER_PX，
对应厘米世界 (0,0)/(80,0)/(80,60)/(0,60)，图像 y 向下。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENTS = ROOT / "backend" / "clients"
if str(CLIENTS) not in sys.path:
    sys.path.insert(0, str(CLIENTS))

CORNER_PX = {0: (100, 800), 1: (800, 800), 2: (800, 100), 3: (100, 100)}


def px_to_world_gt(px):
    """合成布局的真值换算。"""
    return (px[0] - 100) / 700 * 80.0, (800 - px[1]) / 700 * 60.0


def test_params():
    return {
        "table": {"width_cm": 80, "height_cm": 60, "cell_cm": 1},
        "corners": {"marker_ids": [0, 1, 2, 3], "dict": "DICT_4X4_50"},
        "cars": {"dict": "DICT_4X4_50"},
        "robots": {
            "r1": {"ip": "127.0.0.1", "marker_id": 10},
            "r2": {"ip": "127.0.0.1", "marker_id": 11},
        },
        "vision": {"rate_hz": 15, "ema_alpha": 1.0, "stale_sec": 0.5},
        "drive": {"keepalive_period_ms": 250, "command_ttl_ms": 1000},
        "control": {
            "correction_period_ms": 100,
            "min_cruise_pct": 25, "max_cruise_pct": 60,
            "min_turn_pct": 25, "max_turn_pct": 40,
            "k_heading": 40, "turn_enter_rad": 0.9, "turn_exit_rad": 0.25,
            "waypoint_tol_cm": 3, "arrive_tol_cm": 2,
            "landmark_preapproach_gap_cm": 4,
            "landmark_gap_min_cm": 1,
            "landmark_gap_max_cm": 2,
            "landmark_confirm_frames": 2,
            "landmark_creep_speed": 1,
        },
        "landmarks": [],
        "obstacles": [],
        "planner": {"inflate_cells": 1, "connectivity": 8,
                    "robot_radius_cm": 7},
        "bridge": {"rate_hz": 10, "theta_unit": "rad"},
    }


def _gen_marker(mid, size, dict_id=None):
    import cv2
    import numpy as np

    if dict_id is None:
        dict_id = cv2.aruco.DICT_4X4_50
    dictionary = cv2.aruco.getPredefinedDictionary(dict_id)
    try:
        return cv2.aruco.generateImageMarker(dictionary, mid, size)
    except AttributeError:  # OpenCV < 4.7
        img = np.zeros((size, size), dtype="uint8")
        cv2.aruco.drawMarker(dictionary, mid, size, img, 1)
        return img


def paste_marker(canvas, mid, center_px, size=80, angle_deg=0.0, dict_id=None):
    """把标记贴到灰度画布上（带白色静区，可旋转，旋转为图像视觉逆时针）。"""
    import cv2
    import numpy as np

    pad = size // 3
    patch = np.full((size + 2 * pad, size + 2 * pad), 255, dtype="uint8")
    patch[pad:pad + size, pad:pad + size] = _gen_marker(mid, size, dict_id)
    if angle_deg:
        h, w = patch.shape
        rot = cv2.getRotationMatrix2D((w / 2, h / 2), angle_deg, 1.0)
        patch = cv2.warpAffine(patch, rot, (w, h),
                               flags=cv2.INTER_NEAREST, borderValue=255)
    h, w = patch.shape
    x0 = int(center_px[0] - w / 2)
    y0 = int(center_px[1] - h / 2)
    canvas[y0:y0 + h, x0:x0 + w] = patch
    return canvas


def make_frame(markers, size_px=900):
    """markers: [(mid, center_px, angle_deg)] → BGR 合成帧。"""
    import cv2
    import numpy as np

    canvas = np.full((size_px, size_px), 255, dtype="uint8")
    for mid, center, angle in markers:
        paste_marker(canvas, mid, center, angle_deg=angle)
    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
