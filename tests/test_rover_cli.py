import unittest
from unittest.mock import patch

from tests.rover_helpers import CLIENTS  # noqa: F401

import rover_agent.agent as agent  # noqa: E402


class FakeRover:
    def __init__(self):
        self.goals = []
        self.landmark_goals = []

    def set_goal(self, target, speed=10):
        self.goals.append((target, speed))
        return True

    def set_landmark_goal(self, landmark_id, speed=10):
        self.landmark_goals.append((landmark_id, speed))
        return True


class FakeFleet:
    def __init__(self):
        self.r1 = FakeRover()
        self.stop_all_count = 0
        self.position_calls = []

    def rover(self, rid):
        if rid != "r1":
            raise KeyError(rid)
        return self.r1

    def stop_all(self):
        self.stop_all_count += 1

    def get_position(self, rid):
        self.position_calls.append(rid)
        return {
            "robot_id": rid, "x": 3.0, "y": 4.0, "theta": 0.0,
            "status": "idle", "fresh": True, "age_ms": 5,
        }


class CliCommandParserTest(unittest.TestCase):
    def test_old_move_command_defaults_to_speed_ten(self):
        self.assertEqual(agent.parse_cli_command("r1 3 4"), {
            "action": "move", "robot_id": "r1",
            "x_cm": 3.0, "y_cm": 4.0, "speed": 10,
        })

    def test_move_command_accepts_speed(self):
        self.assertEqual(agent.parse_cli_command("r2 9 2 6"), {
            "action": "move", "robot_id": "r2",
            "x_cm": 9.0, "y_cm": 2.0, "speed": 6,
        })

    def test_landmark_command_accepts_id_and_speed(self):
        self.assertEqual(agent.parse_cli_command("r1 @base 3"), {
            "action": "move_landmark", "robot_id": "r1",
            "landmark_id": "base", "speed": 3,
        })

    def test_position_stop_and_quit_commands(self):
        self.assertEqual(agent.parse_cli_command("p r1"), {
            "action": "position", "robot_id": "r1",
        })
        self.assertEqual(agent.parse_cli_command("s"), {"action": "stop_all"})
        self.assertEqual(agent.parse_cli_command("q"), {"action": "quit"})
        self.assertIsNone(agent.parse_cli_command("   "))

    def test_invalid_command_is_rejected(self):
        for line in ("r1 x 4", "r1 3 4 6.0", "r1 3 4 11", "p", "p r1 extra"):
            with self.subTest(line=line):
                with self.assertRaises(ValueError):
                    agent.parse_cli_command(line)


class PositionFormattingTest(unittest.TestCase):
    def test_fresh_position_is_readable(self):
        text = agent.format_position({
            "robot_id": "r1", "x": 3.0, "y": 4.0, "theta": 1.2,
            "status": "moving", "fresh": True, "age_ms": 42,
        })
        self.assertIn("r1", text)
        self.assertIn("position_cm=(3.000, 4.000)", text)
        self.assertIn("新鲜 42ms", text)

    def test_never_seen_position_is_explicit(self):
        text = agent.format_position({
            "robot_id": "r2", "x": None, "y": None, "theta": None,
            "status": "lost", "fresh": False, "age_ms": None,
        })
        self.assertIn("从未识别", text)

    def test_landmark_position_shows_target_and_surface_gap(self):
        text = agent.format_position({
            "robot_id": "r1", "x": 26.5, "y": 30.0, "theta": 0.0,
            "status": "approaching", "fresh": True, "age_ms": 20,
            "target_landmark_id": "base", "landmark_gap_cm": 1.5,
        })
        self.assertIn("target=base", text)
        self.assertIn("gap=1.500cm", text)


class CliDispatchTest(unittest.TestCase):
    def setUp(self):
        self.fleet = FakeFleet()

    def test_move_dispatches_to_owned_rover(self):
        keep_running = agent.dispatch_cli_command(self.fleet, {
            "action": "move", "robot_id": "r1",
            "x_cm": 3.0, "y_cm": 4.0, "speed": 6,
        })
        self.assertTrue(keep_running)
        self.assertEqual(len(self.fleet.r1.goals), 1)
        target, speed = self.fleet.r1.goals[0]
        self.assertAlmostEqual(target[0], 3.0)
        self.assertAlmostEqual(target[1], 4.0)
        self.assertEqual(speed, 6)

    def test_landmark_dispatches_to_owned_rover(self):
        keep_running = agent.dispatch_cli_command(self.fleet, {
            "action": "move_landmark", "robot_id": "r1",
            "landmark_id": "base", "speed": 3,
        })
        self.assertTrue(keep_running)
        self.assertEqual(self.fleet.r1.landmark_goals, [("base", 3)])

    def test_position_uses_fleet_snapshot(self):
        with patch("builtins.print") as output:
            keep_running = agent.dispatch_cli_command(self.fleet, {
                "action": "position", "robot_id": "r1",
            })
        self.assertTrue(keep_running)
        self.assertEqual(self.fleet.position_calls, ["r1"])
        self.assertIn("position_cm=(3.000, 4.000)", output.call_args.args[0])

    def test_stop_and_quit_have_distinct_scope(self):
        self.assertTrue(agent.dispatch_cli_command(
            self.fleet, {"action": "stop_all"}))
        self.assertEqual(self.fleet.stop_all_count, 1)
        self.assertFalse(agent.dispatch_cli_command(
            self.fleet, {"action": "quit"}))


if __name__ == "__main__":
    unittest.main()
