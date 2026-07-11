import unittest

from tests.rover_helpers import CLIENTS  # noqa: F401

from rover_agent import setup_field  # noqa: E402
from rover_agent.setup_field import (circle_world, next_obstacle_id,  # noqa: E402
                                     parse_obstacle_input)

from tests.rover_helpers import test_params  # noqa: E402


class ObstacleInputTest(unittest.TestCase):
    def test_mouse_and_numeric_input_share_schema(self):
        mouse = circle_world(lambda point: point, (40, 30), (45, 30),
                             obstacle_id="rock-1")
        typed = parse_obstacle_input("rock-1 40 30 5")
        expected = {"id": "rock-1", "shape": "circle",
                    "x_cm": 40.0, "y_cm": 30.0, "radius_cm": 5.0}
        self.assertEqual(mouse, expected)
        self.assertEqual(typed, expected)

    def test_drag_preview_uses_the_same_world_circle_schema(self):
        preview = setup_field.drag_preview_obstacle(
            lambda point: point, (40, 30), (45, 30))
        self.assertEqual(preview, {
            "id": "__preview__", "shape": "circle",
            "x_cm": 40.0, "y_cm": 30.0, "radius_cm": 5.0,
        })

    def test_numeric_input_requires_four_fields(self):
        with self.assertRaises(ValueError):
            parse_obstacle_input("rock-1 40 30")
        with self.assertRaises(ValueError):
            parse_obstacle_input("rock-1 x 30 5")

    def test_next_obstacle_id_fills_first_gap(self):
        records = [{"id": "obstacle-1"}, {"id": "obstacle-3"}]
        self.assertEqual(next_obstacle_id(records), "obstacle-2")

    def test_candidate_validation_rejects_duplicate_id_atomically(self):
        existing = [parse_obstacle_input("rock-1 40 30 5")]
        duplicate = parse_obstacle_input("rock-1 20 20 2.5")
        with self.assertRaisesRegex(ValueError, "id"):
            setup_field.validate_obstacle_candidates(
                test_params(), [*existing, duplicate])
        self.assertEqual(existing, [parse_obstacle_input("rock-1 40 30 5")])

    def test_candidate_validation_rejects_circle_outside_board(self):
        outside = parse_obstacle_input("edge 2 30 5")
        with self.assertRaisesRegex(ValueError, "棋盘"):
            setup_field.validate_obstacle_candidates(test_params(), [outside])

    def test_obstacle_summary_uses_centimeter_fields(self):
        obstacle = parse_obstacle_input("rock-1 40 30 5")
        self.assertEqual(
            setup_field.obstacle_summary(obstacle),
            "rock-1: (40.0,30.0)cm r=5.0cm",
        )


if __name__ == "__main__":
    unittest.main()
