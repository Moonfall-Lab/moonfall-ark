from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.api.deps import get_voice_parser, get_world_state_manager, robot_command_from_intent
from app.core.constants import (
    RUNTIME_SOURCE,
    TOPIC_CMD_ROBOT,
    TOPIC_INPUT_CARD,
    TOPIC_INPUT_DECLARE_LAUNCH,
    TOPIC_INPUT_VOICE,
    TOPIC_SENSOR_HR,
    TOPIC_STATE_EVENT,
    TOPIC_STATE_WORLD,
)
from app.models.messages import RuntimeMessage, make_error, make_message
from app.services.event_logger import log_ai, log_event


router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: RuntimeMessage | dict[str, Any]) -> None:
        dead_connections: list[WebSocket] = []
        data = self._to_jsonable(message)
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                dead_connections.append(connection)
        for connection in dead_connections:
            self.disconnect(connection)

    async def send_to(self, websocket: WebSocket, message: RuntimeMessage | dict[str, Any]) -> None:
        await websocket.send_json(self._to_jsonable(message))

    def _to_jsonable(self, message: RuntimeMessage | dict[str, Any]) -> dict[str, Any]:
        if isinstance(message, RuntimeMessage):
            return message.model_dump(mode="json")
        return message


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    state_manager = get_world_state_manager()
    await manager.connect(websocket)
    await manager.send_to(websocket, make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
    try:
        while True:
            raw_text = await websocket.receive_text()
            await handle_ws_text(websocket, raw_text)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        manager.disconnect(websocket)
        try:
            await manager.send_to(websocket, make_error("HANDLER_ERROR", str(exc)))
        except Exception:
            pass


async def handle_ws_text(websocket: WebSocket, raw_text: str) -> None:
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError:
        await manager.send_to(websocket, make_error("INVALID_MESSAGE", "消息不是合法 JSON", raw_text))
        return

    try:
        message = RuntimeMessage.model_validate(raw)
    except ValidationError:
        await manager.send_to(
            websocket,
            make_error("INVALID_MESSAGE", "缺少 topic/source/timestamp/payload 字段", raw),
        )
        return

    await route_message(websocket, message)


async def route_message(websocket: WebSocket, message: RuntimeMessage) -> None:
    state_manager = get_world_state_manager()
    log_event(state_manager.get_state().session_id, message.topic, message.source, message.payload)

    try:
        if message.topic == TOPIC_SENSOR_HR:
            await _handle_sensor_hr(message)
            return
        if message.topic == TOPIC_INPUT_VOICE:
            await _handle_input_voice(message)
            return
        if message.topic == TOPIC_INPUT_CARD:
            await _handle_input_card(message)
            return
        if message.topic == TOPIC_INPUT_DECLARE_LAUNCH:
            await _handle_declare_launch(message)
            return
    except (KeyError, TypeError, ValueError) as exc:
        await manager.send_to(
            websocket,
            make_error("INVALID_PAYLOAD", f"payload 字段不完整或类型错误: {exc}", message.model_dump(mode="json")),
        )
        return
    except Exception as exc:
        await manager.send_to(
            websocket,
            make_error("HANDLER_ERROR", f"处理 topic={message.topic} 时失败: {exc}", message.model_dump(mode="json")),
        )
        return

    await manager.send_to(
        websocket,
        make_error("UNKNOWN_TOPIC", f"未知或不允许客户端发送的 topic: {message.topic}", message.model_dump(mode="json")),
    )


async def _handle_sensor_hr(message: RuntimeMessage) -> None:
    state_manager = get_world_state_manager()
    payload = message.payload
    state_manager.update_player_hr(str(payload["player_id"]), int(payload["heart_rate"]))
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))


async def _handle_input_voice(message: RuntimeMessage) -> None:
    state_manager = get_world_state_manager()
    payload = message.payload
    player_id = payload.get("player_id")
    text = str(payload.get("text", ""))
    intent = get_voice_parser().parse(text, player_id)
    command = robot_command_from_intent(intent)
    state_manager.update_unit_from_command(command.robot_id, command.action, command.target_zone)

    faction = state_manager.faction_for_player(player_id)
    event_payload = {
        "event_type": "voice_command",
        "message": f"语音指令已解析：{command.robot_id} -> {command.action}",
        "faction": faction.id if faction is not None else None,
        "data": {"intent": intent.model_dump(mode="json")},
    }
    log_ai(
        state_manager.get_state().session_id,
        "voice_command",
        text,
        {"intent": intent.model_dump(mode="json"), "command": command.model_dump(mode="json")},
    )
    log_event(state_manager.get_state().session_id, TOPIC_STATE_EVENT, RUNTIME_SOURCE, event_payload)

    await manager.broadcast(make_message(TOPIC_CMD_ROBOT, command.model_dump(mode="json")))
    await manager.broadcast(make_message(TOPIC_STATE_EVENT, event_payload))
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))


async def _handle_input_card(message: RuntimeMessage) -> None:
    state_manager = get_world_state_manager()
    payload = message.payload
    data = state_manager.apply_card(str(payload["player_id"]), str(payload["card_id"]))
    event_payload = {
        "event_type": "card_input",
        "message": "收到卡牌输入",
        "faction": data["faction"],
        "data": {"player_id": payload["player_id"], "card_id": payload["card_id"]},
    }
    log_event(state_manager.get_state().session_id, TOPIC_STATE_EVENT, RUNTIME_SOURCE, event_payload)
    await manager.broadcast(make_message(TOPIC_STATE_EVENT, event_payload))
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))


async def _handle_declare_launch(message: RuntimeMessage) -> None:
    state_manager = get_world_state_manager()
    payload = message.payload
    faction = state_manager.declare_launch(str(payload["player_id"]))
    event_payload = {
        "event_type": "rank_locked",
        "message": f"{faction.id} 宣布点火",
        "faction": faction.id,
        "data": {"declaring_launch": 1},
    }
    log_event(state_manager.get_state().session_id, TOPIC_STATE_EVENT, RUNTIME_SOURCE, event_payload)
    await manager.broadcast(make_message(TOPIC_STATE_EVENT, event_payload))
    await manager.broadcast(make_message(TOPIC_STATE_WORLD, state_manager.get_state_dict()))
