from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from app.core.constants import TOPIC_CMD_ARM, TOPIC_STATE_EVENT, TOPIC_STATE_WORLD
from app.models.messages import RuntimeMessage, make_message
from app.runtime.director import MoonDirector
from app.runtime.rule_engine import RuleEngine
from app.runtime.world_state import WorldStateManager
from app.services.event_logger import log_event


BroadcastFunc = Callable[[RuntimeMessage], Awaitable[None]]


class GameLoop:
    def __init__(
        self,
        state_manager: WorldStateManager,
        rule_engine: RuleEngine,
        director: MoonDirector,
        broadcast: BroadcastFunc,
    ) -> None:
        self.state_manager = state_manager
        self.rule_engine = rule_engine
        self.director = director
        self.broadcast = broadcast
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name="moonfall-game-loop")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        tick = 0
        while self._running:
            state = self.state_manager.get_state()
            await self.broadcast(make_message(TOPIC_STATE_WORLD, self.state_manager.get_state_dict()))

            if tick % 2 == 0:
                await self._evaluate_rules_and_director()

            tick += 1
            await asyncio.sleep(1)

    async def _evaluate_rules_and_director(self) -> None:
        state = self.state_manager.get_state()
        for event in self.rule_engine.evaluate(state):
            payload = {"event_type": event["type"], "message": event["message"]}
            log_event(state.session_id, TOPIC_STATE_EVENT, "runtime", payload)
            await self.broadcast(make_message(TOPIC_STATE_EVENT, payload))

        arm_command = self.director.choose_arm_event(state)
        if arm_command is not None:
            payload = arm_command.model_dump(mode="json")
            log_event(state.session_id, TOPIC_CMD_ARM, "runtime", payload)
            await self.broadcast(make_message(TOPIC_CMD_ARM, payload))
