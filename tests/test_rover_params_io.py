import pathlib
import tempfile
import unittest

import yaml

from tests.rover_helpers import CLIENTS, ROOT  # noqa: F401 —— sys.path

from rover_agent.params_io import (replace_landmarks,  # noqa: E402
                                   update_params_offset, upsert_robot)

SAMPLE = """\
# 顶部注释要保留
table:
  width_cm: 80

robots:
  # 说明注释
  r1: { ip: "10.0.0.5", marker_id: 0, theta_offset_deg: 0 }
  # r2: { ip: "", marker_id: 11, theta_offset_deg: 0 }

# ── 障碍注释也要保留 ──
landmarks:
  - { id: rock-1, shape: circle, x_cm: 40, y_cm: 30, radius_cm: 5 }
  - { id: rock-2, shape: circle, x_cm: 20, y_cm: 45, radius_cm: 4 }

vision:
  rate_hz: 15
"""


class ParamsIoTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.dir.name) / "params.yaml"
        self.path.write_text(SAMPLE, encoding="utf-8")

    def tearDown(self):
        self.dir.cleanup()

    def test_upsert_activates_commented_placeholder(self):
        self.assertTrue(upsert_robot(self.path, "r2", "10.0.0.7", 11))
        text = self.path.read_text()
        self.assertIn('r2: { ip: "10.0.0.7", marker_id: 11', text)
        self.assertNotIn("# r2:", text)
        self.assertIn("# 说明注释", text)

    def test_upsert_inserts_new_after_last_robot(self):
        self.assertTrue(upsert_robot(self.path, "r5", "10.0.0.9", 13))
        lines = self.path.read_text().splitlines()
        i_r1 = next(i for i, ln in enumerate(lines) if ln.startswith("  r1:"))
        i_r5 = next(i for i, ln in enumerate(lines) if ln.startswith("  r5:"))
        self.assertGreater(i_r5, i_r1)
        i_landmarks = next(i for i, ln in enumerate(lines)
                           if ln.startswith("landmarks:"))
        self.assertLess(i_r5, i_landmarks, "必须插在 robots 块内")

    def test_upsert_replaces_existing(self):
        self.assertTrue(upsert_robot(self.path, "r1", "10.0.0.99", 8))
        text = self.path.read_text()
        self.assertIn('r1: { ip: "10.0.0.99", marker_id: 8', text)
        self.assertEqual(text.count("r1:"), 1)

    def test_upsert_then_offset_update(self):
        upsert_robot(self.path, "r2", "10.0.0.7", 11)
        self.assertTrue(update_params_offset(self.path, "r2", -90.0))
        self.assertIn("theta_offset_deg: -90.0", self.path.read_text())

    def test_replace_landmarks(self):
        replace_landmarks(self.path, [
            {"id": "rock-3", "shape": "circle",
             "x_cm": 50, "y_cm": 25, "radius_cm": 5.5},
        ])
        text = self.path.read_text()
        self.assertIn("id: rock-3", text)
        self.assertIn("radius_cm: 5.50", text)
        self.assertNotIn("rock-2", text, "旧障碍应被整块替换")
        self.assertIn("# ── 障碍注释也要保留 ──", text)
        self.assertIn("vision:", text)
        self.assertIn("rate_hz: 15", text)
        import yaml
        data = yaml.safe_load(text)   # 改完仍是合法 yaml
        self.assertEqual(len(data["landmarks"]), 1)

    def test_replace_landmarks_empty(self):
        replace_landmarks(self.path, [])
        data = yaml.safe_load(self.path.read_text())
        self.assertEqual(data["landmarks"], [])
        self.assertIn("vision:", self.path.read_text())

    def test_shipped_map_uses_centimeters(self):
        params_path = ROOT / "backend" / "clients" / "rover_agent" / "params.yaml"
        params = yaml.safe_load(params_path.read_text(encoding="utf-8"))
        self.assertEqual(params["table"], {
            "width_cm": 80, "height_cm": 60, "cell_cm": 1,
        })
        self.assertEqual(params["control"]["arrive_tol_cm"], 2)
        self.assertEqual(params["landmarks"], [])
        self.assertNotIn("obstacles", params)
        self.assertEqual(params["control"]["landmark_gap_min_cm"], 1)
        self.assertEqual(params["control"]["landmark_gap_max_cm"], 2)


if __name__ == "__main__":
    unittest.main()
