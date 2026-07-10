from typing import Any
from uuid import uuid4

from app.models.commands import ArmCommand
from app.models.world import WorldState


class MoonDirector:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        arm_config = (config or {}).get("arm", {})
        self.safe_mode = bool(arm_config.get("safe_mode", True))

    def choose_arm_event(self, state: WorldState) -> ArmCommand | None:
        if state.moon_rage < 0.5:
            return None

        if state.boss_mode:
            action = "strike" if state.moon_rage >= 0.7 else "hover_warning"
            target_zone = "base"
        else:
            action = "drop_dust"
            target_zone = "dust_center"

        return ArmCommand(
            command_id=str(uuid4()),
            action=action,
            target_zone=target_zone,
            intensity=max(0.5, state.moon_rage),
            safe_mode=self.safe_mode,
        )
