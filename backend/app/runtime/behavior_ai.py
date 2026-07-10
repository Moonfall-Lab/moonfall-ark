from __future__ import annotations

from uuid import uuid4

from app.models.commands import RobotCommand
from app.models.world import UnitState, WorldState


class BehaviorAI:
    def choose_action(self, unit: UnitState, state: WorldState) -> RobotCommand:
        if state.global_.moon_rage >= 80:
            return RobotCommand(
                command_id=str(uuid4()),
                robot_id=unit.id,
                action="avoid_and_move",
                target_zone="central_hi",
                priority=1.5,
                avoid=["dust_area"],
            )

        return RobotCommand(
            command_id=str(uuid4()),
            robot_id=unit.id,
            action="collect",
            target_zone="central_hi",
        )
