"""把 Runtime 游戏配置中的固定地标转换成小车规划地图。"""
from __future__ import annotations

from pathlib import Path

import yaml


def load_runtime_landmarks(config_path: str | Path) -> list[dict]:
    """读取 ``moonfall.yaml`` 的 landmarks，并规范为圆形地图对象。"""
    path = Path(config_path)
    with path.open(encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    result = []
    for item in config.get("landmarks", ()):
        record = {
            "id": str(item["id"]),
            "shape": str(item.get("shape", "circle")),
            "x_cm": float(item["x_cm"]),
            "y_cm": float(item["y_cm"]),
            "radius_cm": float(item["radius_cm"]),
        }
        properties = dict(item.get("properties") or {})
        if item.get("type") is not None:
            properties.setdefault("type", str(item["type"]))
        if properties:
            record["properties"] = properties
        result.append(record)
    return result
