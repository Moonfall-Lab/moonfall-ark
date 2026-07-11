"""Card intent to physical-destination selection for rover navigation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Destination:
    """A named center point in the rover field coordinate system."""

    id: str
    x_cm: float
    y_cm: float


_RUINS = (
    Destination("obstacle-2", 61.51, 51.09),
    Destination("obstacle-4", 12.71, 10.16),
)
_RESOURCES = (
    Destination("obstacle-1", 19.22, 52.58),
    Destination("obstacle-3", 37.37, 29.88),
    Destination("obstacle-5", 61.83, 13.90),
)
_CARD_DESTINATIONS = {
    "探索遗迹": _RUINS,
    "explore_relic": _RUINS,
    "采集优先": _RESOURCES,
    "collect_priority": _RESOURCES,
}


def select_destination(
    card_value: str, x_cm: float, y_cm: float,
) -> Destination | None:
    """Return the nearest compatible destination, or ``None`` for no route."""

    candidates = _CARD_DESTINATIONS.get(card_value)
    if candidates is None:
        return None
    nearest = candidates[0]
    nearest_distance = (nearest.x_cm - x_cm) ** 2 + (nearest.y_cm - y_cm) ** 2
    for candidate in candidates[1:]:
        distance = ((candidate.x_cm - x_cm) ** 2
                    + (candidate.y_cm - y_cm) ** 2)
        if distance < nearest_distance - 1e-9:
            nearest = candidate
            nearest_distance = distance
    return nearest


class CardPresentationGate:
    """Emit a visible card once until it has been absent enough times."""

    def __init__(self, missing_observations: int = 5) -> None:
        if missing_observations < 1:
            raise ValueError("missing_observations must be at least one")
        self.missing_observations = missing_observations
        self._active: set[str] = set()
        self._missing: dict[str, int] = {}

    def observe(self, values: Iterable[str]) -> list[str]:
        """Return card values that have newly appeared in this observation."""

        visible = set(values)
        emitted = sorted(visible - self._active)
        for value in visible:
            self._active.add(value)
            self._missing.pop(value, None)
        for value in tuple(self._active - visible):
            misses = self._missing.get(value, 0) + 1
            if misses >= self.missing_observations:
                self._active.remove(value)
                self._missing.pop(value, None)
            else:
                self._missing[value] = misses
        return emitted
