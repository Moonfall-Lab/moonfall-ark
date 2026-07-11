# Insta360 Link 2C QR Skill Scanner Design

## Goal

Add an isolated, camera-side scanner that reads the QR code printed on a Moonfall card, maps the decoded Chinese card name to the existing skill ID, and reports a recognition event to Moonfall Runtime. The scanner does not identify the player, choose a target, execute a card effect, or mutate game state.

## Scope

- Capture the physical Insta360 Link 2C UVC stream on Windows, defaulting to 1920x1080 at 30 FPS.
- Recognize the ten card QR codes in `C:\Users\x\Desktop\git\卡牌`.
- Derive the allowlist from `inputs.cards` and `inputs.relic_cards` in `backend/configs/moonfall.yaml`; do not maintain a second card-name mapping.
- Emit one `input.qr_skill` message per card presentation and allow the same card to trigger again only after it has left the frame.
- Add a Runtime handler that validates and rebroadcasts recognition as `state.event` with `event_type: qr_skill_detected`.

Non-goals are player or face recognition, ArUco markers, target selection, global-versus-player classification, card-effect execution, card artwork editing, and camera gimbal control.

## Architecture

### Scanner client

`backend/clients/insta360_qr_client.py` owns camera configuration, frame capture, optional preview, WebSocket connection, reconnect behavior, and process shutdown. The camera index, frame width, frame height, FPS, Runtime WebSocket URL, preview flag, and missing-frame threshold are command-line options. On Windows it opens the physical Link 2C stream with DirectShow; other platforms use OpenCV's default backend.

Camera capture is synchronous and uses a buffer size of one. Recognition runs on the most recent frame available; the application does not build a frame queue. This keeps the first version small and prevents stale detections.

### Recognition service

`backend/app/services/qr_skill_scanner.py` contains hardware-independent logic:

- `SkillDefinition` represents the configured `skill_id` and Chinese `skill_name`.
- `load_skill_allowlist(config_path)` reads both card lists and returns a name-keyed allowlist.
- `QrDecoder` first uses OpenCV `QRCodeDetector`. If a QR outline is detected without text, it crops the outline with padding, adds a white quiet-zone border, enlarges the crop, and retries. ZXing-C++ is the final fallback.
- `QrPresentationGate` reports a known skill once, suppresses it while still visible, and rearms it after the configured number of consecutive frames in which that QR value is absent.

Unknown or empty QR values never produce Runtime input.

### Runtime input

The scanner sends:

```json
{
  "topic": "input.qr_skill",
  "source": "insta360_link_2c",
  "timestamp": 1720000000.0,
  "payload": {
    "qr_text": "瞬移偷窃",
    "skill_id": "teleport_steal",
    "skill_name": "瞬移偷窃"
  }
}
```

Runtime reloads the same configured allowlist and verifies that `qr_text`, `skill_name`, and `skill_id` describe one registered card. Valid input is logged and broadcast as:

```json
{
  "topic": "state.event",
  "source": "runtime",
  "timestamp": 1720000000.0,
  "payload": {
    "event_type": "qr_skill_detected",
    "message": "识别到技能卡：瞬移偷窃",
    "data": {
      "qr_text": "瞬移偷窃",
      "skill_id": "teleport_steal",
      "skill_name": "瞬移偷窃"
    }
  }
}
```

An unknown or inconsistent mapping returns the existing `INVALID_PAYLOAD` error path. Runtime does not call `apply_card`, `trigger_event`, or any command broadcaster.

## Reliability and Operations

- Default recognition source is the Link 2C physical stream, not Insta360 Virtual Camera.
- A failed camera open exits with a clear error and non-zero status.
- Transient frame-read failures are retried; repeated failures exit instead of spinning forever.
- WebSocket disconnects use bounded reconnect attempts with short backoff. Recognition remains gated while disconnected so reconnecting cannot replay a continuously visible card.
- Preview mode overlays the decoded name and skill ID for setup; headless mode is the default for deployment.
- Logs distinguish recognized, suppressed, unknown, undecodable, camera, and network outcomes without logging full video frames.

## Dependencies

- Add OpenCV and NumPy for UVC capture, detection, ROI preprocessing, and preview.
- Add the `zxing-cpp` Python binding for fallback decoding.
- Keep the existing `websockets`, PyYAML, FastAPI, and Pydantic stack.

The scanner must run under the project's documented Python 3.11+ environment. The current machine's Python 3.8 may be used only for read-only inspection, not as the supported deployment baseline.

## Test Strategy

- Unit-test allowlist loading for all ten configured names and IDs, including duplicate-name and malformed-entry rejection.
- Unit-test presentation gating: first appearance emits, continuous presence suppresses, absence below threshold stays suppressed, threshold absence rearms, and two different cards are tracked independently.
- Unit-test decoder orchestration with injected primary and fallback decoders so the OpenCV-success, ROI-retry, ZXing-fallback, and undecodable paths are deterministic.
- API-test valid `input.qr_skill`, unknown QR text, inconsistent ID/name pairs, and the guarantee that recognition does not mutate world state.
- Add a manual validation command that reads the ten external PNG card files and reports a 10/10 mapping result without modifying them.
- Add a hardware smoke-test procedure for Link 2C at 1080p30: open physical stream, present every card, confirm one event per presentation, remove and re-present one card, and confirm a second event.

## Acceptance Criteria

- All ten supplied card images decode to the matching configured skill IDs.
- A continuously visible card produces exactly one Runtime event.
- Removing and re-presenting the card produces another event.
- Unknown QR codes and inconsistent client payloads do not produce skill events.
- Recognition events do not change player, faction, unit, or global state.
- The scanner can select a Link 2C camera index and run with or without preview.
