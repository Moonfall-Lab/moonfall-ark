import sys
import unittest
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.api.deps import get_world_state_manager  # noqa: E402
from app.main import app  # noqa: E402


class QrSkillRuntimeTest(unittest.TestCase):
    def setUp(self):
        get_world_state_manager().reset()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.addCleanup(self.client_context.__exit__, None, None, None)

    def test_valid_qr_skill_broadcasts_event_without_mutating_state(self):
        before = deepcopy(self.client.get("/api/state").json())

        with self.client.websocket_connect("/ws") as websocket:
            self._receive_until(websocket, "state.world")
            websocket.send_json(self._message())
            event = self._receive_until(websocket, "state.event", "error")

        self.assertEqual(event["topic"], "state.event")
        self.assertEqual(event["payload"]["event_type"], "qr_skill_detected")
        self.assertEqual(event["payload"]["data"]["skill_id"], "teleport_steal")
        self.assertEqual(self.client.get("/api/state").json(), before)

    def test_unknown_qr_text_is_rejected(self):
        error = self._send_and_receive(
            self._message(qr_text="陌生卡牌", skill_name="陌生卡牌", skill_id="unknown")
        )

        self.assertEqual(error["topic"], "error")
        self.assertEqual(error["payload"]["code"], "INVALID_PAYLOAD")

    def test_mismatched_skill_id_is_rejected(self):
        error = self._send_and_receive(self._message(skill_id="ark_repair"))

        self.assertEqual(error["topic"], "error")
        self.assertEqual(error["payload"]["code"], "INVALID_PAYLOAD")

    def test_missing_skill_name_is_rejected(self):
        message = self._message()
        del message["payload"]["skill_name"]

        error = self._send_and_receive(message)

        self.assertEqual(error["topic"], "error")
        self.assertEqual(error["payload"]["code"], "INVALID_PAYLOAD")

    def _message(self, **payload_overrides):
        payload = {
            "qr_text": "瞬移偷窃",
            "skill_id": "teleport_steal",
            "skill_name": "瞬移偷窃",
        }
        payload.update(payload_overrides)
        return {
            "topic": "input.qr_skill",
            "source": "insta360_link_2c",
            "timestamp": 1720000000.0,
            "payload": payload,
        }

    def _receive_until(self, websocket, *topics):
        for _ in range(10):
            message = websocket.receive_json()
            if message.get("topic") in topics:
                return message
        self.fail(f"Did not receive any topic in {topics}")

    def _send_and_receive(self, message):
        with self.client.websocket_connect("/ws") as websocket:
            self._receive_until(websocket, "state.world")
            websocket.send_json(message)
            return self._receive_until(websocket, "state.event", "error")


if __name__ == "__main__":
    unittest.main()
