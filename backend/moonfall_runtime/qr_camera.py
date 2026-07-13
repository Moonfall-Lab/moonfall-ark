from __future__ import annotations

import argparse
import json
import time

from moonfall_runtime.qr import QrDebouncer, recognize_qr_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Open a camera window and scan Moonfall QR cards.")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--player-id", default="p1")
    parser.add_argument("--dedupe-window", type=float, default=2.0)
    args = parser.parse_args()

    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise SystemExit("opencv-python is required. Run: .venv/bin/python -m pip install opencv-python") from exc

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit(f"cannot open camera {args.camera}")

    detector = cv2.QRCodeDetector()
    debouncer = QrDebouncer(args.dedupe_window)
    window = "Moonfall QR Scanner - press q to quit"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    print(f"[qr] camera={args.camera}, default_player_id={args.player_id}")
    print("[qr] show a QR code to the camera; press q in the window to quit")

    last_label = "waiting for QR..."
    last_label_time = 0.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("[qr] failed to read frame")
                time.sleep(0.1)
                continue

            decoded_values, points = _decode_frame(detector, frame)
            for raw in decoded_values:
                result = recognize_qr_text(raw, default_player_id=args.player_id)
                accepted = debouncer.accept(result)
                payload = {**result.__dict__, "accepted": accepted}
                if accepted or (not result.supported and debouncer.accept_log(result)):
                    print("[qr]", json.dumps(payload, ensure_ascii=False))
                status = "accepted" if accepted else "ignored"
                card = result.card_type or result.reason or "unknown"
                last_label = f"{status}: {card} | raw={raw[:40]}"
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
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


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


if __name__ == "__main__":
    main()
