from __future__ import annotations

from dataclasses import dataclass

from moonfall_runtime.state import GameState, Landmark


@dataclass(frozen=True)
class TargetDecision:
    player_id: str
    card_type: str
    unit_id: str
    landmark: Landmark


def choose_target(state: GameState, player_id: str, card_type: str) -> TargetDecision | None:
    unit_id = state.player_to_unit.get(player_id)
    if unit_id is None:
        return None
    unit = state.units.get(unit_id)
    if unit is None:
        return None

    if card_type == "explore_relic":
        candidates = [
            landmark
            for landmark in state.landmarks.values()
            if landmark.type == "ruins" and landmark.has_stock_for(card_type)
        ]
    elif card_type == "energy_priority":
        candidates = [
            landmark
            for landmark in state.landmarks.values()
            if landmark.type in {"energy_station", "high_energy_station"} and landmark.has_stock_for(card_type)
        ]
    else:
        return None

    if not candidates:
        return None
    if len(candidates) > 1 and state.last_landmark_id is not None:
        candidates = [landmark for landmark in candidates if landmark.id != state.last_landmark_id] or candidates
    target = min(candidates, key=lambda landmark: landmark.distance_to(unit.pose))
    unit.target = target
    unit.status = "moving"
    unit.settled_target_id = None
    return TargetDecision(player_id=player_id, card_type=card_type, unit_id=unit_id, landmark=target)
