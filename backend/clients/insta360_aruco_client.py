"""Insta360 Link 2C ArUco 卡牌识别客户端

使用 ArUco 标记替代 QR 码：
- 桌面四角贴 ArUco 标记 → 校准得到单应矩阵 H
- 卡牌上贴 ArUco 标记 → 检测后用 H 转换为世界坐标
- ArUco ID 映射到卡牌名称 → 发送 input.qr_skill 消息

用法:
  python insta360_aruco_client.py --ws-url ws://127.0.0.1:8002/ws --camera-index 0
  
  校准模式（按 'c' 键触发）:
  摄像头对准桌面四角，检测到 4 个角标记后自动校准
  
  检测模式:
  拿卡牌靠近摄像头，检测到 ArUco 标记后发送消息
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import threading
import time
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np
import yaml

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.aruco.calibration import (
    Calibrator,
    aruco_detect,
    dict_id_by_name,
)
from app.services.aruco.geometry import Pose, norm_angle

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "aruco_cards.yaml"


def load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_card_map(config: dict) -> dict[int, dict]:
    cards = config.get("cards", {})
    return {int(k): v for k, v in cards.items()}


def open_camera(camera_index: int):
    if sys.platform == "win32":
        backends = [cv2.CAP_MSMF, cv2.CAP_DSHOW]
    else:
        backends = [cv2.CAP_ANY]
    for backend in backends:
        cap = cv2.VideoCapture(camera_index, backend)
        if cap.isOpened():
            ok, frame = cap.read()
            if ok and frame is not None and frame.size > 0:
                return cap, backend
        cap.release()
    return None, None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Insta360 Link 2C ArUco skill scanner")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--ws-url", default="ws://127.0.0.1:8000/ws")
    parser.add_argument("--preview", action="store_true", default=True)
    parser.add_argument("--no-preview", action="store_false", dest="preview")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--cooldown", type=float, default=2.0, help="同一卡牌发送间隔（秒）")
    return parser.parse_args(argv)


class ArucoDetector:
    def __init__(self, config: dict):
        self.config = config
        corners_cfg = config.get("corners", {})
        self.corner_ids = list(corners_cfg.get("marker_ids", [50, 51, 52, 53]))
        dict_name = corners_cfg.get("dict") or config.get("aruco_dict", "DICT_4X4_50")
        self.dict_id = dict_id_by_name(dict_name)
        self.calibrator = Calibrator(config)
        self.calibrating = False
        self.calibration_frames = []
        self.calibration_needed = 10

    def try_calibrate(self, frame) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        found = aruco_detect(gray, self.dict_id)
        if any(cid in found for cid in self.corner_ids):
            if self.calibrator.calibrate(frame, found):
                return True
        return False

    def detect_cards(self, frame, card_map: dict[int, dict]) -> list[dict]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        found = aruco_detect(gray, self.dict_id)
        results = []
        for mid, quad in found.items():
            if mid in self.corner_ids:
                continue
            if mid not in card_map:
                continue
            card = card_map[mid]
            cx = float(quad[:, 0].mean())
            cy = float(quad[:, 1].mean())
            world_x, world_y = (0.0, 0.0)
            if self.calibrator.calibrated:
                world_x, world_y = self.calibrator.px_to_world((cx, cy))
            up_x = (quad[0][0] + quad[1][0]) / 2.0 - cx
            up_y = (quad[0][1] + quad[1][1]) / 2.0 - cy
            theta = math.atan2(up_y, up_x)
            results.append({
                "marker_id": mid,
                "skill_id": card["id"],
                "skill_name": card["name"],
                "pixel": (cx, cy),
                "world": (world_x, world_y),
                "theta": theta,
                "corners": quad,
            })
        return results


def draw_overlay(frame, detections, calibrator, calibrating, fps, mode):
    h, w = frame.shape[:2]
    overlay = frame.copy()

    for det in detections:
        pts = det["corners"].astype(np.int32)
        cv2.polylines(overlay, [pts], True, (0, 255, 0), 2)
        cx, cy = int(det["pixel"][0]), int(det["pixel"][1])
        label = f"{det['skill_name']}"
        if calibrator.calibrated:
            wx, wy = det["world"]
            label += f" ({wx:.0f},{wy:.0f})"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        y0 = max(cy - th - 8, 0)
        cv2.rectangle(overlay, (cx - tw // 2 - 3, y0), (cx + tw // 2 + 3, y0 + th + 6), (0, 200, 0), -1)
        cv2.putText(overlay, label, (cx - tw // 2, y0 + th + 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)

    if calibrator.calibrated:
        status = f"Calibrated | {fps:.0f} FPS"
        color = (0, 255, 0)
    elif calibrating:
        status = f"CALIBRATING ({len(calibrator.assigned or [])}/4 corners)"
        color = (0, 200, 255)
    else:
        status = f"Press 'c' to calibrate | {fps:.0f} FPS"
        color = (0, 140, 255)
    cv2.putText(overlay, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    if detections:
        cv2.putText(overlay, f"{len(detections)} cards detected", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)

    return overlay


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)
    card_map = load_card_map(config)
    detector = ArucoDetector(config)

    print(f"[aruco] loaded {len(card_map)} card mappings")
    print(f"[aruco] corner markers: {detector.corner_ids}")

    capture, used_backend = open_camera(args.camera_index)
    if capture is None:
        print("[ERROR] cannot open camera")
        return 1
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    capture.set(cv2.CAP_PROP_FPS, args.fps)
    backend_name = "MSMF" if used_backend == cv2.CAP_MSMF else "DSHOW"
    aw = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    ah = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[aruco] camera opened (backend={backend_name}, {aw}x{ah})")

    capture.set(cv2.CAP_PROP_AUTOFOCUS, 1)
    time.sleep(3)
    focus = capture.get(cv2.CAP_PROP_FOCUS)
    capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
    capture.set(cv2.CAP_PROP_FOCUS, focus)
    print(f"[aruco] focus locked at {focus:.0f}")

    ws_holder: dict = {}
    ws_lock = threading.Lock()
    last_send: dict[str, float] = {}

    def ws_send(message: dict) -> None:
        with ws_lock:
            ws = ws_holder.get("ws")
            loop = ws_holder.get("loop")
            if ws and loop:
                try:
                    asyncio.run_coroutine_threadsafe(ws.send(json.dumps(message, ensure_ascii=False)), loop)
                except Exception:
                    pass

    def ws_thread():
        loop = asyncio.new_event_loop()

        async def _run():
            import websockets
            attempts = 0
            while attempts < 5:
                try:
                    async with websockets.connect(args.ws_url) as ws:
                        print(f"[aruco] connected to {args.ws_url}")
                        attempts = 0
                        with ws_lock:
                            ws_holder["ws"] = ws
                            ws_holder["loop"] = loop
                        async for raw in ws:
                            msg = json.loads(raw)
                            if msg.get("topic") == "error":
                                print(f"[aruco] runtime error: {msg['payload'].get('message')}", file=sys.stderr)
                except Exception as exc:
                    attempts += 1
                    print(f"[aruco] ws disconnected ({attempts}/5): {exc}", file=sys.stderr)
                    if attempts < 5:
                        time.sleep(min(0.5 * attempts, 2.0))

        loop.run_until_complete(_run())
        loop.close()

    ws_t = threading.Thread(target=ws_thread, daemon=True)
    ws_t.start()
    time.sleep(1)

    fps_t = time.time()
    fps_n = 0
    fps = 0.0
    mode = "calibrate" if not detector.calibrator.calibrated else "detect"

    print("[aruco] 'c'=calibrate  'q'=quit  'f'=refocus")

    try:
        while True:
            ret, frame = capture.read()
            if not ret:
                time.sleep(0.05)
                continue

            fps_n += 1
            now = time.time()
            if now - fps_t >= 1.0:
                fps = fps_n / (now - fps_t)
                fps_n = 0
                fps_t = now

            detections = detector.detect_cards(frame, card_map)

            for det in detections:
                skill_id = det["skill_id"]
                if now - last_send.get(skill_id, 0) > args.cooldown:
                    message = {
                        "topic": "input.qr_skill",
                        "source": "insta360_link_2c",
                        "timestamp": now,
                        "payload": {
                            "qr_text": det["skill_name"],
                            "skill_id": skill_id,
                            "skill_name": det["skill_name"],
                            "position": {
                                "x": det["world"][0],
                                "y": det["world"][1],
                                "theta": det["theta"],
                            } if detector.calibrator.calibrated else None,
                        },
                    }
                    ws_send(message)
                    last_send[skill_id] = now
                    print(f"[aruco] detected: {det['skill_name']} ({skill_id})")

            overlay = draw_overlay(frame, detections, detector.calibrator, detector.calibrating, fps, mode)

            cv2.imshow("Moonfall - ArUco Skill Scanner", overlay)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("c"):
                print("[aruco] calibrating...")
                if detector.try_calibrate(frame):
                    print(f"[aruco] calibrated! H matrix computed")
                    mode = "detect"
                else:
                    print("[aruco] calibration failed: need 4 corner markers visible")
            elif key == ord("f"):
                capture.set(cv2.CAP_PROP_AUTOFOCUS, 1)
                print("[aruco] refocusing...")
                time.sleep(2.5)
                focus = capture.get(cv2.CAP_PROP_FOCUS)
                capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
                capture.set(cv2.CAP_PROP_FOCUS, focus)
                print(f"[aruco] focus={focus:.0f}")
            elif key == ord("r"):
                detector.calibrator.reset()
                mode = "calibrate"
                print("[aruco] calibration reset")
    finally:
        capture.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
