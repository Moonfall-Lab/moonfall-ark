from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.core.constants import ALLOWED_ACTIONS, ALLOWED_ROBOT_IDS, ALLOWED_ZONES
from app.models.commands import VoiceIntent
from app.services.llm_provider import LLMProvider


SYSTEM_PROMPT = """你是 Moonfall Runtime 的语音指令解析器。
你只能把玩家自然语言解析成 JSON，不要输出解释。
允许动作 action 只能是：move_to, collect, escort, avoid_and_move, return_base, stop。
允许 robot_id 只能是：r1, r2, r3, r4 或 null。
允许 target_zone 只能是：base, resource_ne, resource_sw, relic_nw, relic_se, dust_center 或 null。
输出 JSON 格式：
{
  "intent_type": "robot_command",
  "player_id": "p1",
  "robot_id": "r1",
  "action": "move_to",
  "target_zone": "resource_ne",
  "avoid": ["dust_center"],
  "confidence": 0.8
}
"""


class VoiceParser:
    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or LLMProvider()

    def parse(self, text: str, player_id: str | None = None) -> VoiceIntent:
        try:
            llm_text = self.llm_provider.chat_json(SYSTEM_PROMPT, text)
            parsed = self._load_json(llm_text)
            parsed.setdefault("player_id", player_id)
            intent = VoiceIntent.model_validate(parsed)
            self._validate_intent(intent)
            return intent
        except Exception:
            return self._parse_by_rules(text, player_id)

    def _load_json(self, raw: str) -> dict[str, Any]:
        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`").replace("json\n", "", 1).strip()
        return json.loads(stripped)

    def _validate_intent(self, intent: VoiceIntent) -> None:
        if intent.action not in ALLOWED_ACTIONS:
            raise ValueError(f"invalid action: {intent.action}")
        if intent.robot_id is not None and intent.robot_id not in ALLOWED_ROBOT_IDS:
            raise ValueError(f"invalid robot_id: {intent.robot_id}")
        if intent.target_zone is not None and intent.target_zone not in ALLOWED_ZONES:
            raise ValueError(f"invalid target_zone: {intent.target_zone}")
        for zone_id in intent.avoid:
            if zone_id not in ALLOWED_ZONES:
                raise ValueError(f"invalid avoid zone: {zone_id}")

    def _parse_by_rules(self, text: str, player_id: str | None) -> VoiceIntent:
        robot_id = self._find_robot(text) or self._robot_from_player(player_id)
        target_zone = self._find_zone(text)
        avoid = ["dust_center"] if any(word in text for word in ("绕开", "避开", "月尘")) else []
        action = self._find_action(text, target_zone, avoid)

        try:
            intent = VoiceIntent(
                intent_type="robot_command",
                player_id=player_id,
                robot_id=robot_id,
                action=action,
                target_zone=target_zone,
                avoid=avoid,
                confidence=0.6,
            )
            self._validate_intent(intent)
            return intent
        except (ValidationError, ValueError):
            return VoiceIntent(
                intent_type="robot_command",
                player_id=player_id,
                robot_id=robot_id,
                action="move_to",
                target_zone=target_zone or "resource_ne",
                avoid=avoid,
                confidence=0.3,
            )

    def _find_robot(self, text: str) -> str | None:
        robot_keywords = {
            "r1": ("一号", "1号", "一号车", "1号车", "r1"),
            "r2": ("二号", "2号", "二号车", "2号车", "r2"),
            "r3": ("三号", "3号", "三号车", "3号车", "r3"),
            "r4": ("四号", "4号", "四号车", "4号车", "r4"),
        }
        for robot_id, words in robot_keywords.items():
            if any(word in text for word in words):
                return robot_id
        return None

    def _robot_from_player(self, player_id: str | None) -> str | None:
        mapping = {"p1": "r1", "p2": "r2", "p3": "r3", "p4": "r4"}
        return mapping.get(player_id or "")

    def _find_zone(self, text: str) -> str | None:
        if any(word in text for word in ("东北", "右上", "资源区", "资源", "东区")):
            return "resource_ne"
        if any(word in text for word in ("西南", "左下")):
            return "resource_sw"
        if any(word in text for word in ("基地", "回家", "维修")):
            return "base"
        if "东南" in text:
            return "relic_se"
        if any(word in text for word in ("遗迹", "西北")):
            return "relic_nw"
        if "月尘" in text:
            return "dust_center"
        return None

    def _find_action(self, text: str, target_zone: str | None, avoid: list[str]) -> str:
        if "停" in text:
            return "stop"
        if any(word in text for word in ("回来", "返回", "回家")):
            return "return_base"
        if any(word in text for word in ("采集", "燃料")):
            return "collect"
        if "护送" in text:
            return "escort"
        if avoid:
            return "avoid_and_move"
        if target_zone:
            return "move_to"
        return "move_to"
