from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from moonfall_runtime.messages import robot_command_message, state_event_message, state_world_message
from moonfall_runtime.qr import QrDebouncer, recognize_qr_text
from moonfall_runtime.state import GameState
from moonfall_runtime.targeting import choose_target


app = FastAPI(title="Moonfall Runtime", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
state = GameState.initial()
debouncer = QrDebouncer(window_seconds=2.0)
connections: list[WebSocket] = []


class QrInput(BaseModel):
    player_id: str | None = None
    text: str


class HeartRateInput(BaseModel):
    player_id: str
    heart_rate: int


@app.on_event("startup")
async def startup() -> None:
    if os.getenv("MOONFALL_SIM_ROVERS", "1").lower() not in {"0", "false", "no", "off"}:
        asyncio.create_task(_sim_rover_loop(), name="sim-rover-loop")
    if os.getenv("MOONFALL_QR_CAMERA", "").lower() not in {"1", "true", "yes", "on"}:
        return
    loop = asyncio.get_running_loop()
    camera = int(os.getenv("MOONFALL_QR_CAMERA_INDEX", "0"))
    player_id = os.getenv("MOONFALL_QR_PLAYER_ID", "p1")
    thread = threading.Thread(
        target=_camera_scanner_loop,
        args=(loop, camera, player_id),
        name="qr-camera",
        daemon=True,
    )
    thread.start()


@app.get("/api/config")
async def api_config() -> dict[str, Any]:
    return state.config_for_frontend()


@app.get("/api/state")
async def api_state() -> dict[str, Any]:
    return state.world_for_frontend()


@app.post("/api/control/reset")
async def api_reset() -> dict[str, Any]:
    state.reset()
    await broadcast(state_event_message("reset", "游戏状态已重置"))
    await broadcast(state_world_message(state))
    return {"ok": True, "state": state.world_for_frontend()}


@app.post("/api/control/next_turn")
async def api_next_turn() -> dict[str, Any]:
    state.next_turn()
    event = state_event_message(
        "next_turn",
        f"轮到 {state.current_player_id} 识别卡牌",
        {"player_id": state.current_player_id, "faction": state.player_to_faction.get(state.current_player_id)},
    )
    await broadcast(event)
    await broadcast(state_world_message(state))
    return {"ok": True, "state": state.world_for_frontend()}


@app.post("/api/debug/qr")
async def api_debug_qr(body: QrInput) -> dict[str, Any]:
    return await handle_qr_text(body.text, body.player_id or state.current_player_id)


@app.post("/api/input/hr")
async def api_input_hr(body: HeartRateInput) -> dict[str, Any]:
    result = state.update_heart_rate(body.player_id, body.heart_rate)
    if result is None:
        return {"ok": False, "error": "unknown_player", "player_id": body.player_id}
    await broadcast(state_world_message(state))
    return {"ok": True, "hr": result, "state": state.world_for_frontend()}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    connections.append(ws)
    await ws.send_json(state_world_message(state))
    try:
        while True:
            raw = await ws.receive_text()
            await handle_ws_message(ws, raw)
    except WebSocketDisconnect:
        disconnect(ws)
    except Exception:
        disconnect(ws)


async def handle_ws_message(ws: WebSocket, raw: str) -> None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        await ws.send_json(state_event_message("invalid_message", "消息不是合法 JSON"))
        return

    topic = message.get("topic")
    payload = message.get("payload") or {}
    if topic in {"input.qr", "input.card"}:
        text = str(payload.get("text") or payload.get("card") or payload.get("card_id") or "")
        player_id = str(payload.get("player_id") or state.current_player_id)
        result = await handle_qr_text(text, player_id)
        await ws.send_json(result)
        return

    if topic == "perception.pose":
        car_id = str(payload.get("car_id") or payload.get("robot_id") or "")
        if car_id:
            state.update_pose(
                car_id,
                float(payload.get("x", 0.0)),
                float(payload.get("y", 0.0)),
                float(payload.get("theta", 0.0)),
                payload.get("status"),
            )
            await broadcast(state_world_message(state))
        return

    if topic == "sensor.hr":
        player_id = str(payload.get("player_id") or "")
        heart_rate = payload.get("heart_rate")
        if player_id and heart_rate is not None:
            result = state.update_heart_rate(player_id, int(heart_rate))
            if result is not None:
                await broadcast(state_world_message(state))
        return

    if topic == "state.event":
        event_type = payload.get("event_type")
        if event_type == "robot_arrived":
            car_id = str(payload.get("car_id") or payload.get("robot_id") or "")
            unit = state.units.get(car_id)
            landmark_id = str(payload.get("landmark_id") or (unit.target.id if unit and unit.target else ""))
            settlement = state.settle_arrival(car_id, landmark_id)
            if settlement:
                await broadcast(state_event_message("arrival_settled", "到达结算完成", settlement))
                await broadcast(state_world_message(state))
        return


async def handle_qr_text(text: str, player_id: str) -> dict[str, Any]:
    qr_result = recognize_qr_text(text, default_player_id=player_id)
    if not qr_result.supported:
        return {"ok": True, "ignored": True, "qr": qr_result.__dict__}
    if not debouncer.accept(qr_result):
        return {"ok": True, "ignored": True, "duplicate": True, "qr": qr_result.__dict__}

    effective_player_id = qr_result.player_id or player_id
    decision = choose_target(state, effective_player_id, qr_result.card_type or "")
    if decision is None:
        event = state_event_message("no_target", "没有可用目标", {"player_id": effective_player_id, "card_type": qr_result.card_type})
        await broadcast(event)
        return {"ok": False, "ignored": True, "qr": qr_result.__dict__, "event": event}

    command = robot_command_message(decision.unit_id, decision.landmark)
    event = state_event_message(
        "qr_target_selected",
        f"{effective_player_id} 目标已设定：{decision.landmark.name}",
        {
            "player_id": effective_player_id,
            "card_type": decision.card_type,
            "unit_id": decision.unit_id,
            "landmark_id": decision.landmark.id,
            "target": decision.landmark.frontend_target(),
        },
    )
    await broadcast(command)
    await broadcast(event)
    await broadcast(state_world_message(state))
    return {
        "ok": True,
        "qr": qr_result.__dict__,
        "command": command,
        "event": event,
        "state": state.world_for_frontend(),
    }


async def broadcast(message: dict[str, Any]) -> None:
    dead: list[WebSocket] = []
    for ws in connections:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        disconnect(ws)


def disconnect(ws: WebSocket) -> None:
    if ws in connections:
        connections.remove(ws)


async def _sim_rover_loop() -> None:
    """Move rovers toward targets when real hardware is not providing poses."""
    while True:
        changed = False
        events = []
        for unit in state.units.values():
            target = unit.target
            if target is None or unit.status != "moving":
                continue
            dx = target.x_cm - unit.pose.x_cm
            dy = target.y_cm - unit.pose.y_cm
            distance = (dx * dx + dy * dy) ** 0.5
            if distance <= 1.0:
                unit.pose.x_cm = target.x_cm
                unit.pose.y_cm = target.y_cm
                settlement = state.settle_arrival(unit.id, target.id)
                if settlement:
                    events.append(state_event_message("arrival_settled", "到达结算完成", settlement))
                changed = True
                continue

            step = min(3.0, distance)
            unit.pose.x_cm += dx / distance * step
            unit.pose.y_cm += dy / distance * step
            changed = True

        for event in events:
            await broadcast(event)
        if changed:
            await broadcast(state_world_message(state))
        await asyncio.sleep(0.2)


def _camera_scanner_loop(loop: asyncio.AbstractEventLoop, camera: int, player_id: str) -> None:
    try:
        import cv2  # type: ignore
    except ImportError:
        print("[qr] opencv-python is not installed; camera scanner disabled")
        return

    cap = cv2.VideoCapture(camera)
    if not cap.isOpened():
        print(f"[qr] cannot open camera {camera}")
        return

    detector = cv2.QRCodeDetector()
    log_debouncer = QrDebouncer(window_seconds=2.0)
    window = "Moonfall Backend QR Scanner - press q to close scanner"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    print(f"[qr] camera scanner started: camera={camera}, default_player_id={player_id}")

    last_label = "waiting for QR..."
    last_label_time = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.1)
                continue

            raw_values, points = _decode_frame(detector, frame)
            for raw in raw_values:
                qr_result = recognize_qr_text(raw, default_player_id=player_id)
                if not qr_result.supported:
                    if log_debouncer.accept_log(qr_result):
                        print(f"[qr] ignored unsupported: {raw}")
                    last_label = f"ignored: {raw[:40]}"
                    last_label_time = time.time()
                    continue

                future = asyncio.run_coroutine_threadsafe(handle_qr_text(raw, qr_result.player_id or player_id), loop)
                try:
                    result = future.result(timeout=3)
                except Exception as exc:
                    print(f"[qr] failed to process {raw!r}: {exc}")
                    continue
                status = "accepted"
                if result.get("duplicate"):
                    status = "duplicate"
                elif result.get("ignored"):
                    status = "ignored"
                card_type = result.get("qr", {}).get("card_type")
                target = result.get("event", {}).get("payload", {}).get("data", {}).get("target", {})
                target_name = target.get("name") or target.get("landmark_id") or "none"
                print(f"[qr] {status}: raw={raw} card={card_type} target={target_name}")
                last_label = f"{status}: {card_type} -> {target_name}"
                last_label_time = time.time()

            if points is not None:
                _draw_points(cv2, frame, points)
            if time.time() - last_label_time > 3:
                last_label = "waiting for QR..."
            cv2.putText(
                frame,
                last_label,
                (18, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow(window, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("[qr] scanner window closed")
                break
    finally:
        cap.release()
        cv2.destroyWindow(window)


def _decode_frame(detector, frame):
    found, decoded, points, _straight = detector.detectAndDecodeMulti(frame)
    if found and decoded:
        return [item for item in decoded if item], points

    decoded_one, points_one, _straight = detector.detectAndDecode(frame)
    if decoded_one:
        return [decoded_one], points_one
    return [], None


def _draw_points(cv2, frame, points) -> None:
    import numpy as np

    pts = np.asarray(points, dtype=np.int32)
    if pts.ndim == 3:
        for quad in pts:
            cv2.polylines(frame, [quad.reshape(-1, 1, 2)], True, (0, 255, 0), 2)
    elif pts.ndim == 4:
        for quad in pts:
            cv2.polylines(frame, [quad.reshape(-1, 1, 2)], True, (0, 255, 0), 2)
