import math
import inspect
import unittest

from tests.rover_helpers import CLIENTS, test_params  # noqa: F401

import rover_agent.controller as controller  # noqa: E402
from rover_agent.geometry import Pose, dist  # noqa: E402
from rover_agent.planner import OccupancyGrid, plan  # noqa: E402

step = controller.step

P = test_params()["control"]


def pose(x, y, theta):
    return Pose(x, y, theta, ts=0.0)


class StepTest(unittest.TestCase):
    def test_target_ahead_goes_straight(self):
        l, r, wps, done = step(pose(0, 0, 0), [(50, 0)], P)
        self.assertFalse(done)
        self.assertEqual((l, r), (P["max_cruise_pct"], P["max_cruise_pct"]))

    def test_target_left_turns_in_place(self):
        l, r, _, done = step(pose(0, 0, 0), [(0, 50)], P)
        self.assertFalse(done)
        self.assertEqual((l, r), (-P["max_turn_pct"], P["max_turn_pct"]))

    def test_target_right_turns_in_place(self):
        l, r, _, _ = step(pose(0, 0, 0), [(0, -50)], P)
        self.assertEqual((l, r), (P["max_turn_pct"], -P["max_turn_pct"]))

    def test_target_behind_turns(self):
        l, r, _, _ = step(pose(0, 0, 0), [(-50, 0)], P)
        self.assertEqual(abs(l), P["max_turn_pct"])
        self.assertEqual(l, -r)

    def test_small_error_forward_with_correction(self):
        err = math.atan2(5, 50)
        l, r, _, done = step(pose(0, 0, 0), [(50, 5)], P)
        self.assertFalse(done)
        self.assertGreater(r, l, "目标偏左 → 右轮更快")
        # 输出按 wheel_step_pct(5) 量化，差值允许一档以内的偏差
        self.assertAlmostEqual(r - l, 2 * P["k_heading"] * err, delta=5)

    def test_waypoint_consumed(self):
        _, _, wps, done = step(pose(0, 0, 0), [(3, 0), (50, 0)], P)
        self.assertFalse(done)
        self.assertEqual(wps, [(50, 0)])

    def test_arrival(self):
        l, r, wps, done = step(pose(0, 0, 0), [(2, 0)], P)
        self.assertTrue(done)
        self.assertEqual((l, r), (0, 0))
        self.assertEqual(wps, [])

    def test_final_waypoint_at_two_cm_is_arrived(self):
        l, r, wps, done = step(pose(0, 0, 0), [(2, 0)], P)
        self.assertTrue(done)
        self.assertEqual((l, r), (0, 0))
        self.assertEqual(wps, [])

    def test_five_cm_command_keeps_moving(self):
        _, _, _, done = step(pose(0, 0, 0), [(5, 0)], P)
        self.assertFalse(done)


class SpeedLevelTest(unittest.TestCase):
    def setUp(self):
        self.params = dict(P)
        self.params.update({
            "min_cruise_pct": 25,
            "max_cruise_pct": 60,
            "min_turn_pct": 25,
            "max_turn_pct": 40,
        })

    def test_level_ten_preserves_current_maximum_outputs(self):
        l, r, _, _ = step(pose(0, 0, 0), [(50, 0)], self.params,
                          speed=10)
        self.assertEqual((l, r), (60, 60))
        l, r, _, _ = step(pose(0, 0, 0), [(0, 50)], self.params,
                          speed=10)
        self.assertEqual((l, r), (-40, 40))

    def test_level_one_uses_minimum_effective_outputs(self):
        l, r, _, _ = step(pose(0, 0, 0), [(50, 0)], self.params,
                          speed=1)
        self.assertEqual((l, r), (25, 25))
        l, r, _, _ = step(pose(0, 0, 0), [(0, 50)], self.params,
                          speed=1)
        self.assertEqual((l, r), (-25, 25))

    def test_level_five_interpolates_between_min_and_max(self):
        l, r, _, _ = step(pose(0, 0, 0), [(50, 0)], self.params,
                          speed=5)
        self.assertEqual((l, r), (40, 40))
        l, r, _, _ = step(pose(0, 0, 0), [(0, 50)], self.params,
                          speed=5)
        self.assertEqual((l, r), (-32, 32))

    def test_heading_correction_scales_down_with_speed(self):
        target = [(50, 10)]
        fast_l, fast_r, _, _ = step(pose(0, 0, 0), target, self.params,
                                    speed=10)
        slow_l, slow_r, _, _ = step(pose(0, 0, 0), target, self.params,
                                    speed=1)
        self.assertLess(slow_r - slow_l, fast_r - fast_l)

    def test_validator_accepts_only_integer_zero_to_ten(self):
        self.assertEqual(controller.validate_speed_level(0), 0)
        self.assertEqual(controller.validate_speed_level(10), 10)
        for value in (-1, 11, 1.5, "5", True, None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    controller.validate_speed_level(value)

    def test_zero_is_stop_not_a_controller_motion_level(self):
        with self.assertRaises(ValueError):
            step(pose(0, 0, 0), [(50, 0)], self.params, speed=0)


class SpeedApiShapeTest(unittest.TestCase):
    def test_controller_exposes_speed_level_api(self):
        self.assertTrue(hasattr(controller, "validate_speed_level"))
        self.assertIn("speed", inspect.signature(controller.step).parameters)

    def test_public_cruise_mapping_matches_controller_outputs(self):
        self.assertEqual(controller.cruise_pct_for_speed(P, 5), 40)
        self.assertEqual(controller.cruise_pct_for_speed(P, 10), 60)


class HysteresisTest(unittest.TestCase):
    """原地转滞回：enter=0.9 / exit=0.25，中间地带保持当前模式。"""

    def test_mid_error_cruises_with_arc(self):
        # err≈0.46（旧单阈值 0.44 会原地转）→ 现在直行画弧，不停车
        l, r, _, _ = step(pose(0, 0, 0), [(50, 25)], P)
        self.assertGreater(l, 0)
        self.assertGreater(r, l, "目标偏左 → 右轮更快")

    def test_stays_turning_inside_band(self):
        st = {}
        l, r, _, _ = step(pose(0, 0, 0), [(0, 50)], P, st)
        self.assertTrue(st["turning"])
        self.assertEqual((l, r), (-P["max_turn_pct"], P["max_turn_pct"]))
        # 误差降到 0.46，仍在滞回带内 → 继续原地转，不切模式
        l, r, _, _ = step(pose(0, 0, math.pi / 2 - 0.46), [(0, 50)], P, st)
        self.assertTrue(st["turning"])
        self.assertEqual((l, r), (-P["max_turn_pct"], P["max_turn_pct"]))

    def test_exits_below_exit_thresh(self):
        st = {"turning": True}
        l, r, _, _ = step(pose(0, 0, math.pi / 2 - 0.2), [(0, 50)], P, st)
        self.assertFalse(st["turning"])
        self.assertGreater(l, 0)
        self.assertGreater(r, 0)

    def test_no_reenter_inside_band(self):
        st = {"turning": False}
        step(pose(0, 0, 0), [(50, 25)], P, st)
        self.assertFalse(st["turning"])

    def test_arrival_resets_state(self):
        st = {"turning": True}
        _, _, _, done = step(pose(0, 0, 0), [(2, 0)], P, st)
        self.assertTrue(done)
        self.assertFalse(st["turning"])


class TurnPulseTest(unittest.TestCase):
    MODEL = {
        "turn_power_pct": 40,
        "left_turn_deg_s": 130.1,
        "right_turn_deg_s": 99.9,
    }
    CONTROL = {
        "turn_pulse_fraction": 0.7,
        "turn_pulse_min_sec": 0.08,
        "turn_pulse_max_sec": 0.35,
    }

    def test_direction_specific_rates_produce_different_pulse_lengths(self):
        left_wheels, left_sec = controller.turn_pulse_for_error(
            math.radians(30), self.MODEL, self.CONTROL)
        right_wheels, right_sec = controller.turn_pulse_for_error(
            math.radians(-30), self.MODEL, self.CONTROL)

        self.assertEqual(left_wheels, (-40, 40))
        self.assertEqual(right_wheels, (40, -40))
        self.assertAlmostEqual(left_sec, 0.7 * 30 / 130.1)
        self.assertAlmostEqual(right_sec, 0.7 * 30 / 99.9)
        self.assertGreater(right_sec, left_sec)

    def test_small_error_respects_minimum_pulse(self):
        _, duration = controller.turn_pulse_for_error(
            math.radians(2), self.MODEL, self.CONTROL)
        self.assertEqual(duration, 0.08)


class KinematicSimTest(unittest.TestCase):
    """理想差速模型仿真：沿 A* 路径闭环收敛到目标。"""

    V_FULL = 25.0   # 100% 轮速对应线速度 cm/s
    W_FULL = 3.0    # 全差速对应角速度 rad/s
    DT = 0.08

    def _simulate(self, start, goal, grid):
        waypoints = plan(grid, start, goal)
        self.assertIsNotNone(waypoints)
        x, y, th = start[0], start[1], 0.0
        st = {}  # 与 agent 一致：带滞回状态跑闭环
        for _ in range(1500):
            l, r, waypoints, done = step(pose(x, y, th), waypoints, P, st)
            if done:
                return (x, y)
            v = self.V_FULL * (l + r) / 200.0
            w = self.W_FULL * (r - l) / 200.0
            th += w * self.DT
            x += v * math.cos(th) * self.DT
            y += v * math.sin(th) * self.DT
        self.fail("1500 步内未到达")

    def test_open_field(self):
        end = self._simulate((15, 15), (75, 55), OccupancyGrid(80, 60))
        self.assertLessEqual(dist(end, (75, 55)), P["arrive_tol_cm"] + 1)

    def test_with_obstacle(self):
        grid = OccupancyGrid.from_zones(
            80, [{"id": "m", "kind": "obstacle", "center": [40, 30]}],
            ny=60,
            inflate_cells=1)
        end = self._simulate((15, 30), (70, 40), grid)
        self.assertLessEqual(dist(end, (70, 40)), P["arrive_tol_cm"] + 1)

    def test_with_cylinder_obstacle(self):
        grid = OccupancyGrid(80, 60)
        grid.add_circle(40, 30, 5, margin_cm=7)
        end = self._simulate((15, 30), (70, 35), grid)
        self.assertLessEqual(dist(end, (70, 35)), P["arrive_tol_cm"] + 1)


if __name__ == "__main__":
    unittest.main()
