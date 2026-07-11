# Card Destination Navigation Design

## Purpose

Enable an Insta360 camera to recognize selected Moonfall cards and direct rover `r0` to the nearest compatible physical destination.  A card expresses an intent, not the card's physical position.

## Scope

Supported cards:

| Card | Intent | Candidate destinations |
| --- | --- | --- |
| `探索遗迹` / `explore_relic` | Explore ruins | `obstacle-2`, `obstacle-4` |
| `采集优先` / `collect_priority` | Collect resources | `obstacle-1`, `obstacle-3`, `obstacle-5` |

`返航结算` is recognized but does not command movement in this increment because a physical ship coordinate is not yet defined. All other cards are ignored by navigation.

The five physical destinations use the existing 80 cm x 60 cm rover coordinate system. They are destinations, not navigation obstacles:

| ID | Type | Center (cm) |
| --- | --- | --- |
| `obstacle-1` | energy station | `(19.22, 52.58)` |
| `obstacle-2` | ruins | `(61.51, 51.09)` |
| `obstacle-3` | high-energy station | `(37.37, 29.88)` |
| `obstacle-4` | ruins | `(12.71, 10.16)` |
| `obstacle-5` | energy station | `(61.83, 13.90)` |

## Architecture

`rover_agent` remains the sole owner of the Insta360 video device. A new card-destination scanner consumes copies of frames exposed by `FieldTracker.visual_snapshot()`; it never opens the camera itself. This guarantees that the rover pose and card center are interpreted in the same calibrated world coordinate frame.

```text
Insta360 frame
  -> FieldTracker: AprilTag calibration and r0 pose
  -> CardDestinationScanner: QR-card detection
  -> card intent -> nearest compatible destination
  -> r0.set_goal((x_cm, y_cm), speed=3)
  -> existing A* planning, closed-loop control, and arrival stop
```

The scanner runs at a bounded low rate and decodes only QR values belonging to the existing card allowlist. It reads the card identity only; QR pixel position is intentionally not used as a goal.

## Selection and Trigger Rules

1. Require rover field calibration and a fresh pose for `r0`.
2. Decode a recognized card from the latest shared frame.
3. Map its intent to the candidate set above.
4. Choose the candidate with minimum Euclidean distance from `r0`'s current world position. Ties are resolved by the candidate list order.
5. Call `r0.set_goal()` with the selected center and speed level `3`. A new valid card replaces an unfinished route, matching the existing rover goal behavior.
6. A visible card emits one command. It must leave the frame for the configured missing-frame threshold before it can trigger again.

## Error Handling and Safety

- Do not move if calibration is unavailable, `r0` has no fresh pose, or QR decoding yields an unknown card.
- Do not move for `返航结算` until a ship destination is configured.
- Do not register the five destination circles as planner obstacles; the requested behavior is to reach their centers.
- Keep all existing rover protections unchanged: stale-pose stop, command TTL, explicit emergency stop, coordinate bounds checks, and route planning failure handling.
- Surface skipped/accepted card events in the agent console and visual overlay so an operator can verify the selected destination.

## Verification

Automated tests will cover card-intent mapping, nearest-destination selection, deterministic tie-breaking, duplicate-presentation gating, and rejection when calibration or pose is unavailable. Existing rover planner, controller, and bridge tests must continue to pass.

Hardware verification will use the shared Insta360 stream: calibrate the 80 cm x 60 cm field, place `r0` where nearest choices differ, present each supported card, and confirm the displayed selected center matches the expected destination before allowing the rover to travel at speed 3.

## Deferred Work

- Add the physical ship coordinate and enable `返航结算`.
- Send card selections through Runtime as a first-class event for centralized logs and UI state.
- Add multiple-rover routing and card-to-rover assignment.
