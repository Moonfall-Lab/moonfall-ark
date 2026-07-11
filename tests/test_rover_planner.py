import math
import unittest

from tests.rover_helpers import CLIENTS, test_params  # noqa: F401

from rover_agent.planner import (  # noqa: E402
    OccupancyGrid, build_grid, plan, plan_cells, plan_to_landmark,
)


def assert_valid_path(testcase, grid, cells, allow_start_occupied=True):
    """逐步校验：步长 1（含斜向）、不踩障碍、斜向不切角。"""
    for i in range(1, len(cells)):
        a, b = cells[i - 1], cells[i]
        dx, dy = b[0] - a[0], b[1] - a[1]
        testcase.assertEqual(max(abs(dx), abs(dy)), 1, f"非法步长 {a}->{b}")
        testcase.assertTrue(grid.is_free(*b), f"路径踩障碍 {b}")
        if dx != 0 and dy != 0:
            testcase.assertTrue(
                grid.is_free(a[0] + dx, a[1]) and grid.is_free(a[0], a[1] + dy),
                f"斜向切角 {a}->{b}")


class PlannerTest(unittest.TestCase):
    def test_straight_line(self):
        grid = OccupancyGrid(12)
        cells = plan_cells(grid, (1, 1), (9, 1))
        self.assertIsNotNone(cells)
        self.assertEqual(cells[0], (1, 1))
        self.assertEqual(cells[-1], (9, 1))
        assert_valid_path(self, grid, cells)

    def test_wall_detour(self):
        grid = OccupancyGrid(12)
        for iy in range(0, 9):  # x=5 的墙，只留 y>=9 的口
            grid.set_occupied(5, iy)
        cells = plan_cells(grid, (1, 1), (9, 1))
        self.assertIsNotNone(cells)
        assert_valid_path(self, grid, cells)
        crossing = [c for c in cells if c[0] == 5]
        self.assertTrue(all(c[1] >= 9 for c in crossing), "必须从缺口绕行")

    def test_unreachable_enclosed(self):
        grid = OccupancyGrid(12)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    grid.set_occupied(6 + dx, 6 + dy)
        self.assertIsNone(plan_cells(grid, (1, 1), (6, 6)))

    def test_goal_occupied(self):
        grid = OccupancyGrid(12)
        grid.set_occupied(6, 6)
        self.assertIsNone(plan_cells(grid, (1, 1), (6, 6)))

    def test_start_inside_inflation_can_escape(self):
        grid = OccupancyGrid(12)
        grid.set_occupied(1, 1)  # 起点本身被膨胀波及
        cells = plan_cells(grid, (1, 1), (5, 5))
        self.assertIsNotNone(cells)
        self.assertEqual(cells[0], (1, 1))

    def test_no_corner_cutting(self):
        grid = OccupancyGrid(12)
        grid.set_occupied(5, 5)
        grid.set_occupied(6, 6)
        cells = plan_cells(grid, (6, 5), (5, 6))
        self.assertIsNotNone(cells)
        assert_valid_path(self, grid, cells)
        self.assertGreater(len(cells), 2, "直穿对角即切角，必须绕行")

    def test_from_zones_inflate_and_avoid(self):
        zones = [
            {"id": "meteor", "kind": "obstacle", "center": [6, 6]},
            {"id": "res", "kind": "resource", "center": [8, 8]},
        ]
        grid = OccupancyGrid.from_zones(12, zones, inflate_cells=1)
        self.assertTrue(grid.occupied(5, 5))
        self.assertTrue(grid.occupied(7, 7))
        self.assertTrue(grid.is_free(4, 6))
        self.assertTrue(grid.is_free(8, 8), "resource 不是障碍")
        grid2 = OccupancyGrid.from_zones(12, zones, avoid=("res",),
                                         inflate_cells=1)
        self.assertTrue(grid2.occupied(8, 8), "avoid 点名的 zone 必须避开")

    def test_inactive_zone_not_blocked(self):
        zones = [{"id": "dust", "kind": "hazard", "center": [3, 3],
                  "active": False}]
        grid = OccupancyGrid.from_zones(12, zones, inflate_cells=1)
        self.assertTrue(grid.is_free(3, 3))

    def test_plan_world_coords(self):
        grid = OccupancyGrid(80, 60)
        waypoints = plan(grid, (15, 15), (75, 55))
        self.assertIsNotNone(waypoints)
        self.assertEqual(waypoints[-1], (75, 55))

    def test_plan_same_cell(self):
        grid = OccupancyGrid(80, 60)
        waypoints = plan(grid, (11.1, 11.1), (11.9, 11.9))
        self.assertEqual(waypoints, [(11.9, 11.9)])

    def test_start_out_of_bounds_clamped(self):
        # 车被推出场地右缘一点：起点收回界内，仍可规划回场
        grid = OccupancyGrid(80, 60)
        waypoints = plan(grid, (81, 29), (25, 50))
        self.assertIsNotNone(waypoints)
        self.assertEqual(waypoints[-1], (25, 50))
        # 目标出界仍不可达
        self.assertIsNone(plan(grid, (50, 50), (81, 29)))


class CircleObstacleTest(unittest.TestCase):
    """写死的圆柱障碍：精确判交栅格化 + 车体膨胀 + 绕行。"""

    def test_rasterize_with_margin(self):
        grid = OccupancyGrid(80, 60)
        grid.add_circle(40, 30, 5, margin_cm=7)
        for cell in [(40, 30), (35, 30), (45, 30), (40, 20), (40, 40)]:
            self.assertTrue(grid.occupied(*cell), f"{cell} 应被占用")
        for cell in [(20, 20), (60, 30), (40, 50)]:
            self.assertTrue(grid.is_free(*cell), f"{cell} 应空闲")

    def test_rasterize_no_margin(self):
        grid = OccupancyGrid(80, 60)
        grid.add_circle(40, 30, 5)
        self.assertTrue(grid.occupied(40, 30))
        self.assertTrue(grid.occupied(44, 30))
        self.assertTrue(grid.is_free(46, 30))

    def test_circle_partially_off_table_ok(self):
        grid = OccupancyGrid(80, 60)
        grid.add_circle(2, 2, 5, margin_cm=7)
        self.assertTrue(grid.occupied(0, 0))
        self.assertTrue(grid.is_free(20, 20))

    def test_build_grid_from_params(self):
        params = test_params()
        params["obstacles"] = [{"id": "c", "shape": "circle",
                                "x_cm": 40, "y_cm": 30, "radius_cm": 5}]
        grid = build_grid(params)
        self.assertTrue(grid.occupied(40, 30))
        self.assertTrue(grid.occupied(30, 30), "应叠加车体半径膨胀")
        self.assertTrue(build_grid(test_params()).is_free(40, 30),
                        "无障碍配置应全空闲")

    def test_build_grid_combines_zones_and_circles(self):
        params = test_params()
        params["obstacles"] = [{"id": "c", "shape": "circle",
                                "x_cm": 40, "y_cm": 30, "radius_cm": 5}]
        zones = [{"id": "meteor", "kind": "obstacle", "center": [20, 45]}]
        grid = build_grid(params, zones)
        self.assertTrue(grid.occupied(40, 30))
        self.assertTrue(grid.occupied(20, 45))

    def test_rect_grid(self):
        params = test_params()
        params["table"] = {"width_cm": 80, "height_cm": 60, "cell_cm": 1}
        grid = build_grid(params)
        self.assertEqual((grid.nx, grid.ny), (80, 60))
        self.assertTrue(grid.in_bounds(79, 59))
        self.assertFalse(grid.in_bounds(79, 60))
        self.assertFalse(grid.in_bounds(80, 59))
        cells = plan_cells(grid, (1, 1), (70, 50))
        self.assertIsNotNone(cells)

    def test_detour_around_cylinder(self):
        grid = OccupancyGrid(80, 60)
        grid.add_circle(40, 30, 5, margin_cm=7)
        cells = plan_cells(grid, (10, 30), (70, 30))
        self.assertIsNotNone(cells)
        assert_valid_path(self, grid, cells)  # 已保证不踩占用格、不切角
        self.assertTrue(any(c[1] != 30 for c in cells),
                        "直线路径被圆柱挡住，必须偏离")

    def test_landmark_goal_stops_at_reachable_preapproach_ring(self):
        landmark = {"id": "base", "shape": "circle",
                    "x_cm": 40, "y_cm": 30, "radius_cm": 5}
        grid = OccupancyGrid(80, 60)
        grid.add_circle(40, 30, 5, margin_cm=7)

        result = plan_to_landmark(
            grid, (5, 5), landmark, robot_radius_cm=7,
            preapproach_gap_cm=4, samples=24)

        self.assertIsNotNone(result)
        waypoints, approach = result
        self.assertEqual(waypoints[-1], approach)
        self.assertAlmostEqual(
            math.hypot(approach[0] - 40, approach[1] - 30),
            16.0, delta=0.01)
        self.assertTrue(grid.is_free(int(approach[0]), int(approach[1])))
        self.assertNotEqual(approach, (40, 30))


if __name__ == "__main__":
    unittest.main()
