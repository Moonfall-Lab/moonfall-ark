"""车辆位姿检测与 PoseStore。

贴标记约定：车顶 ArUco 标记的"上边缘"朝车头。
theta 的计算在世界坐标系里做：先把标记 4 个角点逐个过单应变换，
再取"上边缘中点 - 中心"的方向向量 —— 镜头畸变与图像 y 翻转全部由 H 吸收，
本模块之后的代码只见世界坐标。
"""
from __future__ import annotations

import math
import threading
import time

import cv2

from rover_agent.calibration import DEFAULT_DICT_ID, Calibrator, aruco_detect
from rover_agent.geometry import Pose, norm_angle


def detect_rovers(
    frame,
    calib: Calibrator,
    marker_to_robot: dict[int, str],
    dict_id=DEFAULT_DICT_ID,
    theta_offsets: dict[str, float] | None = None,
    found: dict | None = None,
) -> dict[str, Pose]:
    """一帧图像 → {robot_id: Pose(世界坐标)}。未检测到的车不出现在结果里。

    dict_id 可为单个字典或字典元组（车顶码与四角码可能不同套，全部扫描）。
    theta_offsets: robot_id → 弧度，车顶码没按"上边朝车头"贴时的固定补偿。
    found: 预先算好的 {marker_id: quad}（调用方已扫过这帧时传入，避免重复检测）。
    """
    if found is None:
        gray = (cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if frame.ndim == 3 else frame)
        dict_ids = (dict_id,) if isinstance(dict_id, int) else tuple(dict_id)
        found = {}
        for did in dict_ids:
            for mid, quad in aruco_detect(gray, did).items():
                found.setdefault(mid, quad)
    now = time.time()
    offsets = theta_offsets or {}
    poses: dict[str, Pose] = {}
    for mid, robot_id in marker_to_robot.items():
        quad = found.get(mid)
        if quad is None:
            continue
        world = [calib.px_to_world(p) for p in quad]  # tl, tr, br, bl
        cx = sum(p[0] for p in world) / 4.0
        cy = sum(p[1] for p in world) / 4.0
        up_x = (world[0][0] + world[1][0]) / 2.0 - cx  # 上边缘中点 - 中心 = 车头方向
        up_y = (world[0][1] + world[1][1]) / 2.0 - cy
        theta = norm_angle(math.atan2(up_y, up_x) + offsets.get(robot_id, 0.0))
        poses[robot_id] = Pose(cx, cy, theta, now)
    return poses


class PoseStore:
    """视觉线程写、控制线程读的最新位姿仓库（含滑动平均与过期判定）。"""

    def __init__(self, ema_alpha: float = 0.5, stale_sec: float = 0.5):
        self.ema_alpha = float(ema_alpha)
        self.stale_sec = float(stale_sec)
        self._poses: dict[str, Pose] = {}
        self._lock = threading.Lock()

    def update(self, robot_id: str, pose: Pose) -> None:
        a = self.ema_alpha
        with self._lock:
            prev = self._poses.get(robot_id)
            # 旧位姿过期就直接覆盖，不做混合——否则标记丢失很久后重现的
            # 第一帧会和几分钟前的位置对半平均，产生瞬时假位姿
            if (prev is not None and a < 1.0
                    and pose.ts - prev.ts <= self.stale_sec):
                pose = Pose(
                    x=a * pose.x + (1 - a) * prev.x,
                    y=a * pose.y + (1 - a) * prev.y,
                    # 角度混合走最短弧，避免 ±pi 处均值跳到 0
                    theta=norm_angle(prev.theta + a * norm_angle(pose.theta - prev.theta)),
                    ts=pose.ts,
                )
            self._poses[robot_id] = pose

    def get(self, robot_id: str, now: float | None = None) -> Pose | None:
        """返回最新位姿；超过 stale_sec 未更新返回 None（上层必须刹车）。"""
        now = time.time() if now is None else now
        with self._lock:
            pose = self._poses.get(robot_id)
        if pose is None or now - pose.ts > self.stale_sec:
            return None
        return pose

    def last(self, robot_id: str, now: float | None = None):
        """含过期位姿：返回 (pose, age_sec)，从未见过则 (None, None)。调试界面用。"""
        now = time.time() if now is None else now
        with self._lock:
            pose = self._poses.get(robot_id)
        return (pose, now - pose.ts) if pose else (None, None)

    def all_fresh(self, now: float | None = None) -> dict[str, Pose]:
        now = time.time() if now is None else now
        with self._lock:
            items = list(self._poses.items())
        return {rid: p for rid, p in items if now - p.ts <= self.stale_sec}


class CameraSource:
    """默认帧源（临时接入用）。正式图像获取逻辑就绪后，替换为任何提供
    read() -> ndarray | None 的对象即可，这是图像获取的插拔边界。"""

    def __init__(self, index: int = 0):
        self.cap = cv2.VideoCapture(index)

    def read(self):
        ok, frame = self.cap.read()
        return frame if ok else None

    def release(self) -> None:
        self.cap.release()
