"""摄像头、场地标定与全车位姿的统一感知对象。"""
from __future__ import annotations

import math
import threading
import time

import cv2

from rover_agent.calibration import (Calibrator, aruco_detect,
                                     dict_id_by_name)
from rover_agent.geometry import Pose
from rover_agent.vision import CameraSource, PoseStore, detect_rovers


class FieldTracker:
    """只产生全场位置事实，不知道目标、路线、轮速或 UDP。"""

    def __init__(self, params: dict, camera: int = 0, source=None):
        self.params = params
        self.camera = camera
        self.cell = float(params["table"].get("cell_cm", 1))
        self.calibrator = Calibrator(params)
        self.store = PoseStore(params["vision"]["ema_alpha"],
                               params["vision"]["stale_sec"])
        fallback = params.get("aruco_dict", "DICT_4X4_50")
        cars_dict = dict_id_by_name(
            params.get("cars", {}).get("dict") or fallback)
        corners_dict = dict_id_by_name(
            params["corners"].get("dict") or fallback)
        self.dict_ids = tuple(dict.fromkeys((cars_dict, corners_dict)))
        self.marker_to_robot = {
            int(cfg["marker_id"]): rid
            for rid, cfg in params["robots"].items()
        }
        self.theta_offsets = {
            rid: math.radians(float(cfg.get("theta_offset_deg", 0)))
            for rid, cfg in params["robots"].items()
        }
        self._robot_ids = frozenset(params["robots"])
        self._source = source
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._released = False
        self._lifecycle_lock = threading.Lock()
        self._visual_lock = threading.Lock()
        self._last_frame = None
        self._last_found: dict = {}

    @property
    def calibrated(self) -> bool:
        return self.calibrator.calibrated

    @property
    def source(self):
        return self._source

    def process_frame(self, frame) -> dict[str, Pose]:
        if frame is None:
            return {}
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        found: dict = {}
        for dict_id in self.dict_ids:
            found.update(aruco_detect(gray, dict_id))
        with self._visual_lock:
            self._last_frame = frame
            self._last_found = found
        if not self.calibrated:
            if self.calibrator.calibrate(frame, found=found):
                print("[agent] 标定完成")
            return {}
        poses = detect_rovers(
            frame,
            self.calibrator,
            self.marker_to_robot,
            dict_id=self.dict_ids,
            theta_offsets=self.theta_offsets,
            found=found,
        )
        for rid, pose in poses.items():
            self.store.update(rid, pose)
        return poses

    def get_pose(self, robot_id: str) -> Pose | None:
        self._require_robot(robot_id)
        return self.store.get(robot_id)

    def get_last_pose(self, robot_id: str):
        self._require_robot(robot_id)
        return self.store.last(robot_id)

    def position_snapshot(self, robot_id: str) -> dict:
        pose, age = self.get_last_pose(robot_id)
        result = {
            "robot_id": robot_id,
            "x": None,
            "y": None,
            "theta": None,
            "fresh": False,
            "age_ms": None,
        }
        if pose is None:
            return result
        result.update({
            "x": round(pose.x, 3),
            "y": round(pose.y, 3),
            "theta": round(pose.theta, 4),
            "fresh": age is not None and age <= self.store.stale_sec,
            "age_ms": int(round(age * 1000)) if age is not None else None,
        })
        return result

    def visual_snapshot(self):
        with self._visual_lock:
            return self._last_frame, dict(self._last_found)

    def wait_ready(self, robot_ids, timeout: float = 30.0) -> bool:
        wanted = list(robot_ids)
        for rid in wanted:
            self._require_robot(rid)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.calibrated and all(
                    self.store.get(rid) is not None for rid in wanted):
                return True
            time.sleep(0.1)
        return False

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if self._released:
                raise RuntimeError("FieldTracker 已停止，不能再次启动")
            if self._source is None:
                self._source = CameraSource(self.camera)
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="field-tracker",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lifecycle_lock:
            if self._released:
                return
            self._stop_event.set()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        with self._lifecycle_lock:
            if self._released:
                return
            if self._source is not None:
                self._source.release()
            self._released = True

    def _run(self) -> None:
        period = 1.0 / float(self.params["vision"]["rate_hz"])
        while not self._stop_event.is_set():
            started = time.time()
            frame = self._source.read()
            self.process_frame(frame)
            if frame is None:
                self._stop_event.wait(0.05)
                continue
            spare = period - (time.time() - started)
            if spare > 0:
                self._stop_event.wait(spare)

    def _require_robot(self, robot_id: str) -> None:
        if robot_id not in self._robot_ids:
            raise KeyError(
                f"未知车辆 {robot_id}，params.yaml 里已登记: "
                f"{sorted(self._robot_ids)}")
