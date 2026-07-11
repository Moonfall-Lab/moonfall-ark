import math
import unittest

from tests.rover_helpers import CLIENTS  # noqa: F401

from rover_agent.calibrate_turn import (  # noqa: E402
    TurnMeasurement,
    median_turn_measurement,
    summarize_turn,
)
from rover_agent.geometry import Pose  # noqa: E402


class TurnCalibrationMathTest(unittest.TestCase):
    def test_left_turn_reports_positive_angle_and_rate(self):
        result = summarize_turn(
            Pose(30, 30, 0.0, 1.0),
            Pose(30.2, 29.9, math.radians(30), 2.0),
            pulse_sec=0.3,
        )
        self.assertAlmostEqual(result.angle_deg, 30)
        self.assertAlmostEqual(result.rate_deg_s, 100)
        self.assertAlmostEqual(result.translation_cm, math.hypot(0.2, -0.1))

    def test_right_turn_wraps_across_minus_pi(self):
        result = summarize_turn(
            Pose(30, 30, math.radians(-170), 1.0),
            Pose(30, 30, math.radians(170), 2.0),
            pulse_sec=0.4,
        )
        self.assertAlmostEqual(result.angle_deg, -20)
        self.assertAlmostEqual(result.rate_deg_s, -50)

    def test_median_rejects_one_bad_turn(self):
        values = [
            TurnMeasurement(20, 80, 0.2),
            TurnMeasurement(22, 88, 0.3),
            TurnMeasurement(90, 360, 5.0),
        ]
        self.assertEqual(
            median_turn_measurement(values),
            TurnMeasurement(22, 88, 0.3),
        )


if __name__ == "__main__":
    unittest.main()
