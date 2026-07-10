from __future__ import annotations

from uuid import uuid4

from app.models.commands import RobotCommand, VoiceIntent
from app.runtime.behavior_ai import BehaviorAI
from app.runtime.director import MoonDirector
from app.runtime.rule_engine import RuleEngine
from app.runtime.world_state import WorldStateManager
from app.services.voice_parser import VoiceParser


world_state_manager = WorldStateManager()
voice_parser = VoiceParser(config=world_state_manager.config)
behavior_ai = BehaviorAI()
rule_engine = RuleEngine(world_state_manager.config)
moon_director = MoonDirector(world_state_manager.config)


def get_world_state_manager() -> WorldStateManager:
    return world_state_manager


def get_voice_parser() -> VoiceParser:
    return voice_parser


def get_behavior_ai() -> BehaviorAI:
    return behavior_ai


def get_rule_engine() -> RuleEngine:
    return rule_engine


def get_moon_director() -> MoonDirector:
    return moon_director


def robot_command_from_intent(intent: VoiceIntent) -> RobotCommand:
    unit = world_state_manager.unit_for_player(intent.player_id)
    robot_id = intent.robot_id or (unit.id if unit is not None else None) or "r1"
    return RobotCommand(
        command_id=str(uuid4()),
        robot_id=robot_id,
        action=intent.action,
        target_zone=intent.target_zone,
        priority=max(0.5, min(2.0, intent.confidence * 2)),
        avoid=intent.avoid,
    )
