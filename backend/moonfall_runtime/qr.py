from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


SUPPORTED_CARD_TYPES = {"explore_relic", "energy_priority"}

CARD_ALIASES = {
    "explore_relic": {
        "探索遗迹",
        "探索遺跡",
        "遗迹探索",
        "遺跡探索",
        "explore_relic",
        "explore relic",
        "relic",
        "ruins",
    },
    "energy_priority": {
        "采集优先",
        "采集優先",
        "能量优先",
        "能量優先",
        "能源优先",
        "能源優先",
        "燃料优先",
        "燃料優先",
        "energy_priority",
        "energy priority",
        "fuel_priority",
        "fuel priority",
    },
}


@dataclass(frozen=True)
class QrCardResult:
    raw: str
    supported: bool
    card_type: str | None = None
    player_id: str | None = None
    reason: str | None = None


def recognize_qr_text(raw: str, default_player_id: str | None = None) -> QrCardResult:
    """Convert raw QR payload text into a supported card command, or ignore it."""
    text = (raw or "").strip()
    if not text:
        return QrCardResult(raw=raw, supported=False, player_id=default_player_id, reason="empty")

    payload = _extract_payload(text)
    player_id = _first_present(payload, ("player_id", "player", "pid")) or default_player_id
    card_text = _first_present(payload, ("card_type", "card", "action", "text", "result", "type")) or text
    card_type = _normalize_card_type(card_text)
    if card_type is None:
        return QrCardResult(raw=raw, supported=False, player_id=player_id, reason="unsupported")
    return QrCardResult(raw=raw, supported=True, card_type=card_type, player_id=player_id)


def recognize_many_texts(raw_values: list[str], default_player_id: str | None = None) -> list[QrCardResult]:
    return [recognize_qr_text(value, default_player_id=default_player_id) for value in raw_values]


def decode_qr_image(path: str | Path) -> list[str]:
    """Decode QR payload strings from an image file using OpenCV when available."""
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError("QR image decoding requires opencv-python") from exc

    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"cannot read image: {path}")

    detector = cv2.QRCodeDetector()
    found, decoded, _points, _straight = detector.detectAndDecodeMulti(image)
    if found:
        return [item for item in decoded if item]

    decoded_one, _points, _straight = detector.detectAndDecode(image)
    return [decoded_one] if decoded_one else []


def recognize_qr_image(path: str | Path, default_player_id: str | None = None) -> list[QrCardResult]:
    return recognize_many_texts(decode_qr_image(path), default_player_id=default_player_id)


class QrDebouncer:
    """Ignore repeated supported QR results within a short time window."""

    def __init__(self, window_seconds: float = 2.0, clock=time.monotonic) -> None:
        self.window_seconds = float(window_seconds)
        self.clock = clock
        self._last_seen: dict[tuple[str | None, str | None, str], float] = {}

    def accept(self, result: QrCardResult) -> bool:
        if not result.supported:
            return False
        now = float(self.clock())
        key = (result.player_id, result.card_type, result.raw)
        last = self._last_seen.get(key)
        if last is not None and now - last < self.window_seconds:
            return False
        self._last_seen[key] = now
        return True

    def accept_log(self, result: QrCardResult) -> bool:
        now = float(self.clock())
        key = (result.player_id, result.card_type, result.raw)
        last = self._last_seen.get(key)
        if last is not None and now - last < self.window_seconds:
            return False
        self._last_seen[key] = now
        return True


def _extract_payload(text: str) -> dict[str, Any]:
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    parsed_url = urlparse(text)
    if parsed_url.query:
        query = parse_qs(parsed_url.query)
        return {key: values[0] for key, values in query.items() if values}
    return {}


def _first_present(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _normalize_card_type(value: str) -> str | None:
    text = " ".join(str(value).strip().lower().replace("-", "_").split())
    compact = text.replace(" ", "_")
    for card_type, aliases in CARD_ALIASES.items():
        normalized_aliases = {alias.lower().replace("-", "_") for alias in aliases}
        if text in normalized_aliases or compact in normalized_aliases:
            return card_type
    return None
