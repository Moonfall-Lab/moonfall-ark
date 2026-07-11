import math
import unittest

from tests.rover_helpers import CLIENTS, test_params  # noqa: F401

from rover_agent.obstacle_map import ObstacleMap  # noqa: E402


ROCK = {"id": "rock-1", "shape": "circle",
        "x_cm": 40, "y_cm": 30, "radius_cm": 5}
SMALL = {"id": "rock-2", "shape": "circle",
         "x_cm": 20, "y_cm": 20, "radius_cm": 2.5}


class ObstacleMapTest(unittest.TestCase):
    def setUp(self):
        self.map = ObstacleMap(test_params(), initial=[ROCK])

    def test_initial_snapshot_and_grid(self):
        snapshot = self.map.snapshot()
        self.assertEqual(snapshot["version"], 1)
        self.assertEqual(snapshot["width_cm"], 80)
        self.assertEqual(snapshot["height_cm"], 60)
        self.assertEqual(snapshot["cell_cm"], 1)
        self.assertEqual(snapshot["obstacles"][0]["x_cm"], 40.0)
        self.assertTrue(self.map.grid_for().occupied(40, 30))

    def test_replace_is_atomic(self):
        before = self.map.snapshot()
        with self.assertRaises(ValueError):
            self.map.replace([ROCK, dict(ROCK)])
        self.assertEqual(self.map.snapshot(), before)

    def test_upsert_and_remove_increment_version(self):
        self.map.upsert(SMALL)
        self.assertEqual(self.map.snapshot()["version"], 2)
        self.assertEqual(len(self.map.snapshot()["obstacles"]), 2)
        self.map.remove("rock-2")
        self.assertEqual(self.map.snapshot()["version"], 3)
        self.assertEqual(len(self.map.snapshot()["obstacles"]), 1)

    def test_snapshot_is_detached(self):
        snapshot = self.map.snapshot()
        snapshot["obstacles"][0]["x_cm"] = 1
        self.assertEqual(self.map.snapshot()["obstacles"][0]["x_cm"], 40.0)

    def test_optional_properties_survive_and_snapshot_is_deeply_detached(self):
        record = dict(ROCK, properties={"type": "resource",
                                       "tags": ["blue"]})
        obstacle_map = ObstacleMap(test_params(), landmarks=[record])
        snapshot = obstacle_map.landmarks_snapshot()
        self.assertEqual(snapshot["landmarks"][0]["properties"]["type"],
                         "resource")
        snapshot["landmarks"][0]["properties"]["tags"].append("changed")
        self.assertEqual(
            obstacle_map.landmarks_snapshot()["landmarks"][0]
            ["properties"]["tags"], ["blue"])

    def test_unknown_remove_is_rejected(self):
        with self.assertRaises(KeyError):
            self.map.remove("missing")

    def test_invalid_records_are_rejected(self):
        invalid = [
            dict(ROCK, id=""),
            dict(ROCK, shape="square"),
            dict(ROCK, radius_cm=0),
            dict(ROCK, x_cm=math.nan),
            dict(ROCK, x_cm=2, radius_cm=5),
            dict(ROCK, y_cm=59, radius_cm=2),
            dict(ROCK, properties="not-an-object"),
            dict(ROCK, properties={"bad": {1, 2}}),
        ]
        for record in invalid:
            with self.subTest(record=record):
                with self.assertRaises(ValueError):
                    self.map.replace([record])

    def test_avoid_zone_builds_temporary_grid(self):
        params = test_params()
        zones = [{"id": "resource", "kind": "resource", "center": [10, 10]}]
        obstacle_map = ObstacleMap(params, zones=zones, initial=[])
        self.assertTrue(obstacle_map.grid_for().is_free(10, 10))
        self.assertTrue(obstacle_map.grid_for(["resource"]).occupied(10, 10))

    def test_fixed_and_transient_layers_are_distinct_but_plan_together(self):
        snapshot = self.map.replace_transient([SMALL])
        self.assertEqual(snapshot["landmarks"], [
            dict(ROCK, x_cm=40.0, y_cm=30.0, radius_cm=5.0),
        ])
        self.assertEqual(snapshot["transient_obstacles"], [
            dict(SMALL, x_cm=20.0, y_cm=20.0, radius_cm=2.5),
        ])
        self.assertEqual(len(snapshot["obstacles"]), 2)
        grid = self.map.grid_for()
        self.assertTrue(grid.occupied(40, 30))
        self.assertTrue(grid.occupied(20, 20))

    def test_target_lookup_only_matches_fixed_landmarks(self):
        self.map.replace_transient([SMALL])
        self.assertEqual(self.map.landmark_at((40, 30))["id"], "rock-1")
        self.assertIsNone(self.map.landmark_at((20, 20)))
        self.assertEqual(self.map.get_landmark("rock-1")["radius_cm"], 5.0)
        with self.assertRaises(KeyError):
            self.map.get_landmark("rock-2")

    def test_goal_in_fixed_landmark_occupied_cell_matches_landmark(self):
        # 点在实体圆外，但其 1cm 规划格与膨胀后的固定障碍相交。
        self.assertEqual(
            self.map.landmark_for_occupied_goal((47.5, 30))["id"],
            "rock-1",
        )

    def test_transient_occupied_cell_never_becomes_goal_landmark(self):
        self.map.replace_transient([SMALL])
        self.assertIsNone(self.map.landmark_for_occupied_goal((20, 20)))

    def test_transient_updates_do_not_mutate_fixed_landmarks(self):
        before = self.map.landmarks_snapshot()["landmarks"]
        self.map.replace_transient([SMALL])
        self.map.clear_transient()
        self.assertEqual(self.map.landmarks_snapshot()["landmarks"], before)
        self.assertEqual(self.map.transient_snapshot()["transient_obstacles"], [])


if __name__ == "__main__":
    unittest.main()
