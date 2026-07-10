from typing import Any

from app.models.world import WorldState


class RuleEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        rules = (config or {}).get("rules", {})
        self.fuel_win = float(rules.get("fuel_win", 100))
        self.boss_at = float(rules.get("boss_at", 70))
        self.moon_rage_threshold = float(rules.get("moon_rage_threshold", 0.7))

    def evaluate(self, state: WorldState) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []

        if state.fuel >= self.boss_at and not state.boss_mode:
            state.boss_mode = True
            events.append({"type": "enter_boss", "message": "燃料达到 70%，进入 Boss 战"})

        if state.fuel >= self.fuel_win and state.phase != "ended":
            state.phase = "ended"
            state.winner = "players"
            events.append({"type": "win", "message": "燃料收集完成，玩家胜利"})

        if state.core_hp <= 0 and state.phase != "ended":
            state.phase = "ended"
            state.winner = "moon"
            events.append({"type": "lose", "message": "方舟核心被摧毁，任务失败"})

        if state.moon_rage >= self.moon_rage_threshold:
            events.append({"type": "dust_storm", "message": "月怒过高，中央月尘风暴增强"})

        return events
