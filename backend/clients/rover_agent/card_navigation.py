"""Card intent to physical-destination selection for rover navigation."""
from __future__ import annotations

from dataclasses import dataclass
import threading
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


class CardNavigationController:
    """Turn newly presented supported cards into safe rover goals."""

    def __init__(self, fleet, rover_id: str = "r0", speed: int = 3) -> None:
        self.fleet = fleet
        self.rover_id = rover_id
        self.speed = speed
        self.gate = CardPresentationGate()

    def observe(self, values: Iterable[str]) -> Destination | None:
        """Command the first newly presented supported card, when safe to do so."""

        if not self.fleet.field.calibrated:
            return None
        position = self.fleet.get_position(self.rover_id)
        if not position.get("fresh"):
            return None
        for card_value in self.gate.observe(values):
            destination = select_destination(
                card_value, float(position["x"]), float(position["y"]),
            )
            if destination is None:
                continue
            self.fleet.rover(self.rover_id).set_goal(
                (destination.x_cm, destination.y_cm), speed=self.speed,
            )
            return destination
        return None


def _decode_qr_values(detector, frame) -> set[str]:
    """Decode QR payloads from a frame, accepting OpenCV single or multi output."""

    try:
        detected, values, _, _ = detector.detectAndDecodeMulti(frame)
        if detected:
            return {value.strip() for value in values if value and value.strip()}
    except Exception:
        pass
    try:
        value, _, _ = detector.detectAndDecode(frame)
        return {value.strip()} if value and value.strip() else set()
    except Exception:
        return set()


def start_card_navigation_thread(fleet, stop_event, rate_hz: float = 2.0):
    """Scan the Fleet-owned camera feed without opening a second camera handle."""

    def run() -> None:
        import cv2

        controller = CardNavigationController(fleet)
        detector = cv2.QRCodeDetector()
        period = 1.0 / rate_hz
        while not stop_event.is_set():
            frame, _ = fleet.field.visual_snapshot()
            if frame is not None:
                chosen = controller.observe(_decode_qr_values(detector, frame.copy()))
                if chosen is not None:
                    print(f"[card] r0 -> {chosen.id} ({chosen.x_cm:.2f}, {chosen.y_cm:.2f})")
            stop_event.wait(period)

    thread = threading.Thread(target=run, name="card-navigation", daemon=True)
    thread.start()
    return thread
