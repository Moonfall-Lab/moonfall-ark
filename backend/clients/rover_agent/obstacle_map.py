"""回合间可更新的圆形障碍地图。"""
from __future__ import annotations

import copy
import json
import math
import threading

from rover_agent.planner import build_grid, planning_margin_cm


class ObstacleMap:
    """原子维护固定目标、临时障碍、地图版本与 1cm 占用栅格。"""

    def __init__(self, params: dict, zones=(), initial=None,
                 landmarks=None, transient=None):
        self.params = params
        self.zones = list(zones or ())
        self.width_cm = float(params["table"]["width_cm"])
        self.height_cm = float(params["table"]["height_cm"])
        self.cell_cm = float(params["table"].get("cell_cm", 1))
        self._lock = threading.RLock()
        self._version = 1
        if initial is not None and landmarks is not None:
            raise ValueError("initial 与 landmarks 不能同时传入")
        fixed = initial if landmarks is None else landmarks
        self._landmarks = self._normalize_all(fixed or ())
        self._transient = self._normalize_all(transient or ())
        self._validate_cross_layer_ids(self._landmarks, self._transient)
        self._grid = self._build(self._landmarks, self._transient)

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot_unlocked()

    def landmarks_snapshot(self) -> dict:
        with self._lock:
            return {
                "version": self._version,
                "landmarks": copy.deepcopy(self._landmarks),
            }

    def transient_snapshot(self) -> dict:
        with self._lock:
            return {
                "version": self._version,
                "transient_obstacles": copy.deepcopy(self._transient),
            }

    def _snapshot_unlocked(self) -> dict:
        landmarks = copy.deepcopy(self._landmarks)
        transient = copy.deepcopy(self._transient)
        return {
            "version": self._version,
            "width_cm": self.width_cm,
            "height_cm": self.height_cm,
            "cell_cm": self.cell_cm,
            "landmarks": landmarks,
            "transient_obstacles": transient,
            # 兼容旧的可视化/调用方；规划也使用这两个层的并集。
            "obstacles": [*landmarks, *transient],
        }

    def grid_for(self, avoid=()):
        avoid = tuple(avoid or ())
        with self._lock:
            if not avoid:
                return self._grid
            records = copy.deepcopy([*self._landmarks, *self._transient])
        return build_grid(self.params, self.zones, avoid, obstacles=records)

    def replace(self, obstacles) -> dict:
        """兼容旧接口：手动绘制的 obstacles 视为固定目标。"""
        return self.replace_landmarks(obstacles)

    def replace_landmarks(self, landmarks) -> dict:
        records = self._normalize_all(landmarks)
        with self._lock:
            self._validate_cross_layer_ids(records, self._transient)
            grid = self._build(records, self._transient)
            self._landmarks = records
            self._grid = grid
            self._version += 1
            return self._snapshot_unlocked()

    def replace_transient(self, obstacles) -> dict:
        records = self._normalize_all(obstacles)
        with self._lock:
            self._validate_cross_layer_ids(self._landmarks, records)
            grid = self._build(self._landmarks, records)
            self._transient = records
            self._grid = grid
            self._version += 1
            return self._snapshot_unlocked()

    def clear_transient(self) -> dict:
        return self.replace_transient([])

    def upsert(self, obstacle) -> dict:
        return self.upsert_landmark(obstacle)

    def upsert_landmark(self, obstacle) -> dict:
        return self._upsert_layer(obstacle, "landmarks")

    def upsert_transient(self, obstacle) -> dict:
        return self._upsert_layer(obstacle, "transient")

    def _upsert_layer(self, obstacle, layer: str) -> dict:
        record = self._normalize(obstacle)
        with self._lock:
            source = (self._landmarks if layer == "landmarks"
                      else self._transient)
            records = copy.deepcopy(source)
        index = next((i for i, item in enumerate(records)
                      if item["id"] == record["id"]), None)
        if index is None:
            records.append(record)
        else:
            records[index] = record
        if layer == "landmarks":
            return self.replace_landmarks(records)
        return self.replace_transient(records)

    def remove(self, obstacle_id: str) -> dict:
        return self.remove_landmark(obstacle_id)

    def remove_landmark(self, obstacle_id: str) -> dict:
        return self._remove_layer(obstacle_id, "landmarks")

    def remove_transient(self, obstacle_id: str) -> dict:
        return self._remove_layer(obstacle_id, "transient")

    def _remove_layer(self, obstacle_id: str, layer: str) -> dict:
        with self._lock:
            source = (self._landmarks if layer == "landmarks"
                      else self._transient)
            records = copy.deepcopy(source)
        kept = [item for item in records if item["id"] != obstacle_id]
        if len(kept) == len(records):
            raise KeyError(f"未知障碍物: {obstacle_id}")
        if layer == "landmarks":
            return self.replace_landmarks(kept)
        return self.replace_transient(kept)

    def get_landmark(self, landmark_id: str) -> dict:
        with self._lock:
            for item in self._landmarks:
                if item["id"] == landmark_id:
                    return copy.deepcopy(item)
        raise KeyError(f"未知固定目标: {landmark_id}")

    def landmark_at(self, point) -> dict | None:
        x, y = float(point[0]), float(point[1])
        with self._lock:
            for item in self._landmarks:
                if math.hypot(x - item["x_cm"],
                              y - item["y_cm"]) <= item["radius_cm"]:
                    return copy.deepcopy(item)
        return None

    def landmark_for_occupied_goal(self, point) -> dict | None:
        """目标所在规划格若被固定目标占用，返回该固定目标。

        判定与 OccupancyGrid.add_circle 一致：固定目标实体半径叠加规划
        外扩距离后，只要圆与目标所在的 1cm 格子相交就命中。临时障碍
        不参与目标匹配，仍然只用于绕行。
        """
        x, y = float(point[0]), float(point[1])
        ix = math.floor(x / self.cell_cm)
        iy = math.floor(y / self.cell_cm)
        if not (0 <= ix < round(self.width_cm / self.cell_cm)
                and 0 <= iy < round(self.height_cm / self.cell_cm)):
            return None
        x0, x1 = ix * self.cell_cm, (ix + 1) * self.cell_cm
        y0, y1 = iy * self.cell_cm, (iy + 1) * self.cell_cm
        margin = planning_margin_cm(self.params)
        with self._lock:
            landmarks = copy.deepcopy(self._landmarks)
        matches = []
        for item in landmarks:
            cx, cy = item["x_cm"], item["y_cm"]
            nearest_x = min(max(cx, x0), x1)
            nearest_y = min(max(cy, y0), y1)
            if math.hypot(nearest_x - cx, nearest_y - cy) <= (
                    item["radius_cm"] + margin):
                surface_gap = math.hypot(x - cx, y - cy) - item["radius_cm"]
                matches.append((surface_gap, item["id"], item))
        return min(matches)[2] if matches else None

    def _build(self, landmarks, transient):
        return build_grid(
            self.params, self.zones,
            obstacles=[dict(item) for item in (*landmarks, *transient)])

    @staticmethod
    def _validate_cross_layer_ids(landmarks, transient) -> None:
        fixed_ids = {item["id"] for item in landmarks}
        duplicate = fixed_ids.intersection(item["id"] for item in transient)
        if duplicate:
            raise ValueError(
                f"固定目标和临时障碍 id 不能重复: {sorted(duplicate)}")

    def _normalize_all(self, obstacles) -> list[dict]:
        records = [self._normalize(item) for item in obstacles]
        ids = [item["id"] for item in records]
        if len(ids) != len(set(ids)):
            raise ValueError("障碍物 id 不能重复")
        return records

    def _normalize(self, obstacle) -> dict:
        obstacle_id = str(obstacle.get("id", "")).strip()
        if not obstacle_id:
            raise ValueError("障碍物 id 不能为空")
        shape = obstacle.get("shape")
        if shape != "circle":
            raise ValueError(f"不支持的障碍物形状: {shape}")
        try:
            x = float(obstacle["x_cm"])
            y = float(obstacle["y_cm"])
            radius = float(obstacle["radius_cm"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("x_cm/y_cm/radius_cm 必须是数字") from exc
        if not all(math.isfinite(value) for value in (x, y, radius)):
            raise ValueError("障碍物坐标和半径必须是有限数字")
        if radius <= 0:
            raise ValueError("radius_cm 必须大于 0")
        if (x - radius < 0 or x + radius > self.width_cm
                or y - radius < 0 or y + radius > self.height_cm):
            raise ValueError("圆形障碍物必须完整位于棋盘内")
        record = {"id": obstacle_id, "shape": "circle",
                  "x_cm": x, "y_cm": y, "radius_cm": radius}
        if "properties" in obstacle:
            properties = obstacle["properties"]
            if not isinstance(properties, dict):
                raise ValueError("properties 必须是对象")
            try:
                json.dumps(properties, ensure_ascii=False, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise ValueError("properties 必须可以编码为 JSON") from exc
            record["properties"] = copy.deepcopy(properties)
        return record
