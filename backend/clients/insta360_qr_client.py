"""Insta360 Link 2C QR 卡牌识别客户端（精确定位版）

结合 moonfall 的单应矩阵方法：
- 桌面四角 ArUco 标记 → 校准得到单应矩阵 H（像素 → 世界厘米）
- 卡牌 QR 码 4 角点通过 H 变换 → 精确世界坐标 (x, y, theta)
- cv2.QRCodeDetector 解码识别卡牌

用法:
  python insta360_qr_client.py --ws-url ws://127.0.0.1:8002/ws --camera-index 0

  校准: 按 'c' 键，摄像头需看到桌面四角的 ArUco 标记
  检测: 拿卡牌靠近摄像头，显示精确世界坐标
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import threading
import time
from collections import deque
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
    apply_h,
)
from app.services.aruco.geometry import norm_angle

CONFIG_PATH = BACKEND_DIR / "configs" / "moonfall.yaml"
CARD_DIR = Path(r"C:\Users\17674\Desktop\agent\图片识别\卡牌\二维码")

TRACK_TIMEOUT = 3.0


# ── 配置加载 ──────────────────────────────────────────────

def load_card_qr_map(card_dir: Path) -> dict[str, str]:
    """扫描二维码图片目录，建立 QR 内容 → 文件名（卡牌名）映射"""
    detector = cv2.QRCodeDetector()
    qr_to_name: dict[str, str] = {}
    for f in sorted(card_dir.glob("*.png")):
        img = cv2.imdecode(np.fromfile(f, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        data, _, _ = detector.detectAndDecode(img)
        if data and data.strip():
            qr_to_name[data.strip()] = f.stem
    return qr_to_name


def load_skill_map(config_path: Path) -> dict[str, dict]:
    """从 moonfall.yaml 加载 skill_name → {skill_id, skill_name}"""
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    inputs = config.get("inputs", {})
    skills: dict[str, dict] = {}
    for section in ("cards", "relic_cards"):
        for entry in inputs.get(section, []):
            name = str(entry.get("name", "")).strip()
            if name:
                skills[name] = {"skill_id": entry["id"], "skill_name": name}
    return skills


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
    parser = argparse.ArgumentParser(description="Insta360 QR scanner with homography positioning")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--ws-url", default="ws://127.0.0.1:8000/ws")
    parser.add_argument("--preview", action="store_true", default=True)
    parser.add_argument("--no-preview", action="store_false", dest="preview")
    parser.add_argument("--cooldown", type=float, default=2.0)
    parser.add_argument("--card-dir", type=Path, default=CARD_DIR)
    # ArUco 校准参数
    parser.add_argument("--corner-ids", type=int, nargs=4, default=[50, 51, 52, 53],
                        help="桌面四角 ArUco 标记 ID")
    parser.add_argument("--table-width", type=float, default=120.0, help="桌面宽度（厘米）")
    parser.add_argument("--table-height", type=float, default=120.0, help="桌面高度（厘米）")
    parser.add_argument("--aruco-dict", default="DICT_4X4_50")
    return parser.parse_args(argv)


# ── QR 检测线程 ───────────────────────────────────────────

class QrDetectThread(threading.Thread):
    """后台 QR 解码线程，返回 QR 内容 + 4 角点像素坐标"""

    def __init__(self, qr_to_name: dict[str, str], skill_map: dict[str, dict]):
        super().__init__(daemon=True)
        self.qr_to_name = qr_to_name
        self.skill_map = skill_map
        self.buffer: deque = deque(maxlen=5)
        self.lock = threading.Lock()
        self.result: dict | None = None
        self.result_time = 0.0
        self.running = True
        self._detector = cv2.QRCodeDetector()

    def update_frame(self, frame) -> None:
        with self.lock:
            self.buffer.append(frame.copy())

    def get_result(self) -> dict | None:
        if self.result and time.time() - self.result_time < 0.3:
            return self.result
        return None

    def _try_decode(self, img, detector) -> dict | None:
        """尝试用一种预处理图检测 QR 码并解码"""
        # multi
        detected, decoded_info, points, _ = detector.detectAndDecodeMulti(img)
        if detected and points is not None:
            for i, value in enumerate(decoded_info):
                if value and value.strip() in self.qr_to_name:
                    skill = self.skill_map.get(value.strip())
                    if skill:
                        return {
                            "skill_name": skill["skill_name"],
                            "skill_id": skill["skill_id"],
                            "points": np.asarray(points[i], dtype=np.float64).reshape(-1, 2),
                        }
        # single
        value, single_points, _ = detector.detectAndDecode(img)
        if value and value.strip() in self.qr_to_name:
            skill = self.skill_map.get(value.strip())
            if skill and single_points is not None:
                return {
                    "skill_name": skill["skill_name"],
                    "skill_id": skill["skill_id"],
                    "points": np.asarray(single_points, dtype=np.float64).reshape(-1, 2),
                }
        return None

    def _decode(self, frame) -> dict | None:
        detector = self._detector
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame

        # 策略 1: 原始灰度（最快）
        result = self._try_decode(gray, detector)
        if result:
            return result

        # 策略 2: OTSU 二值化（对深色卡牌 QR 码有效）
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        result = self._try_decode(otsu, detector)
        if result:
            return result

        # 策略 3: CLAHE 增强对比度
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        result = self._try_decode(enhanced, detector)
        if result:
            return result

        # 策略 4: CLAHE + OTSU
        _, clahe_otsu = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        result = self._try_decode(clahe_otsu, detector)
        if result:
            return result

        # 策略 5: 放大 2x（QR 码太小时用）
        h, w = gray.shape
        big = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
        result = self._try_decode(big, detector)
        if result:
            return result

        # 策略 6: ROI 放大重试（有 QR 框但解码失败时用）
        value, single_points, _ = detector.detectAndDecode(gray)
        if single_points is not None:
            pts = np.asarray(single_points).reshape(-1, 2)
            x_min, y_min = np.floor(pts.min(axis=0)).astype(int)
            x_max, y_max = np.ceil(pts.max(axis=0)).astype(int)
            qw = max(1, x_max - x_min)
            qh = max(1, y_max - y_min)
            pad = max(12, int(max(qw, qh) * 0.2))
            fh, fw = frame.shape[:2]
            x1 = max(0, x_min - pad)
            y1 = max(0, y_min - pad)
            x2 = min(fw, x_max + pad)
            y2 = min(fh, y_max + pad)
            crop = frame[y1:y2, x1:x2]
            bordered = cv2.copyMakeBorder(crop, 32, 32, 32, 32, cv2.BORDER_CONSTANT, value=255)
            resized = cv2.resize(bordered, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
            retry_val, retry_pts, _ = detector.detectAndDecode(resized)
            if retry_val and retry_val.strip() in self.qr_to_name:
                skill = self.skill_map.get(retry_val.strip())
                if skill and retry_pts is not None:
                    return {
                        "skill_name": skill["skill_name"],
                        "skill_id": skill["skill_id"],
                        "points": np.asarray(retry_pts, dtype=np.float64).reshape(-1, 2),
                    }
        return None

    def run(self) -> None:
        qr_interval = 0.25
        last = 0.0
        while self.running:
            now = time.time()
            if now - last < qr_interval:
                time.sleep(0.02)
                continue
            last = now
            with self.lock:
                frames = list(self.buffer)
                self.buffer.clear()
            if not frames:
                continue
            for frame in reversed(frames):
                result = self._decode(frame)
                if result is not None:
                    self.result = result
                    self.result_time = time.time()
                    break
            time.sleep(0.02)


# ── 单应矩阵定位 ──────────────────────────────────────────

class HomographyLocator:
    """用单应矩阵 H 把 QR 码像素坐标转换为世界坐标"""

    def __init__(self, args):
        self.corner_ids = args.corner_ids
        self.dict_id = dict_id_by_name(args.aruco_dict)
        self.table_w = args.table_width
        self.table_h = args.table_height
        self.H: np.ndarray | None = None
        self._calib_frames = 0

    @property
    def calibrated(self) -> bool:
        return self.H is not None

    def try_calibrate(self, frame) -> bool:
        """检测四角 ArUco 标记，自动校准"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        found = aruco_detect(gray, self.dict_id)

        # 收集可见的角标记
        centers = {}
        for cid in self.corner_ids:
            if cid in found:
                centers[cid] = found[cid].mean(axis=0)

        if len(centers) < 4:
            return False

        # 自动分配四角顺序
        items = [(mid, float(p[0]), float(p[1])) for mid, p in centers.items()]
        cx = sum(x for _, x, _ in items) / len(items)
        cy = sum(y for _, _, y in items) / len(items)
        items.sort(key=lambda it: -math.atan2(it[2] - cy, it[1] - cx))
        start = max(range(len(items)), key=lambda i: (items[i][2] - items[i][1], items[i][2]))
        ordered = items[start:] + items[:start]
        ordered_ids = [mid for mid, _, _ in ordered]

        # 世界坐标：左下(0,0) → 右下(w,0) → 右上(w,h) → 左上(0,h)
        world_pts = [(0.0, 0.0), (self.table_w, 0.0), (self.table_w, self.table_h), (0.0, self.table_h)]
        px_pts = [centers[mid] for mid in ordered_ids]

        src = np.asarray(px_pts, dtype=np.float64).reshape(-1, 1, 2)
        dst = np.asarray(world_pts, dtype=np.float64).reshape(-1, 1, 2)
        H, _ = cv2.findHomography(src, dst, 0)
        if H is not None:
            self.H = H
            return True
        return False

    def reset(self) -> None:
        self.H = None
        self._calib_frames = 0

    def qr_to_world(self, points: np.ndarray) -> tuple[float, float, float]:
        """QR 码 4 角点 → 世界坐标 (x, y, theta)"""
        if self.H is None:
            cx = float(points[:, 0].mean())
            cy = float(points[:, 1].mean())
            return cx, cy, 0.0

        # 4 角点全部变换到世界坐标
        world_corners = []
        for pt in points:
            wx, wy = apply_h(self.H, pt)
            world_corners.append((wx, wy))

        # 中心 = 4 角点世界坐标均值
        cx = sum(p[0] for p in world_corners) / 4.0
        cy = sum(p[1] for p in world_corners) / 4.0

        # 方向角 = 上边缘中点 - 中心（和 moonfall vision.py 一样）
        up_x = (world_corners[0][0] + world_corners[1][0]) / 2.0 - cx
        up_y = (world_corners[0][1] + world_corners[1][1]) / 2.0 - cy
        theta = norm_angle(math.atan2(up_y, up_x))

        return cx, cy, theta

    def px_to_world(self, px) -> tuple[float, float]:
        if self.H is None:
            return 0.0, 0.0
        return apply_h(self.H, px)


# ── 逐帧 QR 追踪器 ────────────────────────────────────────

class QrFrameTracker:
    """每帧用 OTSU 二值化 + detect() 找 QR 码位置，EMA 平滑角点"""

    def __init__(self, ema_alpha: float = 0.4):
        self.detector = cv2.QRCodeDetector()
        self.ema_alpha = ema_alpha
        self.smoothed_points: np.ndarray | None = None
        self.qr_found = False
        self.decode_result: dict | None = None
        self.decode_time = 0.0

    def _to_otsu(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return otsu

    def update(self, frame, decode_result: dict | None = None) -> dict | None:
        if decode_result is not None:
            self.decode_result = decode_result
            self.decode_time = time.time()
            pts = decode_result["points"]
            self.smoothed_points = pts.copy()
            self.qr_found = True
            return self._make_state()

        otsu = self._to_otsu(frame)
        have, points = self.detector.detect(otsu)
        if not have or points is None:
            if self.smoothed_points is not None:
                self.qr_found = False
            return self._make_state()

        pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)

        if self.smoothed_points is not None and self.smoothed_points.shape == pts.shape:
            a = self.ema_alpha
            self.smoothed_points = a * pts + (1 - a) * self.smoothed_points
        else:
            self.smoothed_points = pts.copy()

        self.qr_found = True
        return self._make_state()

    def _make_state(self) -> dict | None:
        if not self.qr_found or self.smoothed_points is None:
            return None
        return {
            "found": self.qr_found,
            "points": self.smoothed_points,
            "skill_name": self.decode_result["skill_name"] if self.decode_result else None,
            "skill_id": self.decode_result["skill_id"] if self.decode_result else None,
        }


# ── 主循环 ────────────────────────────────────────────────

def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    # 加载卡牌 QR 映射
    print("[qr] scanning card QR images...")
    qr_to_name = load_card_qr_map(args.card_dir)
    print(f"[qr] found {len(qr_to_name)} QR codes")
    for qr_text, name in sorted(qr_to_name.items(), key=lambda x: x[1]):
        print(f"    {name}: {qr_text}")

    skill_map = load_skill_map(CONFIG_PATH)
    print(f"[qr] loaded {len(skill_map)} skill definitions")

    # 打开摄像头
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
    print(f"[qr] camera opened (backend={backend_name}, {aw}x{ah})")

    # 自动对焦锁定
    capture.set(cv2.CAP_PROP_AUTOFOCUS, 1)
    time.sleep(3)
    focus = capture.get(cv2.CAP_PROP_FOCUS)
    capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
    capture.set(cv2.CAP_PROP_FOCUS, focus)
    print(f"[qr] focus locked at {focus:.0f}")

    # 初始化模块
    frame_tracker = QrFrameTracker()
    detector_thread = QrDetectThread(qr_to_name, skill_map)
    detector_thread.start()
    locator = HomographyLocator(args)

    # WebSocket 后台线程
    ws_holder: dict = {}
    ws_lock = threading.Lock()
    last_send: dict[str, float] = {}

    def ws_send(message: dict) -> None:
        with ws_lock:
            ws = ws_holder.get("ws")
            loop = ws_holder.get("loop")
            if ws and loop:
                try:
                    asyncio.run_coroutine_threadsafe(
                        ws.send(json.dumps(message, ensure_ascii=False)), loop
                    )
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
                        print(f"[qr] connected to {args.ws_url}")
                        attempts = 0
                        with ws_lock:
                            ws_holder["ws"] = ws
                            ws_holder["loop"] = loop
                        async for raw in ws:
                            msg = json.loads(raw)
                            if msg.get("topic") == "error":
                                print(f"[qr] runtime error: {msg['payload'].get('message')}", file=sys.stderr)
                except Exception as exc:
                    attempts += 1
                    print(f"[qr] ws disconnected ({attempts}/5): {exc}", file=sys.stderr)
                    if attempts < 5:
                        time.sleep(min(0.5 * attempts, 2.0))

        loop.run_until_complete(_run())
        loop.close()

    ws_t = threading.Thread(target=ws_thread, daemon=True)
    ws_t.start()
    time.sleep(1)

    # 持续校准尝试
    calib_check_interval = 2.0
    last_calib_check = 0.0

    fps_t = time.time()
    fps_n = 0
    fps = 0.0

    print("[qr] 'c'=calibrate  'q'=quit  'f'=refocus  'r'=reset calibration")
    print("[qr] place 4 ArUco markers at table corners for calibration")

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

            # 自动尝试校准（每 2 秒试一次）
            if not locator.calibrated and now - last_calib_check > calib_check_interval:
                last_calib_check = now
                if locator.try_calibrate(frame):
                    print("[qr] auto-calibrated! H matrix computed")

            # 喂帧给 QR 检测线程
            detector_thread.update_frame(frame)

            # 获取后台解码结果
            qr_result = detector_thread.get_result()

            # 逐帧追踪（每帧 detect，EMA 平滑）
            track = frame_tracker.update(frame, qr_result)

            if track and track["found"]:
                points = track["points"]
                skill_name = track["skill_name"]
                skill_id = track["skill_id"]

                # 用单应矩阵计算世界坐标
                world_x, world_y, theta = locator.qr_to_world(points)

                # 绘制 QR 码框（逐帧都有，不会闪烁）
                pts_int = points.astype(np.int32)
                cv2.polylines(frame, [pts_int], True, (0, 255, 0), 3)

                # 中心点
                cx_px = int(points[:, 0].mean())
                cy_px = int(points[:, 1].mean())
                cv2.circle(frame, (cx_px, cy_px), 5, (0, 0, 255), -1)

                # 方向指示线
                if len(points) >= 2:
                    up_mid_x = int((points[0][0] + points[1][0]) / 2)
                    up_mid_y = int((points[0][1] + points[1][1]) / 2)
                    cv2.arrowedLine(frame, (cx_px, cy_px), (up_mid_x, up_mid_y), (255, 0, 0), 2)

                # 角点标注
                for i, (px, py) in enumerate(points):
                    cv2.circle(frame, (int(px), int(py)), 3, (0, 255, 255), -1)

                # 标签（已解码显示卡牌名，未解码只显示 QR 检测到）
                if skill_name:
                    if locator.calibrated:
                        label = f"{skill_name} ({world_x:.1f},{world_y:.1f})cm {math.degrees(theta):.0f}deg"
                    else:
                        label = f"{skill_name} (uncalibrated)"
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                    y0 = max(cy_px - th - 12, 0)
                    cv2.rectangle(frame, (cx_px - tw // 2 - 4, y0), (cx_px + tw // 2 + 4, y0 + th + 8), (0, 200, 0), -1)
                    cv2.putText(frame, label, (cx_px - tw // 2, y0 + th + 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
                else:
                    label = "QR detected (identifying...)"
                    cv2.putText(frame, label, (cx_px - 60, cy_px - 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

                # 发送 WebSocket 消息（已解码时才发）
                if skill_id and now - last_send.get(skill_id, 0) > args.cooldown:
                    message = {
                        "topic": "input.qr_skill",
                        "source": "insta360_link_2c",
                        "timestamp": now,
                        "payload": {
                            "qr_text": skill_name,
                            "skill_id": skill_id,
                            "skill_name": skill_name,
                            "position": {
                                "x": round(world_x, 1),
                                "y": round(world_y, 1),
                                "theta": round(theta, 3),
                            } if locator.calibrated else None,
                        },
                    }
                    ws_send(message)
                    last_send[skill_id] = now
                    pos_str = f"({world_x:.1f},{world_y:.1f})cm" if locator.calibrated else "(uncalibrated)"
                    print(f"[qr] detected: {skill_name} ({skill_id}) at {pos_str}")

            # 绘制桌面边界（校准后）
            if locator.calibrated and locator.H is not None:
                # 把桌面四角世界坐标逆变换回像素，画框
                world_corners = np.array([
                    [[0, 0]], [[locator.table_w, 0]],
                    [[locator.table_w, locator.table_h]], [[0, locator.table_h]]
                ], dtype=np.float64)
                H_inv = np.linalg.inv(locator.H)
                px_corners = cv2.perspectiveTransform(world_corners, H_inv).reshape(-1, 2).astype(np.int32)
                cv2.polylines(frame, [px_corners], True, (100, 100, 255), 1)

            # 状态栏
            if locator.calibrated:
                status = f"CALIBRATED | {fps:.0f} FPS"
                color = (0, 255, 0)
            else:
                status = f"UNCALIBRATED (auto-calibrating...) | {fps:.0f} FPS"
                color = (0, 140, 255)
            cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            if args.preview:
                # 左下角 OTSU 小窗（显示检测器实际看到的二值化画面）
                gray_small = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                _, otsu_small = cv2.threshold(gray_small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                otsu_bgr = cv2.cvtColor(otsu_small, cv2.COLOR_GRAY2BGR)
                otsu_bgr = cv2.resize(otsu_bgr, (320, 180))
                # 在 OTSU 小窗上也画检测框
                if track and track["found"]:
                    pts_s = track["points"].astype(np.float64)
                    sx = 320.0 / frame.shape[1]
                    sy = 180.0 / frame.shape[0]
                    pts_scaled = pts_s.copy()
                    pts_scaled[:, 0] *= sx
                    pts_scaled[:, 1] *= sy
                    cv2.polylines(otsu_bgr, [pts_scaled.astype(np.int32)], True, (0, 255, 0), 2)
                fh = frame.shape[0]
                frame[fh - 190:fh - 10, 10:330] = otsu_bgr
                cv2.rectangle(frame, (10, fh - 190), (330, fh - 10), (0, 255, 255), 1)
                cv2.putText(frame, "OTSU channel", (15, fh - 195),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

                cv2.imshow("Moonfall - QR Scanner + Homography", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                elif key == ord("c"):
                    print("[qr] manual calibrating...")
                    if locator.try_calibrate(frame):
                        print("[qr] calibrated!")
                    else:
                        print("[qr] calibration failed: need 4 ArUco corner markers visible")
                elif key == ord("r"):
                    locator.reset()
                    print("[qr] calibration reset")
                elif key == ord("f"):
                    capture.set(cv2.CAP_PROP_AUTOFOCUS, 1)
                    print("[qr] refocusing...")
                    time.sleep(2.5)
                    focus = capture.get(cv2.CAP_PROP_FOCUS)
                    capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
                    capture.set(cv2.CAP_PROP_FOCUS, focus)
                    print(f"[qr] focus={focus:.0f}")
    finally:
        detector_thread.running = False
        detector_thread.join(timeout=1)
        capture.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
