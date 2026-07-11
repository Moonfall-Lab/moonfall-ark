import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.qr_skill_scanner import (  # noqa: E402
    QrPresentationGate,
    load_skill_allowlist,
)


class SkillAllowlistTest(unittest.TestCase):
    def test_loads_supplied_card_names_from_runtime_config(self):
        skills = load_skill_allowlist(BACKEND / "configs" / "moonfall.yaml")
        expected = {
            "探索遗迹": "explore_relic",
            "燃料掠夺": "fuel_raid",
            "月岩炮击": "moonrock_strike",
            "返航结算": "return_settle",
            "采集优先": "collect_priority",
            "神之祈愿": "divine_prayer",
            "瞬移偷窃": "teleport_steal",
            "月尘护符": "dust_ward",
            "核心修复": "ark_repair",
            "并发任务": "concurrent_ops",
        }

        actual = {name: skills[name].skill_id for name in expected}

        self.assertEqual(actual, expected)

    def test_rejects_duplicate_card_names(self):
        path = self._write_config(
            {
                "inputs": {
                    "cards": [
                        {"id": "a", "name": "重复"},
                        {"id": "b", "name": "重复"},
                    ]
                }
            }
        )

        with self.assertRaisesRegex(ValueError, "duplicate card name"):
            load_skill_allowlist(path)

    def _write_config(self, config):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "moonfall.yaml"
        path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
        return path


class QrPresentationGateTest(unittest.TestCase):
    def test_emits_once_until_value_is_absent_for_threshold(self):
        gate = QrPresentationGate(missing_frame_threshold=2)

        self.assertEqual(gate.observe({"采集优先"}), ["采集优先"])
        self.assertEqual(gate.observe({"采集优先"}), [])
        self.assertEqual(gate.observe(set()), [])
        self.assertEqual(gate.observe(set()), [])
        self.assertEqual(gate.observe({"采集优先"}), ["采集优先"])

    def test_tracks_multiple_values_independently(self):
        gate = QrPresentationGate(missing_frame_threshold=1)

        self.assertCountEqual(
            gate.observe({"采集优先", "核心修复"}),
            ["采集优先", "核心修复"],
        )
        self.assertEqual(gate.observe({"核心修复"}), [])
        self.assertEqual(
            gate.observe({"采集优先", "核心修复"}),
            ["采集优先"],
        )


if __name__ == "__main__":
    unittest.main()
