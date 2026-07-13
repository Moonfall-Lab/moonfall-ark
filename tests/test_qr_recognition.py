import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from moonfall_runtime.qr import QrDebouncer, decode_qr_image, recognize_qr_text  # noqa: E402


class QrRecognitionTest(unittest.TestCase):
    def test_recognizes_supported_chinese_cards(self):
        relic = recognize_qr_text("探索遗迹", default_player_id="p1")
        energy = recognize_qr_text("能量优先", default_player_id="p2")
        collect = recognize_qr_text("采集优先", default_player_id="p1")

        self.assertTrue(relic.supported)
        self.assertEqual(relic.card_type, "explore_relic")
        self.assertEqual(relic.player_id, "p1")
        self.assertTrue(energy.supported)
        self.assertEqual(energy.card_type, "energy_priority")
        self.assertEqual(energy.player_id, "p2")
        self.assertTrue(collect.supported)
        self.assertEqual(collect.card_type, "energy_priority")

    def test_recognizes_json_payload_player_and_card(self):
        result = recognize_qr_text('{"player_id":"p1","card":"探索遗迹"}')

        self.assertTrue(result.supported)
        self.assertEqual(result.player_id, "p1")
        self.assertEqual(result.card_type, "explore_relic")

    def test_recognizes_url_payload(self):
        result = recognize_qr_text("moonfall://card?player=p2&card=energy_priority")

        self.assertTrue(result.supported)
        self.assertEqual(result.player_id, "p2")
        self.assertEqual(result.card_type, "energy_priority")

    def test_ignores_unsupported_cards(self):
        result = recognize_qr_text("攻击")

        self.assertFalse(result.supported)
        self.assertIsNone(result.card_type)
        self.assertEqual(result.reason, "unsupported")

    def test_debounces_repeated_supported_results_only(self):
        now = [100.0]
        debouncer = QrDebouncer(window_seconds=2.0, clock=lambda: now[0])
        result = recognize_qr_text("探索遗迹", default_player_id="p1")

        self.assertTrue(debouncer.accept(result))
        self.assertFalse(debouncer.accept(result))
        now[0] = 103.0
        self.assertTrue(debouncer.accept(result))
        self.assertFalse(debouncer.accept(recognize_qr_text("其它卡", default_player_id="p1")))

    def test_debounces_unsupported_logs(self):
        now = [100.0]
        debouncer = QrDebouncer(window_seconds=2.0, clock=lambda: now[0])
        result = recognize_qr_text("其它卡", default_player_id="p1")

        self.assertTrue(debouncer.accept_log(result))
        self.assertFalse(debouncer.accept_log(result))
        now[0] = 103.0
        self.assertTrue(debouncer.accept_log(result))

    def test_image_decode_reports_missing_opencv_cleanly(self):
        try:
            import cv2  # noqa: F401
        except ImportError:
            with self.assertRaisesRegex(RuntimeError, "opencv-python"):
                decode_qr_image("missing.png")


if __name__ == "__main__":
    unittest.main()
