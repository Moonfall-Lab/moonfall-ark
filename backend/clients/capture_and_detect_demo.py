"""截取一张摄像头图片，跑静态 QR 检测 DEMO 并可视化"""
import cv2
import numpy as np
import json
from pathlib import Path
from datetime import datetime

OUT_DIR = Path(__file__).resolve().parent
PHOTO_PATH = OUT_DIR / "capture_camera.png"
RESULT_PATH = OUT_DIR / "detect_result.png"
INFO_PATH = OUT_DIR / "detect_info.json"


def main():
    # ── 1. 截图 ──────────────────────────────
    print("[1/4] opening camera...")
    cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
    if not cap.isOpened():
        print("[ERROR] cannot open camera")
        return

    # 等 2 秒让摄像头稳定
    import time
    time.sleep(2)

    # 读几帧丢掉（暖机）
    for _ in range(10):
        cap.read()

    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        print("[ERROR] failed to capture frame")
        return

    h, w = frame.shape[:2]
    print(f"    captured: {w}x{h}")
    cv2.imencode(".png", frame)[1].tofile(str(POTO_PATH := PHOTO_PATH))
    print(f"    saved: {PHOTO_PATH}")

    # ── 2. QR 码检测（只找位置，不解码）──────────────
    print("\n[2/4] detecting QR codes...")
    detector = cv2.QRCodeDetector()

    # 方法 A: detect (轻量，只找 QR 码的位置和 4 角点)
    have_qr, points = detector.detect(frame)
    print(f"    detect() found: {have_qr}")

    # 方法 B: detectAndDecode (重，但同时给出内容)
    decoded, decoded_points, straight_qr = detector.detectAndDecode(frame)
    print(f"    detectAndDecode() text: {repr(decoded)}")

    # 方法 C: detectAndDecodeMulti (检测多个 QR 码)
    multi_ok, multi_texts, multi_points, multi_straights = detector.detectAndDecodeMulti(frame)
    if multi_ok:
        texts = [t for t in multi_texts if t]
        print(f"    detectAndDecodeMulti() found {len(texts)} QR codes: {texts}")

    # ── 3. 可视化 ─────────────────────────────
    print("\n[3/4] drawing results...")
    vis = frame.copy()

    # 用 detect() 的结果画框（逐帧可用的轻量检测）
    if have_qr and points is not None:
        pts = np.asarray(points, dtype=np.int32).reshape(-1, 2)
        cv2.polylines(vis, [pts], True, (0, 255, 0), 3)

        cx = int(pts[:, 0].mean())
        cy = int(pts[:, 1].mean())
        cv2.circle(vis, (cx, cy), 6, (0, 0, 255), -1)

        # 方向箭头：上边缘中点 → 中心
        up_mid = ((pts[0][0] + pts[1][0]) // 2, (pts[0][1] + pts[1][1]) // 2)
        cv2.arrowedLine(vis, (cx, cy), up_mid, (255, 0, 0), 2)

        # 角点标注
        for i, (px, py) in enumerate(pts):
            cv2.circle(vis, (int(px), int(py)), 4, (0, 255, 255), -1)
            cv2.putText(vis, f"p{i}", (int(px) + 5, int(py) - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        # 外接矩形框（bounding box）
        x, y, ww, hh = cv2.boundingRect(pts)
        cv2.rectangle(vis, (x, y), (x + ww, y + hh), (100, 100, 255), 1)

    # 解码文字标签
    label_parts = []
    if decoded:
        label_parts.append(f"text={decoded}")
    if multi_ok and multi_texts:
        for t in multi_texts:
            if t:
                label_parts.append(f"text={t}")

    if label_parts:
        label = " | ".join(label_parts)
    elif have_qr:
        label = "QR detected (decode failed)"
    else:
        label = "No QR code found"

    # 标签背景
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    cv2.rectangle(vis, (10, h - th - 20), (10 + tw + 16, h - 10), (0, 0, 0), -1)
    cv2.putText(vis, label, (18, h - 15 + th // 2 - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    # 顶部状态
    status = f"DETECT: {'OK' if have_qr else 'NONE'} | DECODE: {'OK' if decoded else 'FAIL'}"
    color = (0, 255, 0) if have_qr else (0, 0, 255)
    cv2.putText(vis, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    # straight_qr（QR 码矫正后的正面图）
    if straight_qr is not None and straight_qr.size > 0:
        sqr = cv2.resize(straight_qr, (200, 200))
        vis[10:210, w - 210:w - 10] = sqr
        cv2.rectangle(vis, (w - 210, 10), (w - 10, 210), (0, 255, 255), 1)
        cv2.putText(vis, "straight_qr", (w - 210, 225),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    cv2.imencode(".png", vis)[1].tofile(str(RESULT_PATH))
    print(f"    saved: {RESULT_PATH}")

    # ── 4. 信息汇总 ───────────────────────────
    print("\n[4/4] summary:")
    info = {
        "image_size": {"width": w, "height": h},
        "detect_found": bool(have_qr),
        "decode_text": decoded if decoded else None,
        "multi_detect_ok": bool(multi_ok),
        "multi_texts": [t for t in (multi_texts or []) if t],
        "qr_points": np.asarray(points).tolist() if (have_qr and points is not None) else None,
        "has_straight_qr": straight_qr is not None and straight_qr.size > 0,
    }
    with open(INFO_PATH, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)

    print(f"    detect_found: {info['detect_found']}")
    print(f"    decode_text:  {info['decode_text']}")
    print(f"    multi_texts:  {info['multi_texts']}")
    print(f"    has_straight: {info['has_straight_qr']}")
    print(f"    saved: {INFO_PATH}")
    print("\nDONE. Check:")
    print(f"  photo:  {PHOTO_PATH}")
    print(f"  result: {RESULT_PATH}")
    print(f"  info:   {INFO_PATH}")


if __name__ == "__main__":
    main()
