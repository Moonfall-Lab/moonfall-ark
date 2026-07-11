import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.qr_skill_scanner import (  # noqa: E402
    QrPresentationGate,
    SkillDefinition,
)
from clients.insta360_qr_client import (  # noqa: E402
    build_qr_skill_message,
    configure_capture,
    parse_args,
    process_frame,
    validate_image_directory,
)


class Insta360QrClientTest(unittest.TestCase):
    def test_build_message_uses_stable_contract(self):
        message = build_qr_skill_message(
            SkillDefinition("ark_repair", "核心修复"),
            timestamp=123.5,
        )

        self.assertEqual(message["topic"], "input.qr_skill")
        self.assertEqual(message["source"], "insta360_link_2c")
        self.assertEqual(message["timestamp"], 123.5)
        self.assertEqual(message["payload"]["qr_text"], "核心修复")
        self.assertEqual(message["payload"]["skill_id"], "ark_repair")
        self.assertEqual(message["payload"]["skill_name"], "核心修复")

    def test_cli_defaults_to_link_2c_capture_profile(self):
        args = parse_args([])

        self.assertEqual(args.camera_index, 0)
        self.assertEqual((args.width, args.height, args.fps), (1920, 1080, 30))
        self.assertEqual(args.ws_url, "ws://127.0.0.1:8000/ws")
        self.assertFalse(args.preview)
        self.assertEqual(args.missing_frame_threshold, 5)

    def test_configure_capture_sets_requested_profile_and_single_buffer(self):
        capture = RecordingCapture()

        configure_capture(capture, width=1920, height=1080, fps=30)

        self.assertEqual(
            capture.values,
            {3: 1920, 4: 1080, 5: 30, 38: 1},
        )

    def test_process_frame_emits_known_skill_once_per_presentation(self):
        decoder = MutableDecoder({"采集优先"})
        gate = QrPresentationGate(missing_frame_threshold=1)
        skills = {"采集优先": SkillDefinition("collect_priority", "采集优先")}

        first = process_frame(object(), decoder, gate, skills, timestamp=1.0)
        repeated = process_frame(object(), decoder, gate, skills, timestamp=2.0)
        decoder.values = set()
        process_frame(object(), decoder, gate, skills, timestamp=3.0)
        decoder.values = {"采集优先"}
        represented = process_frame(object(), decoder, gate, skills, timestamp=4.0)

        self.assertEqual(len(first), 1)
        self.assertEqual(repeated, [])
        self.assertEqual(len(represented), 1)
        self.assertEqual(first[0]["payload"]["skill_id"], "collect_priority")

    @unittest.skipUnless(
        Path(r"C:\Users\x\Desktop\git\卡牌").exists(),
        "supplied card images are not available",
    )
    def test_validation_mode_maps_all_supplied_cards(self):
        results = validate_image_directory(Path(r"C:\Users\x\Desktop\git\卡牌"))

        self.assertEqual(len(results), 10)
        self.assertEqual(results[0].skill_id, "explore_relic")
        self.assertEqual(results[5].skill_id, "divine_prayer")
        self.assertEqual(results[8].skill_id, "ark_repair")


class RecordingCapture:
    def __init__(self):
        self.values = {}

    def set(self, property_id, value):
        self.values[property_id] = value
        return True


class MutableDecoder:
    def __init__(self, values):
        self.values = set(values)

    def decode(self, frame):
        return set(self.values)


if __name__ == "__main__":
    unittest.main()
