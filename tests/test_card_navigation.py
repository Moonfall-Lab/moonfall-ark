import unittest

from tests.rover_helpers import CLIENTS  # noqa: F401 -- inject backend/clients

from rover_agent.card_navigation import (  # noqa: E402
    CardNavigationController, CardPresentationGate, Destination,
    select_destination,
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


class _FakeField:
    def __init__(self, calibrated=True):
        self.calibrated = calibrated


class _FakeRover:
    def __init__(self):
        self.goals = []

    def set_goal(self, target, speed):
        self.goals.append((target, speed))


class _FakeFleet:
    def __init__(self, *, calibrated=True, fresh=True, x=40.0, y=30.0):
        self.field = _FakeField(calibrated)
        self._fresh = fresh
        self._position = {"fresh": fresh, "x": x, "y": y}
        self._rover = _FakeRover()

    def get_position(self, rover_id):
        self.assert_rover_id(rover_id)
        return self._position

    def rover(self, rover_id):
        self.assert_rover_id(rover_id)
        return self._rover

    @staticmethod
    def assert_rover_id(rover_id):
        if rover_id != "r0":
            raise AssertionError(f"unexpected rover {rover_id}")


class CardNavigationControllerTest(unittest.TestCase):
    def test_new_supported_card_commands_r0_at_speed_three(self):
        fleet = _FakeFleet(x=40.0, y=30.0)
        chosen = CardNavigationController(fleet).observe({"采集优先"})

        self.assertEqual(chosen, Destination("obstacle-3", 37.37, 29.88))
        self.assertEqual(fleet._rover.goals, [((37.37, 29.88), 3)])

    def test_card_is_not_consumed_before_field_is_ready(self):
        fleet = _FakeFleet(calibrated=False)
        controller = CardNavigationController(fleet)

        self.assertIsNone(controller.observe({"探索遗迹"}))
        fleet.field.calibrated = True
        chosen = controller.observe({"探索遗迹"})

        self.assertEqual(chosen, Destination("obstacle-2", 61.51, 51.09))

    def test_stale_pose_does_not_command_a_rover(self):
        fleet = _FakeFleet(fresh=False)

        self.assertIsNone(CardNavigationController(fleet).observe({"采集优先"}))
        self.assertEqual(fleet._rover.goals, [])

    def test_same_visible_card_is_not_reissued_until_missing_five_times(self):
        fleet = _FakeFleet()
        controller = CardNavigationController(fleet)

        controller.observe({"探索遗迹"})
        controller.observe({"探索遗迹"})
        self.assertEqual(len(fleet._rover.goals), 1)
        for _ in range(5):
            controller.observe(set())
        controller.observe({"探索遗迹"})
        self.assertEqual(len(fleet._rover.goals), 2)


if __name__ == "__main__":
    unittest.main()
