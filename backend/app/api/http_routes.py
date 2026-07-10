from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import get_voice_parser, get_world_state_manager, robot_command_from_intent
from app.api.websocket_routes import manager
from app.core.constants import (
    RUNTIME_SOURCE,
    TOPIC_CMD_ARM,
    TOPIC_CMD_ROBOT,
    TOPIC_INPUT_CARD,
    TOPIC_INPUT_DECLARE_LAUNCH,
    TOPIC_INPUT_VOICE,
    TOPIC_SENSOR_HR,
    TOPIC_STATE_EVENT,
    TOPIC_STATE_WORLD,
)
from app.models.commands import ArmCommand
from app.models.messages import make_message
from app.services.event_logger import list_ai_logs, list_functional_logs, log_ai, log_event


router = APIRouter()


class ConfigLoadInput(BaseModel):
    config_path: str | None = None
    config: dict[str, Any] | None = None


class HeartRateInput(BaseModel):
    player_id: str
    heart_rate: int


class VoiceInput(BaseModel):
    player_id: str | None = None
    text: str


class CardInput(BaseModel):
    player_id: str
    card_id: str


class DeclareLaunchInput(BaseModel):
    player_id: str


class SetVarInput(BaseModel):
    scope: str
    id: str
    var: str
    value: Any


class TriggerEventInput(BaseModel):
    event_id: str
    faction: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class TriggerArmInput(BaseModel):
    action: str
    target_zone: str | None = "dust_area"
    intensity: float = 0.6


@router.get("/api/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "moonfall-runtime"}


@router.get("/api/state")
async def state() -> dict[str, Any]:
    return get_world_state_manager().get_state_dict()


@router.get("/api/config")
async def config() -> dict[str, Any]:
    return get_world_state_manager().get_config_dict()


@router.post("/api/config/load")
async def config_load(body: ConfigLoadInput) -> dict[str, Any]:
    state_manager = get_world_state_manager()
    state_manager.load_config(config_path=body.config_path, config=body.config)
    payload = {"config_path": body.config_path, "has_inline_config": body.config is not None}
    log_event(state_manager.get_state().session_id, "config.load", "http", payload)
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {"ok": True, "config": state_manager.get_config_dict(), "state": state_manager.get_state_dict()}


@router.post("/api/control/start")
async def control_start() -> dict[str, Any]:
    state_manager = get_world_state_manager()
    state_manager.start()
    log_event(state_manager.get_state().session_id, "control.start", "http", {})
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {"ok": True, "state": state_manager.get_state_dict()}


@router.post("/api/control/reset")
async def control_reset() -> dict[str, Any]:
    state_manager = get_world_state_manager()
    state_manager.reset()
    log_event(state_manager.get_state().session_id, "control.reset", "http", {})
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {"ok": True, "state": state_manager.get_state_dict()}


@router.post("/api/input/hr")
async def input_hr(body: HeartRateInput) -> dict[str, Any]:
    state_manager = get_world_state_manager()
    state_manager.update_player_hr(body.player_id, body.heart_rate)
    payload = body.model_dump(mode="json")
    log_event(state_manager.get_state().session_id, TOPIC_SENSOR_HR, "http", payload)
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {"ok": True, "state": state_manager.get_state_dict()}


@router.post("/api/input/voice")
async def input_voice(body: VoiceInput) -> dict[str, Any]:
    state_manager = get_world_state_manager()
    intent = get_voice_parser().parse(body.text, body.player_id)
    command = robot_command_from_intent(intent)
    state_manager.update_unit_from_command(command.robot_id, command.action, command.target_zone)

    event_payload = {
        "event_type": "voice_command",
        "message": f"语音指令已解析：{command.robot_id} -> {command.action}",
        "faction": (state_manager.faction_for_player(body.player_id).id if body.player_id else None),
        "data": {"intent": intent.model_dump(mode="json")},
    }
    log_event(state_manager.get_state().session_id, TOPIC_INPUT_VOICE, "http", body.model_dump(mode="json"))
    log_event(state_manager.get_state().session_id, TOPIC_STATE_EVENT, RUNTIME_SOURCE, event_payload)
    log_ai(
        state_manager.get_state().session_id,
        "voice_command",
        body.text,
        {"intent": intent.model_dump(mode="json"), "command": command.model_dump(mode="json")},
    )

    await manager.broadcast(make_message(TOPIC_CMD_ROBOT, command.model_dump(mode="json")))
    await manager.broadcast(make_message(TOPIC_STATE_EVENT, event_payload))
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {
        "ok": True,
        "intent": intent.model_dump(mode="json"),
        "command": command.model_dump(mode="json"),
        "event": event_payload,
        "state": state_manager.get_state_dict(),
    }


@router.post("/api/input/card")
async def input_card(body: CardInput) -> dict[str, Any]:
    state_manager = get_world_state_manager()
    data = state_manager.apply_card(body.player_id, body.card_id)
    event_payload = {
        "event_type": "card_input",
        "message": "收到卡牌输入",
        "faction": data["faction"],
        "data": {"player_id": body.player_id, "card_id": body.card_id},
    }
    log_event(state_manager.get_state().session_id, TOPIC_INPUT_CARD, "http", body.model_dump(mode="json"))
    log_event(state_manager.get_state().session_id, TOPIC_STATE_EVENT, RUNTIME_SOURCE, event_payload)
    await manager.broadcast(make_message(TOPIC_STATE_EVENT, event_payload))
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {"ok": True, "event": event_payload, "state": state_manager.get_state_dict()}


@router.post("/api/input/declare_launch")
async def input_declare_launch(body: DeclareLaunchInput) -> dict[str, Any]:
    state_manager = get_world_state_manager()
    faction = state_manager.declare_launch(body.player_id)
    event_payload = {
        "event_type": "rank_locked",
        "message": f"{faction.id} 宣布点火",
        "faction": faction.id,
        "data": {"declaring_launch": 1},
    }
    log_event(state_manager.get_state().session_id, TOPIC_INPUT_DECLARE_LAUNCH, "http", body.model_dump(mode="json"))
    log_event(state_manager.get_state().session_id, TOPIC_STATE_EVENT, RUNTIME_SOURCE, event_payload)
    await manager.broadcast(make_message(TOPIC_STATE_EVENT, event_payload))
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {"ok": True, "event": event_payload, "state": state_manager.get_state_dict()}


@router.post("/api/debug/set_var")
async def debug_set_var(body: SetVarInput) -> dict[str, Any]:
    state_manager = get_world_state_manager()
    state_manager.set_var(body.scope, body.id, body.var, body.value)
    payload = body.model_dump(mode="json")
    log_event(state_manager.get_state().session_id, "debug.set_var", "http", payload)
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {"ok": True, "state": state_manager.get_state_dict()}


@router.post("/api/debug/trigger_event")
async def debug_trigger_event(body: TriggerEventInput) -> dict[str, Any]:
    state_manager = get_world_state_manager()
    event_payload = state_manager.trigger_event(body.event_id, body.faction, body.data or None)
    log_event(state_manager.get_state().session_id, "debug.trigger_event", "http", body.model_dump(mode="json"))
    log_event(state_manager.get_state().session_id, TOPIC_STATE_EVENT, RUNTIME_SOURCE, event_payload)
    await manager.broadcast(make_message(TOPIC_STATE_EVENT, event_payload))
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {"ok": True, "event": event_payload, "state": state_manager.get_state_dict()}


@router.post("/api/debug/trigger_arm")
async def debug_trigger_arm(body: TriggerArmInput) -> dict[str, Any]:
    state_manager = get_world_state_manager()
    command = ArmCommand(
        command_id=str(uuid4()),
        action=body.action,
        target_zone=body.target_zone,
        intensity=body.intensity,
    )
    payload = command.model_dump(mode="json")
    log_event(state_manager.get_state().session_id, TOPIC_CMD_ARM, RUNTIME_SOURCE, payload)
    await manager.broadcast(make_message(TOPIC_CMD_ARM, payload))
    return {"ok": True, "command": payload}


@router.get("/api/logs/ai")
async def logs_ai(limit: int = 100) -> dict[str, Any]:
    return {"items": list_ai_logs(limit)}


@router.get("/api/logs/functional")
async def logs_functional(limit: int = 100) -> dict[str, Any]:
    return {"items": list_functional_logs(limit)}
