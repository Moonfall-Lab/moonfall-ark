import unittest

from tests.rover_helpers import CLIENTS, test_params  # noqa: F401

from rover_agent.fleet import Fleet  # noqa: E402
from rover_agent.setup_field import (circle_world, next_rid,  # noqa: E402
                                     rid_for_marker)


class FakeField:
    def __init__(self):
        self.start_count = 0
        self.stop_count = 0
        self.wait_calls = []

    def start(self):
        self.start_count += 1

    def stop(self):
        self.stop_count += 1

    def wait_ready(self, robot_ids, timeout=30.0):
        self.wait_calls.append((list(robot_ids), timeout))
        return True


class FakeRover:
    def __init__(self, rid, _cfg, _params, _field, _obstacle_map, _zones,
                 debug=None):
        self.robot_id = rid
        self.status = "idle"
        self.tick_count = 0
        self.stop_count = 0
        self.close_count = 0
        self.trail = [(0.1, 0.1)]
        self.full_plan = [(0.1, 0.1), (0.9, 0.9)]
        self.plan = []
        self.position = {
            "robot_id": rid, "x": 3.0, "y": 4.0, "theta": 0.0,
            "status": "idle", "fresh": True, "age_ms": 10,
        }
        self.drive = type("Drive", (), {
            "addr": ("127.0.0.1", 8888), "_err_count": 0,
        })()

    def tick(self):
        self.tick_count += 1

    def stop(self):
        self.stop_count += 1
        self.status = "idle"

    def close(self):
        self.close_count += 1


class FleetCoordinatorTest(unittest.TestCase):
    def setUp(self):
        self.field = FakeField()
        self.fleet = Fleet(
            params=test_params(), field=self.field,
            rover_factory=FakeRover, health=False, start=False,
            debug=lambda _message: None,
        )

    def tearDown(self):
        self.fleet.shutdown()

    def test_rover_returns_stable_instance(self):
        self.assertIs(self.fleet.rover("r1"), self.fleet.rover("r1"))
        with self.assertRaises(KeyError):
            self.fleet.rover("r9")

    def test_car_alias_returns_same_vehicle(self):
        self.assertIs(self.fleet.car("r1"), self.fleet.rover("r1"))

    def test_get_position_delegates_to_rover(self):
        self.assertEqual(self.fleet.get_position("r1"),
                         self.fleet.rover("r1").position)

    def test_stop_all_stops_every_rover(self):
        self.fleet.stop_all()
        self.assertEqual(self.fleet.rover("r1").stop_count, 1)
        self.assertEqual(self.fleet.rover("r2").stop_count, 1)

    def test_tick_calls_each_rover_once(self):
        self.fleet.tick()
        self.assertEqual(self.fleet.rover("r1").tick_count, 1)
        self.assertEqual(self.fleet.rover("r2").tick_count, 1)

    def test_wait_ready_delegates_requested_robots(self):
        self.assertTrue(self.fleet.wait_ready(timeout=2.0, robots=["r2"]))
        self.assertEqual(self.field.wait_calls, [(["r2"], 2.0)])

    def test_trails_and_paths_are_aggregated(self):
        self.assertEqual(self.fleet.trails["r1"], [(0.1, 0.1)])
        self.assertEqual(self.fleet.paths["r2"][-1], (0.9, 0.9))

    def test_control_period_comes_from_config(self):
        self.assertEqual(self.fleet.control_period_s, 0.5)

    def test_obstacle_map_updates_only_between_routes(self):
        rock = {"id": "r", "shape": "circle",
                "x_cm": 40, "y_cm": 30, "radius_cm": 5}
        before = self.fleet.get_obstacles()
        changed = self.fleet.upsert_obstacle(rock)
        self.assertEqual(changed["version"], before["version"] + 1)
        self.assertEqual(changed["obstacles"], [dict(rock, x_cm=40.0,
                                                     y_cm=30.0,
                                                     radius_cm=5.0)])
        self.fleet.rover("r1").plan = [(50, 30)]
        with self.assertRaises(RuntimeError):
            self.fleet.remove_obstacle("r")
        self.assertEqual(self.fleet.get_obstacles(), changed)

        self.fleet.rover("r1").plan = []
        self.fleet.rover("r1").status = "approaching"
        with self.assertRaises(RuntimeError):
            self.fleet.replace_transient_obstacles([])

    def test_public_map_interfaces_separate_landmarks_and_transient(self):
        landmark = {"id": "base", "shape": "circle",
                    "x_cm": 40, "y_cm": 30, "radius_cm": 5}
        transient = {"id": "dust", "shape": "circle",
                     "x_cm": 20, "y_cm": 20, "radius_cm": 2}
        self.fleet.replace_landmarks([landmark])
        self.fleet.replace_transient_obstacles([transient])

        self.assertEqual(
            self.fleet.get_landmarks()["landmarks"][0]["id"], "base")
        self.assertEqual(
            self.fleet.get_transient_obstacles()["transient_obstacles"][0]["id"],
            "dust")
        self.assertEqual(len(self.fleet.get_obstacles()["obstacles"]), 2)

        self.fleet.clear_transient_obstacles()
        self.assertEqual(
            self.fleet.get_transient_obstacles()["transient_obstacles"], [])
        self.assertEqual(len(self.fleet.get_landmarks()["landmarks"]), 1)

    def test_shutdown_is_idempotent(self):
        self.fleet.shutdown()
        self.fleet.shutdown()
        self.assertEqual(self.field.stop_count, 1)
        self.assertEqual(self.fleet.rover("r1").close_count, 1)
        self.assertEqual(self.fleet.rover("r2").close_count, 1)


class SetupHelpersTest(unittest.TestCase):
    def test_next_rid_fills_gap(self):
        self.assertEqual(next_rid({}), "r0")
        self.assertEqual(next_rid({"r0": 1}), "r1")
        self.assertEqual(next_rid({"r0": 1, "r2": 1}), "r1")

    def test_car_id_is_derived_directly_from_marker_id(self):
        self.assertEqual([rid_for_marker(mid) for mid in range(4)],
                         ["r0", "r1", "r2", "r3"])
        with self.assertRaises(ValueError):
            rid_for_marker(8)

    def test_circle_world_scales_px(self):
        px_to_world = lambda p: (p[0] * 0.8, p[1] * 0.6)  # noqa: E731
        obs = circle_world(px_to_world, (50, 50), (60, 50), "o1")
        self.assertAlmostEqual(obs["x_cm"], 40)
        self.assertAlmostEqual(obs["y_cm"], 30)
        self.assertAlmostEqual(obs["radius_cm"], 8)

    def test_circle_world_min_radius(self):
        px_to_world = lambda p: (p[0] * 0.1, p[1] * 0.1)  # noqa: E731
        obs = circle_world(px_to_world, (50, 50), (51, 50), "o1")
        self.assertEqual(obs["radius_cm"], 1.0)


if __name__ == "__main__":
    unittest.main()
