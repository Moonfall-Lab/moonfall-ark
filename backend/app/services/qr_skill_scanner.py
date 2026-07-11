from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
