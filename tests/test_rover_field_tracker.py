import importlib.util
import time
import unittest
from unittest.mock import patch

from tests.rover_helpers import (CLIENTS, CORNER_PX,  # noqa: F401
                                 make_frame, test_params)

from rover_agent.calibration import aruco_detect  # noqa: E402
from rover_agent.field_tracker import FieldTracker  # noqa: E402


class FieldTrackerModuleTest(unittest.TestCase):
    def test_field_tracker_module_exists(self):
        self.assertIsNotNone(importlib.util.find_spec("rover_agent.field_tracker"))


class FakeSource:
    def __init__(self):
        self.release_count = 0
        self.read_count = 0

    def read(self):
        self.read_count += 1
        return None

    def release(self):
        self.release_count += 1


class FieldTrackerTest(unittest.TestCase):
    def setUp(self):
        self.params = test_params()
        self.tracker = FieldTracker(self.params, source=None)
        markers = [
            (0, CORNER_PX[0], 0), (1, CORNER_PX[1], 0),
            (2, CORNER_PX[2], 0), (3, CORNER_PX[3], 0),
            (10, (450, 450), 0),
        ]
        self.frame = make_frame(markers)

    def test_first_frame_calibrates_and_second_frame_detects(self):
        self.assertEqual(self.tracker.process_frame(self.frame), {})
        self.assertTrue(self.tracker.calibrated)

        poses = self.tracker.process_frame(self.frame)

        self.assertIn("r1", poses)
        pose = self.tracker.get_pose("r1")
        self.assertIsNotNone(pose)
        self.assertAlmostEqual(pose.x, 40, delta=1)
        self.assertAlmostEqual(pose.y, 30, delta=1)

    def test_none_frame_is_ignored(self):
        self.assertEqual(self.tracker.process_frame(None), {})
        self.assertFalse(self.tracker.calibrated)

    def test_position_snapshot_is_perception_only(self):
        self.tracker.process_frame(self.frame)
        self.tracker.process_frame(self.frame)

        snapshot = self.tracker.position_snapshot("r1")

        self.assertEqual(snapshot["robot_id"], "r1")
        self.assertAlmostEqual(snapshot["x"], 40, delta=1)
        self.assertAlmostEqual(snapshot["y"], 30, delta=1)
        self.assertTrue(snapshot["fresh"])
        self.assertNotIn("status", snapshot)

    def test_snapshot_keeps_last_pose_when_stale(self):
        self.tracker.process_frame(self.frame)
        self.tracker.process_frame(self.frame)
        pose, _ = self.tracker.get_last_pose("r1")

        with patch("rover_agent.vision.time.time",
                   return_value=pose.ts + self.tracker.store.stale_sec + 1.0):
            snapshot = self.tracker.position_snapshot("r1")

        self.assertFalse(snapshot["fresh"])
        self.assertIsNotNone(snapshot["x"])
        self.assertGreater(snapshot["age_ms"], 1000)

    def test_snapshot_distinguishes_never_seen_and_unknown(self):
        snapshot = self.tracker.position_snapshot("r2")
        self.assertIsNone(snapshot["x"])
        self.assertFalse(snapshot["fresh"])
        with self.assertRaises(KeyError):
            self.tracker.position_snapshot("r9")

    def test_visual_snapshot_contains_last_frame_and_markers(self):
        self.tracker.process_frame(self.frame)
        frame, found = self.tracker.visual_snapshot()
        self.assertIs(frame, self.frame)
        self.assertTrue({0, 1, 2, 3, 10}.issubset(found))

    def test_same_dictionary_is_scanned_once_per_frame(self):
        with patch("rover_agent.field_tracker.aruco_detect",
                   wraps=aruco_detect) as detect:
            self.tracker.process_frame(self.frame)
        self.assertEqual(detect.call_count, 1)


class FieldTrackerLifecycleTest(unittest.TestCase):
    def test_start_and_stop_are_idempotent(self):
        source = FakeSource()
        tracker = FieldTracker(test_params(), source=source)

        tracker.start()
        tracker.start()
        deadline = time.time() + 1.0
        while source.read_count == 0 and time.time() < deadline:
            time.sleep(0.01)
        tracker.stop()
        tracker.stop()

        self.assertGreater(source.read_count, 0)
        self.assertEqual(source.release_count, 1)


if __name__ == "__main__":
    unittest.main()
