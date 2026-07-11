import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402


class MinimalRuntimeContractTest(unittest.TestCase):
    def test_pose_message_updates_r0_in_centimeters(self):
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as websocket:
                websocket.receive_json()
                websocket.send_json({
                    "topic": "perception.pose",
                    "source": "rover_agent",
                    "timestamp": 1.0,
                    "payload": {
                        "car_id": "r0", "x": 30.0, "y": 20.0,
                        "theta": 1.57, "status": "moving",
                    },
                })
            state = client.get("/api/state").json()

        r0 = next(unit for unit in state["units"] if unit["id"] == "r0")
        self.assertEqual(r0["pose"], {"x": 30.0, "y": 20.0, "theta": 1.57})
        self.assertEqual(r0["status"], "moving")

    def test_robot_arrival_event_updates_r0_status(self):
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as websocket:
                websocket.receive_json()
                websocket.send_json({
                    "topic": "state.event",
                    "source": "rover_agent",
                    "timestamp": 1.0,
                    "payload": {
                        "event_type": "robot_arrived", "car_id": "r0",
                        "command_id": "card-1",
                    },
                })
                event = websocket.receive_json()
            state = client.get("/api/state").json()

        self.assertEqual(event["topic"], "state.event")
        self.assertEqual(next(unit for unit in state["units"] if unit["id"] == "r0")["status"], "arrived")


if __name__ == "__main__":
    unittest.main()
