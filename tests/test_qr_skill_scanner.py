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
    OpenCvQrBackend,
    QrDecoder,
    QrPresentationGate,
    ZxingQrBackend,
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


class StaticDecoderBackend:
    def __init__(self, values):
        self.values = set(values)
        self.calls = 0

    def decode(self, frame):
        self.calls += 1
        return set(self.values)


class QrDecoderTest(unittest.TestCase):
    def test_uses_primary_results_without_fallback(self):
        primary = StaticDecoderBackend({"采集优先"})
        fallback = StaticDecoderBackend({"不应调用"})
        decoder = QrDecoder(primary=primary, fallback=fallback)

        self.assertEqual(decoder.decode(object()), {"采集优先"})
        self.assertEqual(primary.calls, 1)
        self.assertEqual(fallback.calls, 0)

    def test_uses_fallback_when_primary_has_no_text(self):
        primary = StaticDecoderBackend(set())
        fallback = StaticDecoderBackend({"神之祈愿"})
        decoder = QrDecoder(primary=primary, fallback=fallback)

        self.assertEqual(decoder.decode(object()), {"神之祈愿"})
        self.assertEqual(primary.calls, 1)
        self.assertEqual(fallback.calls, 1)


class QrImageDecoderTest(unittest.TestCase):
    def test_opencv_backend_decodes_generated_qr(self):
        import cv2

        image = cv2.QRCodeEncoder_create().encode("核心修复")

        self.assertEqual(OpenCvQrBackend().decode(image), {"核心修复"})

    def test_zxing_backend_decodes_generated_qr(self):
        import cv2

        image = cv2.QRCodeEncoder_create().encode("月尘护符")

        self.assertEqual(ZxingQrBackend().decode(image), {"月尘护符"})

    def test_default_decoder_builds_both_backends(self):
        import cv2

        image = cv2.QRCodeEncoder_create().encode("并发任务")

        self.assertEqual(QrDecoder().decode(image), {"并发任务"})

    @unittest.skipUnless(
        Path(r"C:\Users\x\Desktop\git\卡牌\6.png").exists(),
        "supplied card images are not available",
    )
    def test_roi_retry_decodes_divine_prayer_card(self):
        import cv2
        import numpy as np

        path = Path(r"C:\Users\x\Desktop\git\卡牌\6.png")
        image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)

        self.assertEqual(OpenCvQrBackend().decode(image), {"神之祈愿"})


if __name__ == "__main__":
    unittest.main()
