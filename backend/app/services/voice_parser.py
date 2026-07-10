from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.models.commands import VoiceIntent
from app.services.llm_provider import LLMProvider


DEFAULT_ACTIONS = ["move_to", "collect", "attack", "return_base", "repair", "ignition_confirm", "stop"]


class VoiceParser:
    """把玩家自然语言解析成机器人意图。允许的动作、区域、机器人 id 全部从加载的游戏配置派生，
    不再写死常量，换配置即换游戏，语音也随之改变。"""

    def __init__(self, llm_provider: LLMProvider | None = None, config: dict[str, Any] | None = None) -> None:
        self.llm_provider = llm_provider or LLMProvider()
        config = config or {}

        self._zones = [z for z in config.get("map", {}).get("zones", []) if z.get("id")]
        self.allowed_zones = {z["id"] for z in self._zones}
        self.allowed_robots = {u["id"] for u in config.get("units", []) if u.get("id")}

        voice_cfg = config.get("inputs", {}).get("voice", {}) or {}
        actions = voice_cfg.get("action_space") or DEFAULT_ACTIONS
        self._actions = list(actions)
        self.allowed_actions = set(self._actions)

        self.system_prompt = self._build_prompt()

    def _build_prompt(self) -> str:
        actions = ", ".join(self._actions)
        robots = ", ".join(sorted(self.allowed_robots)) or "r1"
        zones = ", ".join(z["id"] for z in self._zones) or "无"
        return (
            "你是 Moonfall Runtime 的语音指令解析器。\n"
            "你只能把玩家自然语言解析成 JSON，不要输出解释。\n"
            f"允许动作 action 只能是：{actions}。\n"
            f"允许 robot_id 只能是：{robots} 或 null。\n"
            f"允许 target_zone 只能是：{zones} 或 null。\n"
            "输出 JSON 格式：\n"
            "{\n"
            '  "intent_type": "robot_command",\n'
            '  "player_id": "p1",\n'
            '  "robot_id": "r1",\n'
            '  "action": "move_to",\n'
            '  "target_zone": null,\n'
            '  "avoid": [],\n'
            '  "confidence": 0.8\n'
            "}\n"
        )

    def parse(self, text: str, player_id: str | None = None) -> VoiceIntent:
        try:
            llm_text = self.llm_provider.chat_json(self.system_prompt, text)
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
        if intent.action not in self.allowed_actions:
            raise ValueError(f"invalid action: {intent.action}")
        if intent.robot_id is not None and intent.robot_id not in self.allowed_robots:
            raise ValueError(f"invalid robot_id: {intent.robot_id}")
        if intent.target_zone is not None and intent.target_zone not in self.allowed_zones:
            raise ValueError(f"invalid target_zone: {intent.target_zone}")
        for zone_id in intent.avoid:
            if zone_id not in self.allowed_zones:
                raise ValueError(f"invalid avoid zone: {zone_id}")

    def _parse_by_rules(self, text: str, player_id: str | None) -> VoiceIntent:
        robot_id = self._find_robot(text) or self._robot_from_player(player_id)
        target_zone = self._find_zone(text)
        hazard = self._zone_of_kind("hazard")
        avoid = [hazard] if hazard and any(word in text for word in ("绕开", "避开", "月尘")) else []
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
                action=self._default_action(),
                target_zone=None,
                avoid=[],
                confidence=0.3,
            )

    def _default_action(self) -> str:
        if "move_to" in self.allowed_actions:
            return "move_to"
        return self._actions[0] if self._actions else "move_to"

    def _zone_of_kind(self, kind: str) -> str | None:
        for zone in self._zones:
            if zone.get("kind") == kind:
                return zone["id"]
        return None

    def _find_robot(self, text: str) -> str | None:
        robot_keywords = {
            "r1": ("一号", "1号", "一号车", "1号车", "r1"),
            "r2": ("二号", "2号", "二号车", "2号车", "r2"),
            "r3": ("三号", "3号", "三号车", "3号车", "r3"),
            "r4": ("四号", "4号", "四号车", "4号车", "r4"),
        }
        for robot_id, words in robot_keywords.items():
            if robot_id in self.allowed_robots and any(word in text for word in words):
                return robot_id
        return None

    def _robot_from_player(self, player_id: str | None) -> str | None:
        mapping = {"p1": "r1", "p2": "r2", "p3": "r3", "p4": "r4"}
        robot_id = mapping.get(player_id or "")
        return robot_id if robot_id in self.allowed_robots else None

    def _find_zone(self, text: str) -> str | None:
        if any(word in text for word in ("月尘", "灾难")):
            zone = self._zone_of_kind("hazard")
            if zone:
                return zone
        if any(word in text for word in ("中央", "中间", "补给", "资源", "燃料")):
            zone = self._zone_of_kind("supply") or self._zone_of_kind("resource")
            if zone:
                return zone
        if any(word in text for word in ("基地", "回家", "发射", "升空", "维修")):
            zone = self._zone_of_kind("base")
            if zone:
                return zone
        return None

    def _find_action(self, text: str, target_zone: str | None, avoid: list[str]) -> str:
        candidates: list[tuple[tuple[str, ...], str]] = [
            (("停",), "stop"),
            (("回来", "返回", "回家"), "return_base"),
            (("采集", "燃料"), "collect"),
            (("攻击", "打", "炮击"), "attack"),
            (("维修", "修"), "repair"),
            (("点火", "升空"), "ignition_confirm"),
            (("护送",), "escort"),
        ]
        for words, action in candidates:
            if action in self.allowed_actions and any(word in text for word in words):
                return action
        return self._default_action()
