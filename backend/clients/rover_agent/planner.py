"""占用栅格与 A* 寻路。

障碍三个来源，统一由 build_grid() 汇总：
1. **圆形地图对象（主用）**：固定目标与内存临时障碍的圆心/半径（厘米），
   叠加半车宽与 `safety_clearance_cm` 膨胀后，按"格子矩形与圆精确判交"
   投影到栅格；
2. 游戏配置 map.zones 中 kind ∈ {obstacle, hazard, trap} 且 active 的区域
   （zone center 也是厘米坐标，按规划格膨胀 inflate_cells 圈）；
3. cmd.robot 的 avoid 列表点名的 zone（无论 kind）。

- 8 连通，不允许切角：斜向移动要求两侧直角邻格都空闲。
- plan() 世界坐标进出；起点若落在膨胀区内仍视为可走（先走出来），终点被占则不可达。
"""
from __future__ import annotations

import heapq
import math

from rover_agent.geometry import CELL_CM, cell_center, world_to_cell

OBSTACLE_KINDS = {"obstacle", "hazard", "trap"}
SQRT2 = math.sqrt(2.0)


def vehicle_radius_cm(params: dict) -> float:
    """返回车体中心到最远角的距离；旧配置回退到 robot_radius_cm。"""
    cfg = params.get("planner", {})
    length = cfg.get("vehicle_length_cm")
    width = cfg.get("vehicle_width_cm")
    if length is None or width is None:
        return float(cfg.get("robot_radius_cm", 0.0))
    length, width = float(length), float(width)
    if length <= 0 or width <= 0:
        raise ValueError("vehicle_length_cm/vehicle_width_cm 必须大于 0")
    return math.hypot(length / 2.0, width / 2.0)


def planning_margin_cm(params: dict) -> float:
    """圆障碍的横向外扩：半车宽 + 额外安全距离。

    A* 路径描述车体中心的行驶轨迹；正常通过窄通道时车头沿路线方向，
    因此横向碰撞约束由车宽决定。车长仍用于原地转向和固定目标贴近。
    """
    cfg = params.get("planner", {})
    clearance = float(cfg.get("safety_clearance_cm", 0.0))
    if clearance < 0:
        raise ValueError("safety_clearance_cm 不能小于 0")
    width = cfg.get("vehicle_width_cm")
    if width is None:
        return vehicle_radius_cm(params) + clearance
    width = float(width)
    if width <= 0:
        raise ValueError("vehicle_width_cm 必须大于 0")
    return width / 2.0 + clearance


class OccupancyGrid:
    def __init__(self, nx: int, ny: int | None = None):
        self.nx = int(nx)
        self.ny = int(ny) if ny is not None else self.nx  # 缺省正方形
        self._occ = [[False] * self.ny for _ in range(self.nx)]  # [ix][iy]

    def in_bounds(self, ix: int, iy: int) -> bool:
        return 0 <= ix < self.nx and 0 <= iy < self.ny

    def set_occupied(self, ix: int, iy: int) -> None:
        if self.in_bounds(ix, iy):
            self._occ[ix][iy] = True

    def occupied(self, ix: int, iy: int) -> bool:
        return not self.in_bounds(ix, iy) or self._occ[ix][iy]

    def is_free(self, ix: int, iy: int) -> bool:
        return not self.occupied(ix, iy)

    def add_circle(self, cx: float, cy: float, radius_cm: float,
                   margin_cm: float = 0.0, cell: float = CELL_CM) -> None:
        """圆柱障碍投影到栅格：格子矩形与（半径+margin）的圆有交即占用。

        判交用"圆心到格子矩形最近点"的精确距离，不做半格近似——
        既不漏掉圆边缘擦过的格子，也不多吞一圈通道。
        """
        r = float(radius_cm) + float(margin_cm)
        min_ix = int(math.floor((cx - r) / cell))
        max_ix = int(math.floor((cx + r) / cell))
        min_iy = int(math.floor((cy - r) / cell))
        max_iy = int(math.floor((cy + r) / cell))
        for ix in range(min_ix, max_ix + 1):
            for iy in range(min_iy, max_iy + 1):
                nearest_x = min(max(cx, ix * cell), (ix + 1) * cell)
                nearest_y = min(max(cy, iy * cell), (iy + 1) * cell)
                if math.hypot(nearest_x - cx, nearest_y - cy) <= r:
                    self.set_occupied(ix, iy)

    @classmethod
    def from_zones(cls, nx: int, zones, avoid=(), inflate_cells: int = 1,
                   ny: int | None = None) -> "OccupancyGrid":
        grid = cls(nx, ny)
        avoid_ids = set(avoid or ())
        for zone in zones or ():
            blocked = zone.get("id") in avoid_ids or (
                zone.get("kind") in OBSTACLE_KINDS and zone.get("active", True)
            )
            center = zone.get("center")
            if not blocked or not center:
                continue
            cx, cy = int(round(center[0])), int(round(center[1]))
            r = int(inflate_cells)
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    grid.set_occupied(cx + dx, cy + dy)
        return grid


def _neighbors(grid: OccupancyGrid, ix: int, iy: int, start):
    """8 邻域；斜向禁止切角。start 格视为可离开（起点可能落在膨胀区里）。"""
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = ix + dx, iy + dy
            if not grid.is_free(nx, ny) and (nx, ny) != start:
                continue
            if dx != 0 and dy != 0:  # 斜向：两侧直角格必须空闲
                if not (grid.is_free(ix + dx, iy) and grid.is_free(ix, iy + dy)):
                    continue
            cost = SQRT2 if dx != 0 and dy != 0 else 1.0
            yield (nx, ny), cost


def _octile(a, b) -> float:
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return max(dx, dy) + (SQRT2 - 1.0) * min(dx, dy)


def plan_cells(grid: OccupancyGrid, start: tuple[int, int], goal: tuple[int, int]):
    """A*：格子路径（含起终点）；不可达返回 None。起点占用视为可走出。"""
    if not grid.in_bounds(*goal) or grid.occupied(*goal):
        return None
    if not grid.in_bounds(*start):
        return None
    if start == goal:
        return [start]
    open_heap = [(_octile(start, goal), 0.0, start)]
    g_cost = {start: 0.0}
    came: dict[tuple[int, int], tuple[int, int]] = {}
    while open_heap:
        _, g, cur = heapq.heappop(open_heap)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            path.reverse()
            return path
        if g > g_cost.get(cur, math.inf):
            continue
        for nxt, cost in _neighbors(grid, *cur, start=start):
            ng = g + cost
            if ng < g_cost.get(nxt, math.inf):
                g_cost[nxt] = ng
                came[nxt] = cur
                heapq.heappush(open_heap, (ng + _octile(nxt, goal), ng, nxt))
    return None


def _simplify(cells):
    """合并同方向的连续步，只留拐点。"""
    if len(cells) <= 2:
        return list(cells)
    out = [cells[0]]
    for i in range(1, len(cells) - 1):
        d0 = (cells[i][0] - out[-1][0], cells[i][1] - out[-1][1])
        d1 = (cells[i + 1][0] - cells[i][0], cells[i + 1][1] - cells[i][1])
        # 方向变了才保留（比较归一化方向）
        n0 = max(abs(d0[0]), abs(d0[1])) or 1
        n1 = max(abs(d1[0]), abs(d1[1])) or 1
        if (d0[0] / n0, d0[1] / n0) != (d1[0] / n1, d1[1] / n1):
            out.append(cells[i])
    out.append(cells[-1])
    return out


def plan(grid: OccupancyGrid, start_w, goal_w, cell: float = CELL_CM):
    """世界坐标 → 路径点列表（世界坐标，不含起点，末点为精确目标）；不可达返回 None。

    起点出界时收进最近的界内格子（车被推出场地边缘一点时自己开回来）；
    目标出界仍严格判不可达。
    """
    start = world_to_cell(start_w[0], start_w[1], cell)
    start = (min(max(start[0], 0), grid.nx - 1),
             min(max(start[1], 0), grid.ny - 1))
    goal = world_to_cell(goal_w[0], goal_w[1], cell)
    cells = plan_cells(grid, start, goal)
    if cells is None:
        return None
    waypoints = [cell_center(ix, iy, cell) for ix, iy in _simplify(cells)[1:]]
    if waypoints:
        waypoints[-1] = (float(goal_w[0]), float(goal_w[1]))
    else:  # 起点与终点同格
        waypoints = [(float(goal_w[0]), float(goal_w[1]))]
    return waypoints


def plan_to_landmark(grid: OccupancyGrid, start_w, landmark: dict,
                     robot_radius_cm: float,
                     preapproach_gap_cm: float = 4.0,
                     samples: int = 24,
                     cell: float = CELL_CM):
    """在固定目标外沿采样接近点，返回实际路径最短的 `(路径, 接近点)`。

    目标圆仍保留在占用栅格中；候选点位于车体膨胀边界之外，因此路线
    可以贴近目标，却不会穿过目标本体。
    """
    if samples < 1:
        raise ValueError("samples 必须大于 0")
    cx = float(landmark["x_cm"])
    cy = float(landmark["y_cm"])
    distance = (float(landmark["radius_cm"])
                + float(robot_radius_cm)
                + float(preapproach_gap_cm))
    best = None
    for index in range(samples):
        angle = 2.0 * math.pi * index / samples
        candidate = (cx + distance * math.cos(angle),
                     cy + distance * math.sin(angle))
        waypoints = plan(grid, start_w, candidate, cell=cell)
        if waypoints is None:
            continue
        points = [start_w, *waypoints]
        length = sum(math.hypot(b[0] - a[0], b[1] - a[1])
                     for a, b in zip(points, points[1:]))
        if best is None or length < best[0]:
            best = (length, waypoints, candidate)
    if best is None:
        return None
    return best[1], best[2]


def build_grid(params: dict, zones=(), avoid=(), obstacles=None) -> OccupancyGrid:
    """汇总三类障碍构建栅格（Rover / viz 统一走这里）。

    - obstacles：调用方合并后的固定目标与临时圆形障碍；
      每个叠加半车宽与额外安全距离膨胀；
    - zones / avoid：游戏配置区域与 cmd.robot 点名回避（兼容保留）。
    """
    planner_cfg = params.get("planner", {})
    table = params["table"]
    cell = float(table.get("cell_cm", CELL_CM))
    nx = int(round(float(table["width_cm"]) / cell))
    ny = int(round(float(table["height_cm"]) / cell))
    grid = OccupancyGrid.from_zones(
        nx, zones, avoid, int(planner_cfg.get("inflate_cells", 1)), ny=ny)
    margin = planning_margin_cm(params)
    circles = ((params.get("obstacles") or ())
               if obstacles is None else obstacles)
    for obs in circles:
        grid.add_circle(float(obs["x_cm"]), float(obs["y_cm"]),
                        float(obs["radius_cm"]), margin, cell=cell)
    return grid
