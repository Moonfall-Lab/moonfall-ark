from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml


@dataclass(frozen=True)
class SkillDefinition:
    skill_id: str
    skill_name: str


def load_skill_allowlist(config_path: Path) -> dict[str, SkillDefinition]:
    with Path(config_path).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    inputs = config.get("inputs", {})
    result: dict[str, SkillDefinition] = {}
    for section in ("cards", "relic_cards"):
        entries = inputs.get(section, [])
        if not isinstance(entries, list):
            raise ValueError(f"inputs.{section} must be a list")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"inputs.{section} entries must be objects")
            skill_id = str(entry.get("id", "")).strip()
            skill_name = str(entry.get("name", "")).strip()
            if not skill_id or not skill_name:
                raise ValueError(f"inputs.{section} entries require id and name")
            if skill_name in result:
                raise ValueError(f"duplicate card name: {skill_name}")
            result[skill_name] = SkillDefinition(skill_id=skill_id, skill_name=skill_name)
    return result


class QrPresentationGate:
    def __init__(self, missing_frame_threshold: int = 5):
        if missing_frame_threshold < 1:
            raise ValueError("missing_frame_threshold must be at least 1")
        self.missing_frame_threshold = missing_frame_threshold
        self._active: set[str] = set()
        self._missing: dict[str, int] = {}

    def observe(self, visible_values: set[str]) -> list[str]:
        emitted = sorted(visible_values - self._active)
        for value in visible_values:
            self._active.add(value)
            self._missing[value] = 0
        for value in list(self._active - visible_values):
            misses = self._missing.get(value, 0) + 1
            if misses >= self.missing_frame_threshold:
                self._active.remove(value)
                self._missing.pop(value, None)
            else:
                self._missing[value] = misses
        return emitted


class DecoderBackend(Protocol):
    def decode(self, frame: Any) -> set[str]: ...


class OpenCvQrBackend:
    def __init__(self):
        import cv2

        self.cv2 = cv2
        self.detector = cv2.QRCodeDetector()

    def decode(self, frame: Any) -> set[str]:
        values: set[str] = set()
        detected, decoded_info, points, _ = self.detector.detectAndDecodeMulti(frame)
        if detected:
            values.update(value.strip() for value in decoded_info if value.strip())
        if values:
            return values

        value, single_points, _ = self.detector.detectAndDecode(frame)
        if value.strip():
            return {value.strip()}

        retry_points = single_points if single_points is not None else points
        if retry_points is None:
            return set()
        retry_image = self._build_retry_image(frame, retry_points)
        retry_value, _, _ = self.detector.detectAndDecode(retry_image)
        return {retry_value.strip()} if retry_value.strip() else set()

    def _build_retry_image(self, frame: Any, points: Any) -> Any:
        import numpy as np

        flattened = np.asarray(points).reshape(-1, 2)
        x_min, y_min = np.floor(flattened.min(axis=0)).astype(int)
        x_max, y_max = np.ceil(flattened.max(axis=0)).astype(int)
        width = max(1, x_max - x_min)
        height = max(1, y_max - y_min)
        pad_x = max(12, int(width * 0.2))
        pad_y = max(12, int(height * 0.2))
        frame_height, frame_width = frame.shape[:2]
        x_min = max(0, x_min - pad_x)
        y_min = max(0, y_min - pad_y)
        x_max = min(frame_width, x_max + pad_x)
        y_max = min(frame_height, y_max + pad_y)
        crop = frame[y_min:y_max, x_min:x_max]
        bordered = self.cv2.copyMakeBorder(
            crop,
            32,
            32,
            32,
            32,
            self.cv2.BORDER_CONSTANT,
            value=255,
        )
        return self.cv2.resize(
            bordered,
            None,
            fx=3,
            fy=3,
            interpolation=self.cv2.INTER_NEAREST,
        )


class ZxingQrBackend:
    def decode(self, frame: Any) -> set[str]:
        import zxingcpp

        barcodes = zxingcpp.read_barcodes(
            frame,
            formats=zxingcpp.BarcodeFormat.QRCode,
        )
        return {barcode.text.strip() for barcode in barcodes if barcode.text.strip()}


class QrDecoder:
    def __init__(
        self,
        primary: DecoderBackend | None = None,
        fallback: DecoderBackend | None = None,
    ):
        self.primary = primary if primary is not None else OpenCvQrBackend()
        self.fallback = fallback if fallback is not None else ZxingQrBackend()

    def decode(self, frame: Any) -> set[str]:
        values = self.primary.decode(frame)
        if values:
            return values
        return self.fallback.decode(frame)
