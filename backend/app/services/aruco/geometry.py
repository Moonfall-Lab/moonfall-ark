"""几何与坐标换算。

世界坐标系：原点桌面左下角，x 向右，y 向上，单位厘米。
theta：弧度，x 正方向为 0，逆时针为正，归一化到 (-pi, pi]。
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Pose:
    x: float      # 厘米
    y: float      # 厘米
    theta: float  # 弧度
    ts: float     # 检测时刻


def norm_angle(a: float) -> float:
    a = (a + math.pi) % (2.0 * math.pi) - math.pi
    if a <= -math.pi:
        a += 2.0 * math.pi
    return a
