import math
import unittest

from tests.rover_helpers import CLIENTS  # noqa: F401

from rover_agent.calibrate_straight import (  # noqa: E402
    TrialMeasurement,
    average_pose,
    forward_clearance_cm,
    median_measurement,
    summarize_trial,
)
from rover_agent.geometry import Pose  # noqa: E402


class StraightCalibrationMathTest(unittest.TestCase):
    def test_average_pose_uses_circular_heading_mean(self):
        poses = [
            Pose(10, 20, math.radians(179), 1.0),
            Pose(12, 22, math.radians(-179), 2.0),
        ]
        result = average_pose(poses)
        self.assertAlmostEqual((result.x, result.y), (11, 21))
        self.assertAlmostEqual(abs(math.degrees(result.theta)), 180, delta=0.1)

    def test_trial_summary_reports_speed_and_drift(self):
        start = Pose(10, 10, 0.0, 1.0)
        end = Pose(20, 11, 0.1, 2.0)
        result = summarize_trial(start, end, pulse_sec=1.0)
        self.assertAlmostEqual(result.distance_cm, math.hypot(10, 1))
        self.assertAlmostEqual(result.speed_cm_s, math.hypot(10, 1))
        self.assertAlmostEqual(result.motion_drift_deg,
                               math.degrees(math.atan2(1, 10)))
        self.assertAlmostEqual(result.heading_change_deg,
                               math.degrees(0.1))
        self.assertAlmostEqual(result.lateral_per_20_cm, 2.0, delta=0.02)

    def test_forward_clearance_respects_inner_safety_margin(self):
        self.assertAlmostEqual(
            forward_clearance_cm(Pose(40, 30, 0, 0), 80, 60, margin_cm=5),
            35,
        )
        self.assertAlmostEqual(
            forward_clearance_cm(
                Pose(40, 30, math.pi / 2, 0), 80, 60, margin_cm=5),
            25,
        )

    def test_median_measurement_is_resistant_to_one_bad_trial(self):
        trials = [
            TrialMeasurement(10, 10, 1, 2, 0.5),
            TrialMeasurement(11, 11, 2, 3, 0.8),
            TrialMeasurement(50, 50, 40, 30, 9),
        ]
        result = median_measurement(trials)
        self.assertEqual(result, TrialMeasurement(11, 11, 2, 3, 0.8))


if __name__ == "__main__":
    unittest.main()
