import unittest

from tests.rover_helpers import CLIENTS  # noqa: F401 -- inject backend/clients

from rover_agent.card_navigation import (  # noqa: E402
    CardPresentationGate, Destination, select_destination,
)


class DestinationSelectionTest(unittest.TestCase):
    def test_explore_relic_selects_nearest_ruin(self):
        self.assertEqual(
            select_destination("探索遗迹", 60.0, 50.0),
            Destination("obstacle-2", 61.51, 51.09),
        )

    def test_collect_priority_selects_nearest_resource(self):
        self.assertEqual(
            select_destination("采集优先", 60.0, 14.0),
            Destination("obstacle-5", 61.83, 13.90),
        )

    def test_english_aliases_select_the_same_destinations(self):
        self.assertEqual(
            select_destination("explore_relic", 10.0, 10.0),
            Destination("obstacle-4", 12.71, 10.16),
        )
        self.assertEqual(
            select_destination("collect_priority", 20.0, 50.0),
            Destination("obstacle-1", 19.22, 52.58),
        )

    def test_unsupported_cards_do_not_select_a_destination(self):
        self.assertIsNone(select_destination("返航结算", 0.0, 0.0))
        self.assertIsNone(select_destination("unknown", 0.0, 0.0))

    def test_equal_distance_uses_destination_list_order(self):
        self.assertEqual(
            select_destination("探索遗迹", 37.11, 30.625),
            Destination("obstacle-2", 61.51, 51.09),
        )


class CardPresentationGateTest(unittest.TestCase):
    def test_card_can_trigger_again_only_after_five_absent_observations(self):
        gate = CardPresentationGate()

        self.assertEqual(gate.observe(["探索遗迹"]), ["探索遗迹"])
        self.assertEqual(gate.observe(["探索遗迹"]), [])
        for _ in range(4):
            self.assertEqual(gate.observe([]), [])
        self.assertEqual(gate.observe([]), [])
        self.assertEqual(gate.observe(["探索遗迹"]), ["探索遗迹"])


if __name__ == "__main__":
    unittest.main()
