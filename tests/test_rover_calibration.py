import unittest

import numpy as np

from tests.rover_helpers import (
    CLIENTS,  # noqa: F401
    CORNER_PX,
    make_frame,
    px_to_world_gt,
    test_params,
)

from rover_agent.calibration import (  # noqa: E402
    Calibrator, apply_h, assign_corners, compute_homography, detect_corners,
)


class HomographyMathTest(unittest.TestCase):
    # 已知真值单应（像素 → 世界，带轻微透视项）
    H_PW = np.array([
        [0.002, 1.0e-5, -0.2],
        [2.0e-5, -0.0021, 1.7],
        [1.0e-6, -2.0e-6, 1.0],
    ])

    def test_recover_and_fifth_point(self):
        px_pts = [(100, 800), (820, 780), (830, 90), (90, 110)]
        world_pts = [apply_h(self.H_PW, p) for p in px_pts]
        H = compute_homography(px_pts, world_pts)
        # 第 5、6 个点（含标定四边形外的外推点）误差 < 1mm
        for probe in [(450, 450), (50, 900)]:
            got = apply_h(H, probe)
            want = apply_h(self.H_PW, probe)
            self.assertAlmostEqual(got[0], want[0], delta=1e-3)
            self.assertAlmostEqual(got[1], want[1], delta=1e-3)


class DetectCornersTest(unittest.TestCase):
    def test_blank_returns_none(self):
        blank = np.full((400, 400, 3), 255, dtype=np.uint8)
        self.assertIsNone(detect_corners(blank, [0, 1, 2, 3]))

    def test_missing_one_corner_returns_none(self):
        frame = make_frame([(mid, CORNER_PX[mid], 0.0) for mid in (0, 1, 2)])
        self.assertIsNone(detect_corners(frame, [0, 1, 2, 3]))


class CalibratorTest(unittest.TestCase):
    def setUp(self):
        self.frame = make_frame([(mid, CORNER_PX[mid], 0.0) for mid in range(4)])
        self.calib = Calibrator(test_params())

    def test_not_calibrated_raises(self):
        with self.assertRaises(RuntimeError):
            self.calib.px_to_world((0, 0))

    def test_calibrate_and_transform(self):
        self.assertTrue(self.calib.calibrate(self.frame))
        # 角点自检
        x, y = self.calib.px_to_world(CORNER_PX[1])
        self.assertAlmostEqual(x, 80.0, delta=0.5)
        self.assertAlmostEqual(y, 0.0, delta=0.5)
        # 中央任意点对照真值换算
        got = self.calib.px_to_world((450, 450))
        want = px_to_world_gt((450, 450))
        self.assertAlmostEqual(got[0], want[0], delta=0.5)
        self.assertAlmostEqual(got[1], want[1], delta=0.5)

    def test_reset(self):
        self.assertTrue(self.calib.calibrate(self.frame))
        self.calib.reset()
        self.assertFalse(self.calib.calibrated)


class AssignCornersTest(unittest.TestCase):
    def test_geometric_assignment(self):
        # 画面：7 在左下、4 在右下、5 在右上、6 在左上
        centers = {4: (800, 800), 5: (800, 100), 6: (100, 100), 7: (100, 800)}
        self.assertEqual(assign_corners(centers), [7, 4, 5, 6])

    def test_rotated_layout(self):
        centers = {10: (450, 850), 11: (850, 450), 12: (450, 50), 13: (50, 450)}
        # 左下（y-x 最大）= id10，逆时针 → 11(右) → 12(上) → 13(左)
        self.assertEqual(assign_corners(centers), [10, 11, 12, 13])

    def test_auto_assign_calibration(self):
        # 故意把 id 2 摆在画面左下：auto_assign 应把它当原点
        frame = make_frame([(2, CORNER_PX[0], 0.0), (3, CORNER_PX[1], 0.0),
                            (0, CORNER_PX[2], 0.0), (1, CORNER_PX[3], 0.0)])
        params = test_params()
        params["corners"]["auto_assign"] = True
        calib = Calibrator(params)
        self.assertTrue(calib.calibrate(frame))
        self.assertEqual(calib.assigned[0], 2)
        x, y = calib.px_to_world(CORNER_PX[0])  # 画面左下那张 → 世界原点
        self.assertAlmostEqual(x, 0.0, delta=0.5)
        self.assertAlmostEqual(y, 0.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
