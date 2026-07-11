import math
import unittest

from tests.rover_helpers import (
    CLIENTS,  # noqa: F401
    CORNER_PX,
    make_frame,
    px_to_world_gt,
    test_params,
)

from rover_agent.calibration import Calibrator  # noqa: E402
from rover_agent.geometry import Pose, norm_angle  # noqa: E402
from rover_agent.vision import PoseStore, detect_rovers  # noqa: E402


class VisionSyntheticTest(unittest.TestCase):
    """合成图像端到端：四角标定 + 车顶标记 → 世界位姿（无需相机）。"""

    def setUp(self):
        markers = [(mid, CORNER_PX[mid], 0.0) for mid in range(4)]
        markers.append((10, (450, 450), 0.0))   # r1：标记上边朝图像上方 → θ=π/2
        markers.append((11, (300, 600), 90.0))  # r2：视觉逆时针转 90° → θ=π
        self.frame = make_frame(markers)
        self.calib = Calibrator(test_params())
        self.assertTrue(self.calib.calibrate(self.frame))

    def test_positions(self):
        poses = detect_rovers(self.frame, self.calib, {10: "r1", 11: "r2"})
        self.assertIn("r1", poses)
        self.assertIn("r2", poses)
        for rid, px in (("r1", (450, 450)), ("r2", (300, 600))):
            want = px_to_world_gt(px)
            self.assertAlmostEqual(poses[rid].x, want[0], delta=0.2, msg=rid)
            self.assertAlmostEqual(poses[rid].y, want[1], delta=0.2, msg=rid)

    def test_theta(self):
        poses = detect_rovers(self.frame, self.calib, {10: "r1", 11: "r2"})
        self.assertLess(abs(norm_angle(poses["r1"].theta - math.pi / 2)), 0.15)
        self.assertLess(abs(norm_angle(poses["r2"].theta - math.pi)), 0.15)

    def test_missing_marker_absent(self):
        poses = detect_rovers(self.frame, self.calib, {10: "r1", 99: "ghost"})
        self.assertIn("r1", poses)
        self.assertNotIn("ghost", poses)


class DualDictAutoAssignTest(unittest.TestCase):
    """复刻现场配置：AprilTag 四角乱序 + auto_assign + 4X4 车顶码，双字典共存。"""

    def test_field_configuration_end_to_end(self):
        import cv2
        import numpy as np

        from tests.rover_helpers import paste_marker

        APRIL = cv2.aruco.DICT_APRILTAG_36h11
        canvas = np.full((900, 900), 255, dtype=np.uint8)
        # 与现场一致的乱序摆放：5 左下、4 右下、7 右上、6 左上
        for mid, px in ((5, CORNER_PX[0]), (4, CORNER_PX[1]),
                        (7, CORNER_PX[2]), (6, CORNER_PX[3])):
            paste_marker(canvas, mid, px, size=110, dict_id=APRIL)
        paste_marker(canvas, 10, (450, 450), size=80)  # 车顶 4X4 id10
        frame = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)

        params = test_params()
        params["corners"] = {"dict": "DICT_APRILTAG_36h11",
                             "marker_ids": [4, 5, 6, 7], "auto_assign": True}
        calib = Calibrator(params)
        self.assertTrue(calib.calibrate(frame))
        self.assertEqual(calib.assigned, [5, 4, 7, 6])
        poses = detect_rovers(frame, calib, {10: "r1"},
                              dict_id=cv2.aruco.DICT_4X4_50)
        self.assertIn("r1", poses)
        self.assertAlmostEqual(poses["r1"].x, 40, delta=0.5)
        self.assertAlmostEqual(poses["r1"].y, 30, delta=0.5)


class PoseStoreTest(unittest.TestCase):
    def test_stale(self):
        store = PoseStore(ema_alpha=1.0, stale_sec=0.5)
        store.update("r1", Pose(1.0, 2.0, 0.0, ts=100.0))
        self.assertIsNotNone(store.get("r1", now=100.4))
        self.assertIsNone(store.get("r1", now=100.6))
        self.assertIsNone(store.get("nobody", now=100.0))

    def test_ema_position(self):
        store = PoseStore(ema_alpha=0.5, stale_sec=10)
        store.update("r1", Pose(0.0, 0.0, 0.0, ts=1.0))
        store.update("r1", Pose(1.0, 1.0, 0.0, ts=1.1))
        pose = store.get("r1", now=1.1)
        self.assertAlmostEqual(pose.x, 0.5)
        self.assertAlmostEqual(pose.y, 0.5)

    def test_ema_angle_wrap(self):
        # ±pi 附近的混合必须走最短弧，不能均值到 0
        store = PoseStore(ema_alpha=0.5, stale_sec=10)
        store.update("r1", Pose(0, 0, math.pi - 0.05, ts=1.0))
        store.update("r1", Pose(0, 0, -math.pi + 0.05, ts=1.1))
        pose = store.get("r1", now=1.1)
        self.assertLess(abs(abs(pose.theta) - math.pi), 0.06)


if __name__ == "__main__":
    unittest.main()
