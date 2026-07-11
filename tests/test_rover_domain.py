import importlib.util
import math
import time
import unittest
from unittest.mock import patch

from tests.rover_helpers import CLIENTS, test_params  # noqa: F401

from rover_agent.geometry import Pose  # noqa: E402
from rover_agent.obstacle_map import ObstacleMap  # noqa: E402
from rover_agent.planner import build_grid  # noqa: E402
from rover_agent.rover import Rover  # noqa: E402


class RoverDomainModuleTest(unittest.TestCase):
    def test_rover_domain_module_exists(self):
        self.assertIsNotNone(importlib.util.find_spec("rover_agent.rover"))


class FakeField:
    def __init__(self, poses, cell=1):
        self.poses = dict(poses)
        self.cell = cell

    def get_pose(self, rid):
        return self.poses.get(rid)

    def position_snapshot(self, rid):
        pose = self.poses.get(rid)
        return {
            "robot_id": rid,
            "x": round(pose.x, 3) if pose else None,
            "y": round(pose.y, 3) if pose else None,
            "theta": pose.theta if pose else None,
            "fresh": pose is not None,
            "age_ms": 0 if pose else None,
        }


class RecoveringField(FakeField):
    def __init__(self, recovered_pose):
        super().__init__({})
        self.recovered_pose = recovered_pose
        self.read_count = 0

    def get_pose(self, rid):
        self.read_count += 1
        if self.read_count == 1:
            return None
        return self.recovered_pose


class RecordingDrive:
    def __init__(self):
        self.wheels = []
        self.stop_count = 0
        self.close_count = 0
        self.addr = ("127.0.0.1", 8888)
        self._err_count = 0

    def set_wheels(self, left, right):
        self.wheels.append((left, right))

    def stop(self):
        self.stop_count += 1
        self.wheels.append((0, 0))

    def close(self):
        self.close_count += 1


class FakeObstacleMap:
    def __init__(self, grid, landmarks=()):
        self.grid = grid
        self.calls = []
        self.landmarks = [dict(item) for item in landmarks]

    def grid_for(self, avoid=()):
        self.calls.append(tuple(avoid))
        return self.grid

    def landmark_at(self, point):
        for item in self.landmarks:
            if math.hypot(point[0] - item["x_cm"],
                          point[1] - item["y_cm"]) <= item["radius_cm"]:
                return dict(item)
        return None

    def landmark_for_occupied_goal(self, point):
        return self.landmark_at(point)

    def get_landmark(self, landmark_id):
        for item in self.landmarks:
            if item["id"] == landmark_id:
                return dict(item)
        raise KeyError(landmark_id)


class RoverDomainTest(unittest.TestCase):
    def setUp(self):
        self.params = test_params()
        now = time.time()
        self.field = FakeField({
            "r1": Pose(15, 15, 0.0, now),
            "r2": Pose(15, 25, 0.0, now),
        })
        self.base_grid = build_grid(self.params)
        self.obstacle_map = FakeObstacleMap(self.base_grid)
        self.logs = []

    def make_rover(self, rid, obstacle_map=None):
        drive = RecordingDrive()
        rover = Rover(
            rid,
            self.params["robots"][rid],
            self.params,
            self.field,
            obstacle_map or self.obstacle_map,
            zones=[],
            drive=drive,
            debug=self.logs.append,
        )
        return rover, drive

    def test_tick_uses_owned_speed_and_plan(self):
        r1, d1 = self.make_rover("r1")
        r2, d2 = self.make_rover("r2")
        self.assertTrue(r1.set_goal((75, 15), speed=1))
        self.assertTrue(r2.set_goal((75, 25), speed=10))

        r1.tick()
        r2.tick()

        self.assertEqual(d1.wheels[-1], (25, 25))
        self.assertEqual(d2.wheels[-1], (60, 60))
        self.assertEqual(r1.speed, 1)
        self.assertEqual(r2.speed, 10)
        self.assertTrue(r1.plan)
        self.assertTrue(r2.plan)

    def test_two_rovers_do_not_share_state(self):
        r1, d1 = self.make_rover("r1")
        r2, d2 = self.make_rover("r2")
        r1.set_goal((75, 15), speed=1)
        r2.set_goal((75, 25), speed=10)
        r1.tick()
        r2.tick()

        r1.stop()

        self.assertFalse(r1.plan)
        self.assertTrue(r2.plan)
        self.assertEqual(r1.status, "idle")
        self.assertEqual(r2.status, "moving")
        self.assertGreater(d1.stop_count, 0)
        self.assertEqual(d2.stop_count, 0)

    def test_speed_zero_stops_without_planning(self):
        rover, drive = self.make_rover("r1")
        rover.set_goal((75, 15), speed=5)

        self.assertTrue(rover.set_goal((75, 15), speed=0))

        self.assertFalse(rover.plan)
        self.assertEqual(rover.status, "idle")
        self.assertGreater(drive.stop_count, 0)

    def test_invalid_speed_is_rejected(self):
        rover, _ = self.make_rover("r1")
        self.assertFalse(rover.set_goal((75, 15), speed=11))
        self.assertFalse(rover.plan)
        self.assertEqual(rover.status, "idle")

    def test_pose_loss_stops_but_keeps_plan_then_recovers(self):
        rover, drive = self.make_rover("r1")
        rover.set_goal((75, 15), speed=6)
        saved_plan = list(rover.plan)
        del self.field.poses["r1"]

        rover.tick()

        self.assertEqual(rover.status, "lost")
        self.assertEqual(rover.plan, saved_plan)
        self.assertGreater(drive.stop_count, 0)

        self.field.poses["r1"] = Pose(15, 15, 0.0, time.time())
        rover.tick()
        self.assertEqual(rover.status, "moving")
        self.assertNotEqual(drive.wheels[-1], (0, 0))

    def test_arrival_within_two_cm_latches_and_acknowledges(self):
        rover, drive = self.make_rover("r1")
        rover.set_goal((17, 15), speed=4)

        rover.tick()

        self.assertEqual(rover.status, "arrived")
        self.assertFalse(rover.plan)
        self.assertGreater(drive.stop_count, 0)
        rover.acknowledge_arrival()
        self.assertEqual(rover.status, "idle")

    def test_unreachable_target_sets_status(self):
        rover, _ = self.make_rover("r1")
        self.assertFalse(rover.set_goal((100, 100), speed=5))
        self.assertEqual(rover.status, "unreachable")

    def test_failed_new_command_cancels_previous_route(self):
        rover, drive = self.make_rover("r1")
        self.assertTrue(rover.set_goal((75, 15), speed=5))
        del self.field.poses["r1"]
        rover.params["vision"]["command_pose_wait_sec"] = 0

        self.assertFalse(rover.set_goal((20, 20), speed=5))

        self.assertFalse(rover.plan)
        self.assertEqual(rover.status, "lost")
        self.assertEqual(drive.wheels[-1], (0, 0))

    def test_calibrated_turn_pulses_then_waits_for_two_new_poses(self):
        self.params["motion_models"] = {
            "default": {
                "turn_power_pct": 40,
                "left_turn_deg_s": 130.1,
                "right_turn_deg_s": 99.9,
            },
        }
        self.params["control"].update({
            "turn_pulse_fraction": 0.7,
            "turn_pulse_min_sec": 0.08,
            "turn_pulse_max_sec": 0.35,
            "turn_settle_sec": 0.2,
            "turn_confirm_frames": 2,
        })
        self.field.poses["r1"] = Pose(40, 30, 0.0, 1.0)
        rover, drive = self.make_rover("r1")
        self.assertTrue(rover.set_goal((40, 55), speed=10))

        with patch("rover_agent.rover.time.monotonic", return_value=10.0):
            rover.tick()
        self.assertEqual(drive.wheels[-1], (-40, 40))
        self.assertEqual(rover.controller_state["turn_phase"], "pulse")

        with patch("rover_agent.rover.time.monotonic", return_value=10.36):
            rover.tick()
        self.assertEqual(drive.wheels[-1], (0, 0))
        self.assertEqual(rover.controller_state["turn_phase"], "observe")

        self.field.poses["r1"] = Pose(40, 30, 0.4, 2.0)
        with patch("rover_agent.rover.time.monotonic", return_value=10.7):
            rover.tick()
        self.assertEqual(rover.controller_state["turn_fresh_count"], 1)
        self.field.poses["r1"] = Pose(40, 30, 0.7, 3.0)
        with patch("rover_agent.rover.time.monotonic", return_value=10.8):
            rover.tick()
        self.assertEqual(rover.controller_state["turn_phase"], "pulse")
        self.assertEqual(drive.wheels[-1], (-40, 40))

    def test_command_waits_for_temporarily_missing_pose(self):
        field = RecoveringField(Pose(15, 15, 0.0, time.time()))
        drive = RecordingDrive()
        rover = Rover(
            "r1", self.params["robots"]["r1"], self.params,
            field, self.obstacle_map, zones=[], drive=drive,
        )

        self.assertTrue(rover.set_goal((20, 20), speed=2))
        self.assertGreaterEqual(field.read_count, 2)
        self.assertEqual(rover.status, "moving")

    def test_position_merges_perception_with_owned_status(self):
        rover, _ = self.make_rover("r1")
        rover.status = "moving"
        position = rover.position
        self.assertEqual(position["status"], "moving")
        self.assertEqual(position["car_id"], "r1")
        self.assertEqual((position["x"], position["y"]), (15, 15))

    def test_goto_and_zone_keep_public_contract(self):
        zones = [{"id": "base", "center": [50, 50]}]
        drive = RecordingDrive()
        rover = Rover(
            "r1", self.params["robots"]["r1"], self.params,
            self.field, self.obstacle_map, zones=zones, drive=drive)
        self.assertTrue(rover.goto(x_cm=70, y_cm=50, speed=3))
        self.assertEqual(rover.speed, 3)
        self.assertTrue(rover.goto_zone("base", speed=4))
        self.assertEqual(rover.speed, 4)
        self.assertFalse(rover.goto_zone("missing"))

    def test_trail_sampling_uses_half_centimeter_threshold(self):
        rover, _ = self.make_rover("r1")
        rover.tick()
        self.field.poses["r1"] = Pose(15.4, 15, 0.0, time.time())
        rover.tick()
        self.assertEqual(rover.trail, [(15, 15)])

        self.field.poses["r1"] = Pose(15.6, 15, 0.0, time.time())
        rover.tick()
        self.assertEqual(rover.trail, [(15, 15), (15.6, 15)])

    def test_each_goal_reads_current_obstacle_map(self):
        rover, _ = self.make_rover("r1")
        rover.set_goal((70, 15), avoid=["dust"])
        rover.stop()
        rover.set_goal((60, 15))
        self.assertEqual(self.obstacle_map.calls, [("dust",), ()])

    def landmark_map(self):
        landmark = {"id": "base", "shape": "circle",
                    "x_cm": 40, "y_cm": 30, "radius_cm": 5}
        grid = build_grid(self.params, obstacles=[landmark])
        return landmark, FakeObstacleMap(grid, [landmark])

    def test_coordinate_inside_fixed_landmark_becomes_landmark_goal(self):
        landmark, obstacle_map = self.landmark_map()
        self.field.poses["r1"] = Pose(10, 30, 0.0, time.time())
        rover, _ = self.make_rover("r1", obstacle_map)

        self.assertTrue(rover.set_goal((40, 30), speed=5))

        self.assertEqual(rover.target_landmark["id"], "base")
        self.assertEqual(rover.approach_phase, "route")
        approach = rover.full_plan[-1]
        self.assertAlmostEqual(
            math.hypot(approach[0] - landmark["x_cm"],
                       approach[1] - landmark["y_cm"]),
            16.0, delta=0.01)

    def test_coordinate_in_inflated_fixed_cell_becomes_landmark_goal(self):
        self.params["planner"]["robot_radius_cm"] = 2
        landmark = {"id": "obstacle-5", "shape": "circle",
                    "x_cm": 63.28, "y_cm": 46.87, "radius_cm": 5.16}
        obstacle_map = ObstacleMap(self.params, landmarks=[landmark])
        self.field.poses["r1"] = Pose(63.63, 25.56, 0.0, time.time())
        rover, _ = self.make_rover("r1", obstacle_map)

        self.assertTrue(rover.set_goal((60, 40), speed=2))
        self.assertEqual(rover.target_landmark["id"], "obstacle-5")
        self.assertEqual(rover.approach_phase, "route")

    def test_transient_obstacle_is_never_promoted_to_target(self):
        transient = {"id": "dust", "shape": "circle",
                     "x_cm": 40, "y_cm": 30, "radius_cm": 5}
        obstacle_map = FakeObstacleMap(
            build_grid(self.params, obstacles=[transient]))
        rover, _ = self.make_rover("r1", obstacle_map)
        self.assertFalse(rover.set_goal((40, 30), speed=3))
        self.assertIsNone(rover.target_landmark)

    def test_landmark_arrival_requires_two_stable_frames_in_gap_band(self):
        landmark, obstacle_map = self.landmark_map()
        self.field.poses["r1"] = Pose(10, 30, 0.0, time.time())
        rover, drive = self.make_rover("r1", obstacle_map)
        self.assertTrue(rover.goto_landmark("base", speed=5))
        approach = rover.plan[-1]

        self.field.poses["r1"] = Pose(*approach, 0.0, time.time())
        rover.tick()
        self.assertEqual(rover.status, "approaching")
        self.assertEqual(rover.approach_phase, "creep")

        dx = approach[0] - landmark["x_cm"]
        dy = approach[1] - landmark["y_cm"]
        length = math.hypot(dx, dy)
        center_distance = landmark["radius_cm"] + 7 + 1.5
        close = (landmark["x_cm"] + dx / length * center_distance,
                 landmark["y_cm"] + dy / length * center_distance)
        first_ts = time.time()
        self.field.poses["r1"] = Pose(*close, 0.0, first_ts)

        rover.tick()
        self.assertEqual(rover.status, "approaching")
        self.assertEqual(rover.landmark_confirmations, 1)
        rover.tick()  # 同一张视觉帧不能重复计数
        self.assertEqual(rover.status, "approaching")
        self.assertEqual(rover.landmark_confirmations, 1)
        self.field.poses["r1"] = Pose(*close, 0.0, first_ts + 0.1)
        rover.tick()
        self.assertEqual(rover.status, "arrived")
        self.assertFalse(rover.plan)
        self.assertGreater(drive.stop_count, 0)
        self.assertAlmostEqual(rover.position["landmark_gap_cm"], 1.5)

    def test_landmark_creep_uses_speed_one_until_gap_band(self):
        landmark, obstacle_map = self.landmark_map()
        self.field.poses["r1"] = Pose(10, 30, 0.0, time.time())
        rover, drive = self.make_rover("r1", obstacle_map)
        rover.goto_landmark("base", speed=8)
        approach = rover.plan[-1]
        self.field.poses["r1"] = Pose(*approach, 0.0, time.time())
        rover.tick()

        # 从左侧朝目标，表面间隙 3cm，应以 speed=1 继续直行。
        self.field.poses["r1"] = Pose(25, 30, 0.0, time.time())
        rover.tick()
        self.assertEqual(rover.status, "approaching")
        self.assertEqual(drive.wheels[-1], (25, 25))

    def test_landmark_creep_stops_if_gap_is_below_safe_minimum(self):
        _, obstacle_map = self.landmark_map()
        self.field.poses["r1"] = Pose(10, 30, 0.0, time.time())
        rover, drive = self.make_rover("r1", obstacle_map)
        rover.goto_landmark("base", speed=5)
        approach = rover.plan[-1]
        self.field.poses["r1"] = Pose(*approach, 0.0, time.time())
        rover.tick()

        self.field.poses["r1"] = Pose(27.5, 30, 0.0, time.time())
        rover.tick()  # 表面间隙 0.5cm
        self.assertEqual(rover.status, "too_close")
        self.assertEqual(drive.wheels[-1], (0, 0))

    def test_close_is_idempotent(self):
        rover, drive = self.make_rover("r1")
        rover.close()
        rover.close()
        self.assertEqual(drive.close_count, 1)


if __name__ == "__main__":
    unittest.main()
