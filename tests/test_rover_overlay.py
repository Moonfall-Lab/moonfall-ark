import unittest

import cv2
import numpy as np

from tests.rover_helpers import CLIENTS  # noqa: F401

from rover_agent.calibration import compute_homography  # noqa: E402
from rover_agent.overlay import (circle_world_points, draw_overlay,  # noqa: E402
                                 project_world_points)


class FakeCalibrator:
    def __init__(self, H):
        self.H = H

    @property
    def calibrated(self):
        return self.H is not None


class FakeRover:
    status = "idle"

    def __init__(self, x, y, theta=0):
        self.pose = type("Pose", (), {"x": x, "y": y,
                                      "theta": theta})()


class OverlayProjectionTest(unittest.TestCase):
    def setUp(self):
        self.H = compute_homography(
            [(100, 500), (700, 520), (760, 80), (80, 100)],
            [(0, 0), (80, 0), (80, 60), (0, 60)],
        )

    def test_world_points_project_back_to_camera(self):
        projected = project_world_points(self.H, [(0, 0), (80, 60)])
        np.testing.assert_allclose(projected[0], (100, 500), atol=1)
        np.testing.assert_allclose(projected[1], (760, 80), atol=1)

    def test_circle_is_sampled_in_world_space(self):
        ring = circle_world_points(40, 30, 5, samples=48)
        self.assertEqual(len(ring), 48)
        radii = [np.hypot(x - 40, y - 30) for x, y in ring]
        self.assertTrue(all(abs(radius - 5) < 1e-6 for radius in radii))

    def test_draw_overlay_returns_changed_copy(self):
        frame = np.zeros((600, 800, 3), np.uint8)
        original = frame.copy()
        snapshot = {
            "version": 2, "width_cm": 80.0, "height_cm": 60.0,
            "cell_cm": 1.0,
            "obstacles": [{"id": "rock", "shape": "circle",
                           "x_cm": 40.0, "y_cm": 30.0,
                           "radius_cm": 5.0}],
        }
        output = draw_overlay(
            frame, FakeCalibrator(self.H), snapshot,
            robot_states={"r1": FakeRover(65, 15)},
            paths={"r1": [(65, 15), (30, 40)]},
            trails={"r1": [(60, 12), (65, 15)]},
            robot_radius_cm=7,
        )
        self.assertTrue(np.array_equal(frame, original))
        self.assertGreater(cv2.countNonZero(cv2.cvtColor(output,
                                                          cv2.COLOR_BGR2GRAY)),
                           100)
        self.assertFalse(np.array_equal(output, original))

    def test_preview_circle_is_projected_instead_of_drawn_in_pixel_space(self):
        frame = np.zeros((600, 800, 3), np.uint8)
        snapshot = {
            "version": 1, "width_cm": 80.0, "height_cm": 60.0,
            "cell_cm": 1.0, "obstacles": [],
        }
        calibrator = FakeCalibrator(self.H)
        without_preview = draw_overlay(frame, calibrator, snapshot)
        with_preview = draw_overlay(
            frame, calibrator, snapshot,
            preview_obstacle={
                "id": "__preview__", "shape": "circle",
                "x_cm": 40.0, "y_cm": 30.0, "radius_cm": 5.0,
            },
        )

        projected = project_world_points(
            self.H, circle_world_points(40, 30, 5))
        spans = np.ptp(projected, axis=0)
        self.assertGreater(abs(float(spans[0] - spans[1])), 2.0)
        self.assertGreater(cv2.countNonZero(cv2.cvtColor(
            cv2.absdiff(with_preview, without_preview),
            cv2.COLOR_BGR2GRAY)), 20)

    def test_fixed_and_transient_obstacles_use_distinct_rendering(self):
        frame = np.zeros((600, 800, 3), np.uint8)
        base = {"version": 1, "width_cm": 80.0, "height_cm": 60.0,
                "cell_cm": 1.0}
        obstacle = {"id": "one", "shape": "circle",
                    "x_cm": 40.0, "y_cm": 30.0, "radius_cm": 5.0}
        fixed = draw_overlay(
            frame, FakeCalibrator(self.H),
            dict(base, landmarks=[obstacle], transient_obstacles=[]))
        transient = draw_overlay(
            frame, FakeCalibrator(self.H),
            dict(base, landmarks=[], transient_obstacles=[obstacle]))
        self.assertFalse(np.array_equal(fixed, transient))


if __name__ == "__main__":
    unittest.main()
