import math
import pathlib
import tempfile
import unittest

from tests.rover_helpers import CLIENTS  # noqa: F401 —— sys.path 注入

from rover_agent.init_direction import (  # noqa: E402
    snap_deg, suggest_offset_deg, update_params_offset,
)

PARAMS_YAML = """\
robots:
  r1: {ip: "10.0.0.1", marker_id: 0, theta_offset_deg: 0}  # 行尾注释
  r2: {ip: "10.0.0.2", marker_id: 1}
"""


class OffsetMathTest(unittest.TestCase):
    def test_sticker_straight(self):
        self.assertAlmostEqual(suggest_offset_deg(1.0, 1.0), 0.0)

    def test_sticker_reversed(self):
        # 车往 +x 走，码却指 -x → 差 180°
        off = suggest_offset_deg(0.0, math.pi)
        self.assertAlmostEqual(abs(off), 180.0, places=4)
        self.assertEqual(abs(snap_deg(off)), 180)

    def test_sticker_quarter_turn(self):
        off = suggest_offset_deg(math.pi / 2, 0.0)
        self.assertAlmostEqual(off, 90.0, places=4)
        self.assertEqual(snap_deg(off), 90)

    def test_wraparound(self):
        # 170° 与 -170° 只差 20°，不是 340°
        off = suggest_offset_deg(math.radians(170), math.radians(-170))
        self.assertAlmostEqual(off, -20.0, places=4)
        self.assertEqual(snap_deg(off), 0)

    def test_snap_prefers_nearest(self):
        self.assertEqual(snap_deg(-95.0), -90)
        self.assertEqual(snap_deg(179.0), 180)
        self.assertEqual(snap_deg(-179.0), 180)


class UpdateParamsTest(unittest.TestCase):
    def _roundtrip(self, rid, deg):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "params.yaml"
            p.write_text(PARAMS_YAML, encoding="utf-8")
            self.assertTrue(update_params_offset(p, rid, deg))
            return p.read_text(encoding="utf-8")

    def test_update_existing_key(self):
        text = self._roundtrip("r1", 180.0)
        self.assertIn("theta_offset_deg: 180.0", text)
        self.assertIn("# 行尾注释", text, "注释必须保留")
        self.assertIn('r2: {ip: "10.0.0.2", marker_id: 1}', text,
                      "别的车那行不能被改")

    def test_insert_missing_key(self):
        text = self._roundtrip("r2", -90.0)
        self.assertIn("marker_id: 1, theta_offset_deg: -90.0}", text)
        self.assertIn("theta_offset_deg: 0", text, "r1 保持原值")

    def test_unknown_robot(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "params.yaml"
            p.write_text(PARAMS_YAML, encoding="utf-8")
            self.assertFalse(update_params_offset(p, "r9", 5.0))
            self.assertEqual(p.read_text(encoding="utf-8"), PARAMS_YAML)


if __name__ == "__main__":
    unittest.main()
