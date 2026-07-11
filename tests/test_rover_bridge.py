import asyncio
import json
import unittest
from unittest.mock import patch

from tests.rover_helpers import CLIENTS  # noqa: F401

from rover_agent.bridge import _receiver, _sender  # noqa: E402
from rover_agent.geometry import Pose  # noqa: E402


class FakeWebSocket:
    def __init__(self, messages=()):
        self.messages = [json.dumps(message) for message in messages]
        self.sent = []

    def __aiter__(self):
        self._iter = iter(self.messages)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def send(self, raw):
        self.sent.append(json.loads(raw))


class FakeRover:
    def __init__(self, rid):
        self.robot_id = rid
        self.goals = []
        self.stop_count = 0
        self.status = "idle"
        self.pose = Pose(30.0, 40.0, 0.25, 0.0)
        self.ack_count = 0
        self.landmark_goals = []
        self.target_landmark = None
        self.landmark_gap_cm = None

    @property
    def position(self):
        return {
            "target_landmark_id": (
                self.target_landmark["id"] if self.target_landmark else None),
            "landmark_gap_cm": self.landmark_gap_cm,
        }

    def set_goal(self, target, avoid=(), speed=10):
        self.goals.append((target, tuple(avoid), speed))
        return True

    def set_landmark_goal(self, landmark_id, avoid=(), speed=10):
        self.landmark_goals.append((landmark_id, tuple(avoid), speed))
        return True

    def stop(self):
        self.stop_count += 1

    def zone_center_world(self, zone):
        return (50.0, 50.0) if zone == "center" else None

    def acknowledge_arrival(self):
        self.ack_count += 1
        if self.status == "arrived":
            self.status = "idle"


class FakeFleet:
    def __init__(self):
        self._rovers = {rid: FakeRover(rid) for rid in ("r1", "r2")}
        self.stop_all_count = 0
        self.transient = []

    @property
    def rovers(self):
        return dict(self._rovers)

    def rover(self, rid):
        if rid not in self._rovers:
            raise KeyError(rid)
        return self._rovers[rid]

    def stop_all(self):
        self.stop_all_count += 1

    def get_landmarks(self):
        return {"version": 3, "landmarks": [
            {"id": "base", "shape": "circle",
             "x_cm": 40.0, "y_cm": 30.0, "radius_cm": 5.0},
        ]}

    def replace_transient_obstacles(self, obstacles):
        self.transient = [dict(item) for item in obstacles]
        return {"version": 4, "transient_obstacles": self.transient}

    def clear_transient_obstacles(self):
        self.transient = []
        return {"version": 5, "transient_obstacles": []}


def command(payload):
    return {"topic": "cmd.robot", "payload": payload}


class BridgeReceiverTest(unittest.TestCase):
    def run_receiver(self, payload):
        ws = FakeWebSocket([command(payload)])
        fleet = FakeFleet()
        pending = {}
        asyncio.run(_receiver(ws, fleet, pending))
        return ws, fleet, pending

    def test_missing_speed_defaults_to_ten(self):
        _, fleet, _ = self.run_receiver({
            "robot_id": "r1", "x": 3, "y": 4, "command_id": "c1",
        })
        target, avoid, speed = fleet.rover("r1").goals[0]
        self.assertEqual((avoid, speed), ((), 10))
        self.assertAlmostEqual(target[0], 3.0)
        self.assertAlmostEqual(target[1], 4.0)

    def test_requested_speed_is_forwarded_to_addressed_rover(self):
        _, fleet, _ = self.run_receiver({
            "robot_id": "r1", "x": 3, "y": 4, "speed": 6,
        })
        self.assertEqual(fleet.rover("r1").goals[-1][-1], 6)
        self.assertEqual(fleet.rover("r2").goals, [])

    def test_car_id_can_address_vehicle_without_robot_id(self):
        _, fleet, _ = self.run_receiver({
            "car_id": "r1", "x": 3, "y": 4, "speed": 3,
        })
        self.assertEqual(fleet.rover("r1").goals[-1], ((3.0, 4.0), (), 3))

    def test_conflicting_car_and_robot_ids_are_rejected(self):
        ws, fleet, _ = self.run_receiver({
            "car_id": "r1", "robot_id": "r2", "x": 3, "y": 4,
        })
        self.assertEqual(fleet.rover("r1").goals, [])
        self.assertEqual(fleet.rover("r2").goals, [])
        self.assertEqual(ws.sent[0]["payload"]["code"],
                         "conflicting_car_id")

    def test_speed_zero_stops_only_addressed_rover_without_target(self):
        _, fleet, pending = self.run_receiver({
            "robot_id": "r1", "speed": 0, "command_id": "c-stop",
        })
        self.assertEqual(fleet.rover("r1").stop_count, 1)
        self.assertEqual(fleet.rover("r2").stop_count, 0)
        self.assertEqual(fleet.stop_all_count, 0)
        self.assertEqual(fleet.rover("r1").goals, [])
        self.assertNotIn("r1", pending)

    def test_invalid_speed_emits_error_and_does_not_plan(self):
        ws, fleet, _ = self.run_receiver({
            "robot_id": "r1", "x": 3, "y": 4,
            "speed": 6.5, "command_id": "bad-speed",
        })
        self.assertEqual(fleet.rover("r1").goals, [])
        self.assertEqual(ws.sent[0]["topic"], "error")
        self.assertEqual(ws.sent[0]["payload"]["code"],
                         "invalid_robot_speed")
        self.assertEqual(ws.sent[0]["payload"]["robot_id"], "r1")

    def test_explicit_stop_action_remains_full_fleet_emergency_stop(self):
        _, fleet, _ = self.run_receiver({"robot_id": "r1", "action": "stop"})
        self.assertEqual(fleet.stop_all_count, 1)
        self.assertEqual(fleet.rover("r1").stop_count, 0)

    def test_zone_goal_is_resolved_by_rover(self):
        _, fleet, _ = self.run_receiver({
            "robot_id": "r2", "target_zone": "center", "speed": 3,
        })
        self.assertEqual(fleet.rover("r2").goals, [((50.0, 50.0), (), 3)])

    def test_landmark_goal_is_forwarded_by_id(self):
        _, fleet, _ = self.run_receiver({
            "robot_id": "r1", "landmark_id": "base", "speed": 2,
        })
        self.assertEqual(
            fleet.rover("r1").landmark_goals, [("base", (), 2)])

    def test_unknown_rover_is_ignored(self):
        ws, fleet, pending = self.run_receiver({
            "robot_id": "r9", "x": 3, "y": 4,
        })
        self.assertEqual(ws.sent, [])
        self.assertEqual(pending, {})
        self.assertTrue(all(not rover.goals
                            for rover in fleet.rovers.values()))


class BridgeSenderTest(unittest.TestCase):
    def test_sender_reads_rover_state_and_acknowledges_arrival(self):
        ws = FakeWebSocket()
        fleet = FakeFleet()
        fleet.rover("r1").status = "arrived"
        fleet.rover("r1").target_landmark = {"id": "base"}
        fleet.rover("r1").landmark_gap_cm = 1.5
        pending = {"r1": "command-1"}

        async def stop_after_one_cycle(_period):
            raise asyncio.CancelledError

        with patch("rover_agent.bridge.asyncio.sleep", stop_after_one_cycle):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(_sender(ws, fleet, 10, "rad", pending))

        pose_messages = [m for m in ws.sent
                         if m["topic"] == "perception.pose"]
        event_messages = [m for m in ws.sent if m["topic"] == "state.event"]
        self.assertEqual(len(pose_messages), 2)
        self.assertEqual(pose_messages[0]["payload"]["x"], 30.0)
        self.assertEqual(pose_messages[0]["payload"]["car_id"], "r1")
        self.assertEqual(event_messages[0]["payload"]["command_id"],
                         "command-1")
        self.assertEqual(event_messages[0]["payload"]["landmark_id"], "base")
        self.assertEqual(event_messages[0]["payload"]["car_id"], "r1")
        self.assertEqual(event_messages[0]["payload"]["landmark_gap_cm"], 1.5)
        self.assertEqual(fleet.rover("r1").ack_count, 1)
        self.assertEqual(fleet.rover("r1").status, "idle")
        self.assertNotIn("r1", pending)


class BridgeMapCommandTest(unittest.TestCase):
    def run_map_command(self, payload):
        ws = FakeWebSocket([{"topic": "cmd.rover_map", "payload": payload}])
        fleet = FakeFleet()
        asyncio.run(_receiver(ws, fleet, {}))
        return ws, fleet

    def test_upper_layer_can_query_fixed_landmarks(self):
        ws, _ = self.run_map_command({"action": "get_landmarks"})
        self.assertEqual(ws.sent[-1]["topic"], "state.rover_map")
        self.assertEqual(
            ws.sent[-1]["payload"]["landmarks"][0]["id"], "base")

    def test_upper_layer_can_replace_and_clear_transient_obstacles(self):
        dust = {"id": "dust", "shape": "circle",
                "x_cm": 20, "y_cm": 20, "radius_cm": 2}
        ws, fleet = self.run_map_command({
            "action": "replace_transient", "obstacles": [dust],
        })
        self.assertEqual(fleet.transient, [dust])
        self.assertEqual(ws.sent[-1]["payload"]["transient_obstacles"], [dust])

        ws, fleet = self.run_map_command({"action": "clear_transient"})
        self.assertEqual(fleet.transient, [])
        self.assertEqual(ws.sent[-1]["payload"]["transient_obstacles"], [])


if __name__ == "__main__":
    unittest.main()
