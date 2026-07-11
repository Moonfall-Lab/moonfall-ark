import unittest
from unittest.mock import patch

from tests.rover_helpers import CLIENTS, test_params  # noqa: F401

from rover_agent.fleet import Fleet  # noqa: E402
from rover_agent.smoke_drive import SEND_PERIOD  # noqa: E402
from rover_agent.viz import load_params  # noqa: E402


class RecordingDrive:
    periods = []
    ttls = []

    def __init__(self, _ip, port=8888, period_ms=250,
                 command_ttl_ms=1000, reverse=False):
        self.addr = ("127.0.0.1", port)
        self._err_count = 0
        type(self).periods.append(period_ms)
        type(self).ttls.append(command_ttl_ms)

    def stop(self):
        pass

    def close(self):
        pass


class FakeField:
    def start(self):
        pass

    def stop(self):
        pass

    def get_pose(self, _rid):
        return None

    def position_snapshot(self, rid):
        return {"robot_id": rid, "x": None, "y": None, "theta": None,
                "fresh": False, "age_ms": None}

    def wait_ready(self, _robot_ids, timeout=30.0):
        return False


class TimingSplitTest(unittest.TestCase):
    def setUp(self):
        RecordingDrive.periods = []
        RecordingDrive.ttls = []

    def test_fleet_rovers_use_drive_keepalive_period(self):
        with patch("rover_agent.rover.RoverDrive", RecordingDrive):
            fleet = Fleet(
                params=test_params(), field=FakeField(), start=False,
                health=False, debug=lambda _message: None,
            )
        try:
            self.assertEqual(RecordingDrive.periods, [250, 250])
            self.assertEqual(RecordingDrive.ttls, [1000, 1000])
        finally:
            fleet.shutdown()

    def test_fleet_uses_control_correction_period(self):
        with patch("rover_agent.rover.RoverDrive", RecordingDrive):
            fleet = Fleet(
                params=test_params(), field=FakeField(), start=False,
                health=False, debug=lambda _message: None,
            )
        try:
            self.assertEqual(fleet.control_period_s, 0.1)
        finally:
            fleet.shutdown()

    def test_field_config_uses_verified_network_values(self):
        params = load_params()
        self.assertEqual(params["robots"]["r0"], {
            "ip": "10.202.241.122",
            "marker_id": 0,
            "theta_offset_deg": 0,
        })
        self.assertEqual(params["drive"]["keepalive_period_ms"], 250)
        self.assertEqual(params["planner"]["vehicle_length_cm"], 6)
        self.assertEqual(params["planner"]["vehicle_width_cm"], 5.5)
        self.assertEqual(params["planner"]["safety_clearance_cm"], 0.5)
        self.assertEqual(params["vision"]["command_pose_wait_sec"], 2)
        self.assertEqual(params["motion_models"]["default"], {
            "straight_speed_cm_s": {5: 5.48, 10: 8.91},
            "turn_power_pct": 40,
            "left_turn_deg_s": 130.1,
            "right_turn_deg_s": 99.9,
        })

    def test_field_config_registers_second_rover(self):
        params = load_params()
        self.assertEqual(params["robots"]["r1"], {
            "ip": "10.202.241.220",
            "marker_id": 1,
            "theta_offset_deg": 0,
        })

    def test_smoke_drive_uses_safe_keepalive_period(self):
        self.assertEqual(SEND_PERIOD, 0.25)


if __name__ == "__main__":
    unittest.main()
