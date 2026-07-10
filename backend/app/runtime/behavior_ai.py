from uuid import uuid4

from app.models.commands import RobotCommand
from app.models.world import RobotState, WorldState


class BehaviorAI:
    def choose_action(self, robot: RobotState, state: WorldState) -> RobotCommand:
        if robot.hp < 30:
            return RobotCommand(
                command_id=str(uuid4()),
                robot_id=robot.robot_id,
                action="return_base",
                target_zone="base",
                priority=2.0,
            )

        if state.moon_rage > 0.7:
            return RobotCommand(
                command_id=str(uuid4()),
                robot_id=robot.robot_id,
                action="avoid_and_move",
                target_zone="resource_ne",
                priority=1.5,
                avoid=["dust_center"],
            )

        return RobotCommand(
            command_id=str(uuid4()),
            robot_id=robot.robot_id,
            action="move_to",
            target_zone="resource_ne",
        )
