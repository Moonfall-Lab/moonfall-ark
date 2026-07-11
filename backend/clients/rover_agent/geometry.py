"""几何与坐标换算（纯函数，全部可单元测试）。

世界坐标系：原点桌面左下角，x 向右，y 向上，单位厘米。
theta：弧度，x 正方向为 0，逆时针为正，归一化到 (-pi, pi]。
规划栅格默认每格 1cm。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

CELL_CM = 1.0


@dataclass
class Pose:
    x: float      # 厘米
    y: float      # 厘米
    theta: float  # 弧度
    ts: float     # 检测时刻 time.time()


def norm_angle(a: float) -> float:
    """角度归一化到 (-pi, pi]。"""
    a = (a + math.pi) % (2.0 * math.pi) - math.pi
    if a <= -math.pi:
        a += 2.0 * math.pi
    return a


def world_to_cell(x: float, y: float, cell: float = CELL_CM) -> tuple[int, int]:
    return int(math.floor(x / cell)), int(math.floor(y / cell))


def cell_center(ix: int, iy: int, cell: float = CELL_CM) -> tuple[float, float]:
    return (ix + 0.5) * cell, (iy + 0.5) * cell


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def heading_error(pose: Pose, target: tuple[float, float]) -> float:
    """车头指向 target 所需的修正角，逆时针为正。"""
    desired = math.atan2(target[1] - pose.y, target[0] - pose.x)
    return norm_angle(desired - pose.theta)
