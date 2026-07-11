from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.constants import CONFIG_PATH  # noqa: E402
from app.services.qr_skill_scanner import (  # noqa: E402
    QrDecoder,
    QrPresentationGate,
    SkillDefinition,
    load_skill_allowlist,
)


@dataclass(frozen=True)
class ValidationResult:
    filename: str
    qr_text: str
    skill_id: str


def build_qr_skill_message(skill: SkillDefinition, timestamp: float) -> dict[str, object]:
    return {
        "topic": "input.qr_skill",
        "source": "insta360_link_2c",
        "timestamp": timestamp,
        "payload": {
            "qr_text": skill.skill_name,
            "skill_id": skill.skill_id,
            "skill_name": skill.skill_name,
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Insta360 Link 2C QR skill scanner")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--ws-url", default="ws://127.0.0.1:8000/ws")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--missing-frame-threshold", type=int, default=5)
    parser.add_argument("--max-read-failures", type=int, default=10)
    parser.add_argument("--reconnect-attempts", type=int, default=5)
    parser.add_argument("--validate-images", type=Path)
    return parser.parse_args(argv)


def validate_image_directory(image_dir: Path) -> list[ValidationResult]:
    import cv2
    import numpy as np

    image_dir = Path(image_dir)
    if not image_dir.is_dir():
        raise ValueError(f"image directory does not exist: {image_dir}")
    decoder = QrDecoder()
    skills = load_skill_allowlist(CONFIG_PATH)
    paths = sorted(
        image_dir.glob("*.png"),
        key=lambda path: (not path.stem.isdigit(), int(path.stem) if path.stem.isdigit() else path.stem),
    )
    if not paths:
        raise ValueError(f"no PNG images found in: {image_dir}")

    results: list[ValidationResult] = []
    for path in paths:
        frame = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f"cannot read image: {path}")
        values = decoder.decode(frame)
        if len(values) != 1:
            raise ValueError(f"expected one QR code in {path.name}, decoded: {sorted(values)}")
        qr_text = next(iter(values))
        skill = skills.get(qr_text)
        if skill is None:
            raise ValueError(f"unknown QR card in {path.name}: {qr_text}")
        results.append(ValidationResult(path.name, qr_text, skill.skill_id))
    return results


def configure_capture(capture: object, width: int, height: int, fps: int) -> None:
    import cv2

    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    capture.set(cv2.CAP_PROP_FPS, fps)
    capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)


def process_frame(
    frame: object,
    decoder: object,
    gate: QrPresentationGate,
    skills: dict[str, SkillDefinition],
    timestamp: float,
) -> list[dict[str, object]]:
    decoded_values = decoder.decode(frame)
    known_values = {value for value in decoded_values if value in skills}
    newly_presented = gate.observe(known_values)
    return [build_qr_skill_message(skills[value], timestamp) for value in newly_presented]


async def run_camera(args: argparse.Namespace) -> None:
    import cv2
    import websockets
    from websockets.exceptions import ConnectionClosed

    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    capture = cv2.VideoCapture(args.camera_index, backend)
    configure_capture(capture, args.width, args.height, args.fps)
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(
            f"cannot open camera index {args.camera_index}; select the physical Insta360 Link 2C stream"
        )

    decoder = QrDecoder()
    gate = QrPresentationGate(args.missing_frame_threshold)
    skills = load_skill_allowlist(CONFIG_PATH)
    read_failures = 0
    reconnect_failures = 0
    last_label = "waiting for QR card"

    try:
        while reconnect_failures < args.reconnect_attempts:
            try:
                async with websockets.connect(args.ws_url) as websocket:
                    print(f"[qr] connected to {args.ws_url}")
                    reconnect_failures = 0
                    receiver = asyncio.create_task(_drain_runtime_messages(websocket))
                    try:
                        while True:
                            ok, frame = capture.read()
                            if not ok or frame is None:
                                read_failures += 1
                                if read_failures >= args.max_read_failures:
                                    raise RuntimeError(
                                        f"camera read failed {read_failures} consecutive times"
                                    )
                                await asyncio.sleep(0.05)
                                continue

                            read_failures = 0
                            messages = process_frame(frame, decoder, gate, skills, time.time())
                            for message in messages:
                                await websocket.send(json.dumps(message, ensure_ascii=False))
                                payload = message["payload"]
                                last_label = f"{payload['skill_name']} ({payload['skill_id']})"
                                print(f"[qr] recognized {last_label}")

                            if args.preview:
                                cv2.putText(
                                    frame,
                                    last_label,
                                    (24, 48),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    1.0,
                                    (0, 255, 0),
                                    2,
                                    cv2.LINE_AA,
                                )
                                cv2.imshow("Moonfall - Insta360 Link 2C QR Scanner", frame)
                                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                                    return
                            await asyncio.sleep(0)
                    finally:
                        receiver.cancel()
                        await asyncio.gather(receiver, return_exceptions=True)
            except (ConnectionClosed, OSError) as exc:
                reconnect_failures += 1
                print(
                    f"[qr] runtime connection failed "
                    f"({reconnect_failures}/{args.reconnect_attempts}): {exc}",
                    file=sys.stderr,
                )
                if reconnect_failures < args.reconnect_attempts:
                    await asyncio.sleep(min(0.5 * reconnect_failures, 2.0))

        raise RuntimeError(
            f"cannot connect to Runtime after {args.reconnect_attempts} attempts: {args.ws_url}"
        )
    finally:
        capture.release()
        if args.preview:
            cv2.destroyAllWindows()


async def _drain_runtime_messages(websocket: object) -> None:
    async for raw in websocket:
        message = json.loads(raw)
        if message.get("topic") == "error":
            print(f"[qr] runtime error: {json.dumps(message, ensure_ascii=False)}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.validate_images is not None:
            results = validate_image_directory(args.validate_images)
            for result in results:
                print(f"{result.filename}\t{result.qr_text}\t{result.skill_id}")
            print(f"[qr] validated {len(results)}/{len(results)} card images")
            return 0
        asyncio.run(run_camera(args))
        return 0
    except KeyboardInterrupt:
        print("[qr] stopped")
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"[qr] error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
