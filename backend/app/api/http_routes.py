from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import (
    get_moon_director,
    get_voice_parser,
    get_world_state_manager,
    robot_command_from_intent,
)
from app.api.websocket_routes import manager
from app.core.constants import (
    RUNTIME_SOURCE,
    TOPIC_CMD_ARM,
    TOPIC_CMD_ROBOT,
    TOPIC_INPUT_CARD,
    TOPIC_INPUT_VOICE,
    TOPIC_SENSOR_HR,
    TOPIC_STATE_EVENT,
    TOPIC_STATE_WORLD,
)
from app.models.commands import ArmCommand
from app.models.messages import make_message
from app.services.event_logger import log_event


router = APIRouter()


class HeartRateInput(BaseModel):
    player_id: str
    heart_rate: int


class VoiceInput(BaseModel):
    player_id: str | None = None
    text: str


class CardInput(BaseModel):
    player_id: str | None = None
    card_id: str | None = None
    action: str | None = None
    payload: dict = Field(default_factory=dict)


class SetFuelInput(BaseModel):
    fuel: float


class SetMoonRageInput(BaseModel):
    moon_rage: float


class TriggerArmInput(BaseModel):
    action: str
    target_zone: str | None = "dust_center"


@router.get("/api/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "moonfall-runtime"}


@router.get("/api/state")
async def state() -> dict:
    return get_world_state_manager().get_state_dict()


@router.post("/api/input/hr")
async def input_hr(body: HeartRateInput) -> dict:
    state_manager = get_world_state_manager()
    state_manager.update_player_hr(body.player_id, body.heart_rate)
    payload = body.model_dump(mode="json")
    log_event(state_manager.get_state().session_id, TOPIC_SENSOR_HR, "http", payload)
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {"ok": True, "state": state_manager.get_state_dict()}


@router.post("/api/input/voice")
async def input_voice(body: VoiceInput) -> dict:
    state_manager = get_world_state_manager()
    intent = get_voice_parser().parse(body.text, body.player_id)
    command = robot_command_from_intent(intent)
    voice_payload = body.model_dump(mode="json")
    log_event(state_manager.get_state().session_id, TOPIC_INPUT_VOICE, "http", voice_payload)

    event_payload = {
        "event_type": "voice_command",
        "message": f"语音指令已解析：{command.robot_id} -> {command.action}",
        "intent": intent.model_dump(mode="json"),
    }
    state_manager.add_event(event_payload["message"])
    await manager.broadcast(make_message(TOPIC_CMD_ROBOT, command.model_dump(mode="json")))
    await manager.broadcast(make_message(TOPIC_STATE_EVENT, event_payload))
    return {"ok": True, "intent": intent.model_dump(mode="json"), "command": command.model_dump(mode="json")}


@router.post("/api/input/card")
async def input_card(body: CardInput) -> dict:
    state_manager = get_world_state_manager()
    payload = body.model_dump(mode="json")
    log_event(state_manager.get_state().session_id, TOPIC_INPUT_CARD, "http", payload)
    event_payload = {"event_type": "card_input", "message": "收到卡牌输入", "card": payload}
    state_manager.add_event(event_payload["message"])
    await manager.broadcast(make_message(TOPIC_STATE_EVENT, event_payload))
    return {"ok": True, "event": event_payload}


@router.post("/api/debug/reset")
async def debug_reset() -> dict:
    state_manager = get_world_state_manager()
    state_manager.reset()
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {"ok": True, "state": state_manager.get_state_dict()}


@router.post("/api/debug/set_fuel")
async def debug_set_fuel(body: SetFuelInput) -> dict:
    state_manager = get_world_state_manager()
    state_manager.set_fuel(body.fuel)
    log_event(state_manager.get_state().session_id, "debug.set_fuel", "http", body.model_dump(mode="json"))
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {"ok": True, "state": state_manager.get_state_dict()}


@router.post("/api/debug/set_moon_rage")
async def debug_set_moon_rage(body: SetMoonRageInput) -> dict:
    state_manager = get_world_state_manager()
    state_manager.set_moon_rage(body.moon_rage)
    log_event(state_manager.get_state().session_id, "debug.set_moon_rage", "http", body.model_dump(mode="json"))
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {"ok": True, "state": state_manager.get_state_dict()}


@router.post("/api/debug/trigger_arm")
async def debug_trigger_arm(body: TriggerArmInput) -> dict:
    state_manager = get_world_state_manager()
    command = ArmCommand(
        command_id=str(uuid4()),
        action=body.action,
        target_zone=body.target_zone,
        safe_mode=get_moon_director().safe_mode,
    )
    payload = command.model_dump(mode="json")
    log_event(state_manager.get_state().session_id, TOPIC_CMD_ARM, RUNTIME_SOURCE, payload)
    await manager.broadcast(make_message(TOPIC_CMD_ARM, payload))
    return {"ok": True, "command": payload}


@router.post("/api/debug/trigger_boss")
async def debug_trigger_boss() -> dict:
    state_manager = get_world_state_manager()
    state_manager.set_fuel(70)
    state_manager.set_boss_mode(True)
    event_payload = {"event_type": "enter_boss", "message": "调试触发 Boss 战"}
    state_manager.add_event(event_payload["message"])
    log_event(state_manager.get_state().session_id, TOPIC_STATE_EVENT, RUNTIME_SOURCE, event_payload)
    await manager.broadcast(make_message(TOPIC_STATE_EVENT, event_payload))
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    return {"ok": True, "event": event_payload, "state": state_manager.get_state_dict()}
