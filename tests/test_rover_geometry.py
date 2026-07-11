import math
import unittest

from tests.rover_helpers import CLIENTS  # noqa: F401 —— 注入 backend/clients

from rover_agent.geometry import (  # noqa: E402
    Pose, cell_center, dist, heading_error, norm_angle, world_to_cell,
)


class NormAngleTest(unittest.TestCase):
    def test_basic(self):
        self.assertAlmostEqual(norm_angle(0.0), 0.0)
        self.assertAlmostEqual(norm_angle(1.0), 1.0)
        self.assertAlmostEqual(norm_angle(-1.0), -1.0)

    def test_pi_boundary(self):
        # 约定归一化到 (-pi, pi]：±pi 都归到 +pi
        self.assertAlmostEqual(norm_angle(math.pi), math.pi)
        self.assertAlmostEqual(norm_angle(-math.pi), math.pi)
        self.assertAlmostEqual(norm_angle(3 * math.pi), math.pi)
        self.assertAlmostEqual(norm_angle(-3 * math.pi), math.pi)

    def test_wraparound(self):
        self.assertAlmostEqual(norm_angle(2.5 * math.pi), 0.5 * math.pi)
        self.assertAlmostEqual(norm_angle(-2.5 * math.pi), -0.5 * math.pi)


class CellConversionTest(unittest.TestCase):
    def test_cell_floor_and_center(self):
        self.assertEqual(world_to_cell(5.1, 19.9), (5, 19))
        self.assertEqual(world_to_cell(79.9, 0.0), (79, 0))
        cx, cy = cell_center(3, 4)
        self.assertAlmostEqual(cx, 3.5)
        self.assertAlmostEqual(cy, 4.5)


class HeadingErrorTest(unittest.TestCase):
    def _pose(self, theta):
        return Pose(0.0, 0.0, theta, 0.0)

    def test_ahead(self):
        self.assertAlmostEqual(heading_error(self._pose(0.0), (1.0, 0.0)), 0.0)

    def test_left(self):
        self.assertAlmostEqual(heading_error(self._pose(0.0), (0.0, 1.0)),
                               math.pi / 2)

    def test_behind_is_pi(self):
        self.assertAlmostEqual(heading_error(self._pose(0.0), (-1.0, 0.0)),
                               math.pi)

    def test_aligned_nonzero_theta(self):
        self.assertAlmostEqual(heading_error(self._pose(math.pi / 2), (0.0, 1.0)),
                               0.0)

    def test_wrap_shortest_arc(self):
        # 车头 3/4pi，目标方向 -3/4pi：最短修正为 +pi/2（跨 ±pi 边界）
        err = heading_error(self._pose(0.75 * math.pi), (-1.0, -1.0))
        self.assertAlmostEqual(err, 0.5 * math.pi)

    def test_dist(self):
        self.assertAlmostEqual(dist((0, 0), (3, 4)), 5.0)


if __name__ == "__main__":
    unittest.main()
