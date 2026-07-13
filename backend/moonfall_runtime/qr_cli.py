from __future__ import annotations

import argparse
import json

from moonfall_runtime.qr import QrDebouncer, recognize_qr_image, recognize_qr_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Recognize Moonfall QR card payloads.")
    parser.add_argument("--text", action="append", default=[], help="Raw QR payload text. Can be passed more than once.")
    parser.add_argument("--image", action="append", default=[], help="Image path containing one or more QR codes.")
    parser.add_argument("--player-id", default=None)
    parser.add_argument("--dedupe-window", type=float, default=2.0)
    args = parser.parse_args()

    debouncer = QrDebouncer(args.dedupe_window)
    results = []
    for raw in args.text:
        result = recognize_qr_text(raw, default_player_id=args.player_id)
        results.append({**result.__dict__, "accepted": debouncer.accept(result)})
    for image in args.image:
        for result in recognize_qr_image(image, default_player_id=args.player_id):
            results.append({**result.__dict__, "accepted": debouncer.accept(result)})

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

