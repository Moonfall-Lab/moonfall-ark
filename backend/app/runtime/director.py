from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.models.commands import ArmCommand
from app.models.world import WorldState


class MoonDirector:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        arm_config = (config or {}).get("arm", {})
        self.safe_mode = bool(arm_config.get("safe_mode", True))

    def choose_arm_event(self, state: WorldState) -> ArmCommand | None:
        moon_rage = state.global_.moon_rage
        if moon_rage < 50:
            return None

        action = "strike" if moon_rage >= 80 else "drop_dust"
        return ArmCommand(
            command_id=str(uuid4()),
            action=action,
            target_zone="dust_area",
            intensity=max(0.5, min(1.0, moon_rage / 100)),
            safe_mode=self.safe_mode,
        )
