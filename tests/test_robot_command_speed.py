import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.models.commands import RobotCommand  # noqa: E402


def make_command(**overrides):
    data = {"command_id": "c1", "robot_id": "r1", "action": "collect"}
    data.update(overrides)
    return RobotCommand(**data)


class RobotCommandSpeedContractTest(unittest.TestCase):
    def test_default_speed_is_ten(self):
        self.assertEqual(make_command().speed, 10)

    def test_integer_levels_zero_to_ten_are_allowed(self):
        for value in (0, 1, 6, 10):
            with self.subTest(value=value):
                self.assertEqual(make_command(speed=value).speed, value)

    def test_non_integer_or_out_of_range_speed_is_rejected(self):
        for value in (-1, 11, 6.5, True, "6"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    make_command(speed=value)


if __name__ == "__main__":
    unittest.main()
