import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from moonfall_runtime.state import GameState  # noqa: E402
from moonfall_runtime.targeting import choose_target  # noqa: E402


class TargetingTest(unittest.TestCase):
    def test_energy_priority_selects_nearest_available_energy_target(self):
        state = GameState.initial()
        decision = choose_target(state, "p1", "energy_priority")

        self.assertIsNotNone(decision)
        self.assertEqual(decision.unit_id, "r0")
        self.assertEqual(decision.landmark.id, "obstacle-1")
        self.assertEqual(state.units["r0"].target.id, "obstacle-1")
        self.assertEqual(state.units["r0"].status, "moving")

    def test_explore_relic_selects_nearest_available_relic(self):
        state = GameState.initial()
        decision = choose_target(state, "p2", "explore_relic")

        self.assertIsNotNone(decision)
        self.assertEqual(decision.unit_id, "r1")
        self.assertEqual(decision.landmark.id, "obstacle-2")

    def test_skips_empty_targets(self):
        state = GameState.initial()
        state.landmarks["obstacle-2"].relic_cards = 0
        state.landmarks["obstacle-4"].relic_cards = 0

        self.assertIsNone(choose_target(state, "p1", "explore_relic"))

    def test_frontend_state_contains_target_and_stock(self):
        state = GameState.initial()
        choose_target(state, "p1", "energy_priority")
        world = state.world_for_frontend()

        unit = next(item for item in world["units"] if item["id"] == "r0")
        self.assertEqual(unit["target"]["landmark_id"], "obstacle-1")
        zone = next(item for item in world["zones"] if item["id"] == "obstacle-3")
        self.assertEqual(zone["fuel_blocks"], 3)

    def test_initial_rover_positions_are_middle_edges(self):
        state = GameState.initial()

        self.assertEqual(state.units["r0"].pose.x_cm, 5.0)
        self.assertEqual(state.units["r0"].pose.y_cm, 30.0)
        self.assertEqual(state.units["r1"].pose.x_cm, 75.0)
        self.assertEqual(state.units["r1"].pose.y_cm, 30.0)

    def test_does_not_select_same_landmark_twice_when_alternative_exists(self):
        state = GameState.initial()
        state.last_landmark_id = "obstacle-3"

        decision = choose_target(state, "p1", "energy_priority")

        self.assertIsNotNone(decision)
        self.assertNotEqual(decision.landmark.id, "obstacle-3")

    def test_updates_heart_rate_and_stress(self):
        state = GameState.initial()

        result = state.update_heart_rate("p1", 100)
        world = state.world_for_frontend()
        pa = next(item for item in world["factions"] if item["id"] == "pa")

        self.assertEqual(result["heart_rate"], 100)
        self.assertEqual(result["stress"], 0.5)
        self.assertEqual(pa["vars"]["heart_rate"], 100)
        self.assertEqual(pa["vars"]["stress"], 0.5)


if __name__ == "__main__":
    unittest.main()
