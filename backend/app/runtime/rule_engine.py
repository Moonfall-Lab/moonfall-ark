from __future__ import annotations

from typing import Any

from app.models.world import WorldState


class RuleEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        rules = (config or {}).get("rules", {})
        self.max_turn = int(rules.get("max_turn", 20))

    def evaluate(self, state: WorldState) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []

        if state.global_.moon_rage >= 50:
            events.append({"type": "dust_storm", "message": "月尘风暴增强"})

        if state.turn >= self.max_turn and state.phase != "ended":
            state.phase = "ended"
            state.winner = state.rank_order[0] if state.rank_order else None
            events.append({"type": "rank_locked", "message": "回合结束，锁定当前排名"})

        return events
