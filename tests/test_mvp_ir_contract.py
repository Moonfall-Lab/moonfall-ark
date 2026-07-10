import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402


class MvpIrContractTest(unittest.TestCase):
    def setUp(self):
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.addCleanup(self.client_context.__exit__, None, None, None)

    def test_state_matches_mvp_ir_world_payload(self):
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 200)

        state = response.json()
        self.assertEqual(state["game_id"], "moonfall_mvp")
        self.assertEqual(state["schema_version"], "1.0")
        self.assertIn(state["phase"], {"prepare", "command", "action", "resolution", "ended"})
        self.assertIsInstance(state["turn"], int)
        self.assertIn("global", state)
        self.assertGreaterEqual(state["global"]["moon_rage"], 0)
        self.assertLessEqual(state["global"]["moon_rage"], 100)
        self.assertIn(state["global"]["moon_tier"], {"sleep", "alert", "anger", "endgame"})
        self.assertIsInstance(state["factions"], list)
        self.assertIsInstance(state["units"], list)
        self.assertIsInstance(state["zones"], list)
        self.assertIsInstance(state["rank_order"], list)
        self.assertIn("winner", state)

        first_faction = state["factions"][0]
        self.assertEqual(first_faction["id"], "pa")
        self.assertIn("p1", first_faction["players"])
        self.assertIsNone(first_faction["rank"])
        self.assertIn("fuel", first_faction["vars"])
        self.assertIn("ship_hp", first_faction["vars"])
        self.assertIn("declaring_launch", first_faction["vars"])

        first_unit = state["units"][0]
        self.assertIn("id", first_unit)
        self.assertIn("faction", first_unit)
        self.assertIn("kind", first_unit)
        self.assertIn("pose", first_unit)
        self.assertIn("status", first_unit)
        self.assertIn("carrying", first_unit)

    def test_config_exposes_frontend_ids(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)

        config = response.json()
        self.assertEqual(config["game_id"], "moonfall_mvp")
        self.assertIn("factions", config)
        self.assertIn("vars", config)
        self.assertIn("cards", config["inputs"])
        self.assertIn("events", config["director"])
        self.assertEqual(config["factions"][0]["id"], "pa")
        self.assertEqual(config["map"]["zones"][0]["id"], "dust_area")

    def test_inputs_mutate_ir_state_and_emit_events(self):
        declare = self.client.post("/api/input/declare_launch", json={"player_id": "p1"})
        self.assertEqual(declare.status_code, 200)
        self.assertTrue(declare.json()["ok"])
        faction = self._faction("pa", declare.json()["state"])
        self.assertEqual(faction["vars"]["declaring_launch"], 1)

        card = self.client.post("/api/input/card", json={"player_id": "p1", "card_id": "collect_priority"})
        self.assertEqual(card.status_code, 200)
        self.assertEqual(card.json()["event"]["event_type"], "card_input")

        voice = self.client.post("/api/input/voice", json={"player_id": "p1", "text": "一号车去中央采集"})
        self.assertEqual(voice.status_code, 200)
        self.assertTrue(voice.json()["ok"])
        self.assertIn("command", voice.json())
        self.assertEqual(voice.json()["event"]["event_type"], "voice_command")

    def test_debug_set_var_and_trigger_event(self):
        set_var = self.client.post(
            "/api/debug/set_var",
            json={"scope": "faction", "id": "pa", "var": "fuel", "value": 5},
        )
        self.assertEqual(set_var.status_code, 200)
        self.assertEqual(self._faction("pa", set_var.json()["state"])["vars"]["fuel"], 5)

        event = self.client.post("/api/debug/trigger_event", json={"event_id": "dust_storm"})
        self.assertEqual(event.status_code, 200)
        self.assertEqual(event.json()["event"]["event_type"], "dust_storm")

    def test_logs_are_queryable_for_ai_and_functional_records(self):
        self.client.post("/api/input/voice", json={"player_id": "p1", "text": "一号车去中央采集"})
        ai_logs = self.client.get("/api/logs/ai")
        functional_logs = self.client.get("/api/logs/functional")

        self.assertEqual(ai_logs.status_code, 200)
        self.assertEqual(functional_logs.status_code, 200)
        self.assertGreaterEqual(len(ai_logs.json()["items"]), 1)
        self.assertGreaterEqual(len(functional_logs.json()["items"]), 1)

    def _faction(self, faction_id, state):
        for faction in state["factions"]:
            if faction["id"] == faction_id:
                return faction
        self.fail(f"Missing faction {faction_id}")


if __name__ == "__main__":
    unittest.main()
