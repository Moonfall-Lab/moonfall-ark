# Moonfall Ark Agent Notes

This repository is currently being rebuilt around a simplified two-rover card game. Treat this file as the working source of truth for future agents.

## Current Scope

Keep the frontend and hardware communication code, but the old backend runtime has been removed. The active backend is the new lightweight runtime in:

- `backend/moonfall_runtime/`

The frontend is still the existing React/Three.js app in:

- `frontend/`

The rover hardware/client code is preserved in:

- `backend/clients/rover_agent/`
- `backend/clients/*_client_example.py`

## Game Rules

The game currently has:

- 2 players: `p1`, `p2`
- 2 factions/ships: `pa`, `pb`
- 2 rovers: `r0`, `r1`
- `p1 -> pa -> r0`
- `p2 -> pb -> r1`

Initial ship state:

- `fuel = 0`
- `hp = 3`
- `ship_hp = hp`
- `relic_cards = 0`

Win condition:

- A player wins when their ship reaches `fuel >= 5`.
- Set `winner` to the faction id and `phase = ended`.

Supported QR/card actions:

- `探索遗迹` -> `explore_relic`
- `采集优先` / `能量优先` / `能源优先` / `燃料优先` -> `energy_priority`
- Anything else is ignored.

Turn flow:

- Only the current player should scan.
- Starts with `p1`.
- `POST /api/control/next_turn` switches `p1 <-> p2` and increments `turn`.
- The frontend top bar shows the current scanning player and has a "下一回合" button.

Target selection:

- `explore_relic`: choose an available ruins landmark.
- `energy_priority`: choose an available energy/high-energy landmark.
- Prefer the nearest available target to the current rover position.
- Do not choose the same landmark twice in a row if another valid target exists.

Arrival settlement:

- Normal energy station: player `fuel + 1`, station `fuel_blocks - 1`.
- High-energy station: player `fuel + min(2, remaining)`, station fuel reduced by that amount.
- Ruins: player `relic_cards + 1`, ruins `relic_cards - 1`.

## Field Coordinates

Backend and hardware use centimeters. Frontend coordinates are centimeters divided by 10.

Field size:

- `80cm x 60cm`
- frontend grid: `8 x 6`

Initial rover positions:

- `r0`: `(5, 30)` cm, frontend `(0.5, 3.0)`
- `r1`: `(75, 30)` cm, frontend `(7.5, 3.0)`

Landmarks:

| id | type | name | x_cm | y_cm | radius_cm | initial stock |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `obstacle-1` | `energy_station` | 西能源站 | 19.22 | 52.58 | 5.82 | `fuel_blocks = 5` |
| `obstacle-2` | `ruins` | 东北遗迹 | 61.51 | 51.09 | 5.44 | `relic_cards = 2` |
| `obstacle-3` | `high_energy_station` | 中央高能站 | 37.37 | 29.88 | 5.77 | `fuel_blocks = 3` |
| `obstacle-4` | `ruins` | 西南遗迹 | 12.71 | 10.16 | 5.94 | `relic_cards = 2` |
| `obstacle-5` | `energy_station` | 东南能源站 | 61.83 | 13.90 | 5.41 | `fuel_blocks = 5` |

## Active Backend Modules

- `backend/moonfall_runtime/state.py`
  - Holds game state, landmarks, rovers, factions, frontend serialization, heart rate state, arrival settlement.
- `backend/moonfall_runtime/qr.py`
  - Parses QR payload text and filters supported cards.
  - Supports raw Chinese text, JSON payloads, and URL query payloads.
- `backend/moonfall_runtime/targeting.py`
  - Selects the next landmark target.
- `backend/moonfall_runtime/messages.py`
  - Builds `state.world`, `state.event`, and `cmd.robot` envelopes.
- `backend/moonfall_runtime/server.py`
  - FastAPI app with HTTP and WebSocket APIs.
  - Also includes optional backend camera QR scanner.
- `backend/moonfall_runtime/qr_camera.py`
  - Standalone camera QR scanner utility.

## Frontend Integration

The frontend defaults to live backend mode:

- `frontend/src/config.js`
- `NEED_MOCK = false`

Frontend consumes:

- `GET /api/config`
- WebSocket `/ws`
- `state.world`
- `state.event`

Frontend sends:

- `POST /api/control/reset` on page load, so refresh starts from initial state.
- `POST /api/control/next_turn` from the top bar button.
- `POST /api/debug/qr` from the browser QR preview scanner.

Important UI areas:

- `frontend/src/components/TopBar.jsx`
  - Shows current scanning player and "下一回合".
- `frontend/src/components/CameraPreview.jsx`
  - Browser camera preview and QR scan status.
  - Sends recognized QR payloads to `/api/debug/qr` with the current player id.
- `frontend/src/components/MissionPanel.jsx`
  - Left panel only shows the two ships' HP and fuel blocks.
- `frontend/src/components/Scene3D.jsx`
  - Shows rover telemetry, target points, and field stock.

## WebSocket Protocol

All messages use:

```json
{
  "topic": "topic.name",
  "source": "sender",
  "timestamp": 1720000000.0,
  "payload": {}
}
```

Backend sends to rover hardware:

```json
{
  "topic": "cmd.robot",
  "source": "runtime",
  "payload": {
    "command_id": "uuid",
    "car_id": "r0",
    "robot_id": "r0",
    "action": "move",
    "x": 19.22,
    "y": 52.58,
    "speed": 5,
    "landmark_id": "obstacle-1"
  }
}
```

Hardware should send pose updates:

```json
{
  "topic": "perception.pose",
  "source": "rover_agent",
  "payload": {
    "car_id": "r0",
    "robot_id": "r0",
    "x": 12.3,
    "y": 35.6,
    "theta": 1.57,
    "status": "moving"
  }
}
```

Hardware should send arrival events:

```json
{
  "topic": "state.event",
  "source": "rover_agent",
  "payload": {
    "event_type": "robot_arrived",
    "command_id": "uuid-from-cmd",
    "car_id": "r0",
    "robot_id": "r0",
    "landmark_id": "obstacle-1"
  }
}
```

Heart rate input:

```json
{
  "topic": "sensor.hr",
  "source": "hr_p1",
  "payload": {
    "player_id": "p1",
    "heart_rate": 100
  }
}
```

Heart rate logic:

- Store `heart_rate` on the faction.
- Compute `stress = clamp((heart_rate - 80) / 40, 0, 1)`.
- Broadcast `state.world`.

## HTTP API

Active endpoints:

- `GET /api/config`
- `GET /api/state`
- `POST /api/control/reset`
- `POST /api/control/next_turn`
- `POST /api/debug/qr`
- `POST /api/input/hr`

`POST /api/debug/qr` body:

```json
{
  "player_id": "p1",
  "text": "采集优先"
}
```

`POST /api/input/hr` body:

```json
{
  "player_id": "p1",
  "heart_rate": 100
}
```

## Running

Install backend/frontend dependencies if needed:

```bash
.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend && npm install
```

Run backend:

```bash
PYTHONPATH=backend .venv/bin/python -m uvicorn moonfall_runtime.server:app --host 127.0.0.1 --port 8000
```

Run backend for LAN/hardware access:

```bash
MOONFALL_SIM_ROVERS=0 PYTHONPATH=backend .venv/bin/python -m uvicorn moonfall_runtime.server:app --host 0.0.0.0 --port 8000
```

Run frontend:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open:

- `http://127.0.0.1:5173/`
- `http://127.0.0.1:5173/#/dashboard`

Recommended full real-hardware flow:

Terminal 1, backend in real rover mode:

```bash
cd /Users/jan/Desktop/MoonF
MOONFALL_SIM_ROVERS=0 PYTHONPATH=backend .venv/bin/python -m uvicorn moonfall_runtime.server:app --host 127.0.0.1 --port 8000
```

Terminal 2, frontend:

```bash
cd /Users/jan/Desktop/MoonF/frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Terminal 3, global camera + rover control agent:

```bash
cd /Users/jan/Desktop/MoonF
env -u ALL_PROXY -u HTTPS_PROXY -u HTTP_PROXY -u all_proxy -u https_proxy -u http_proxy \
  NO_PROXY=127.0.0.1,localhost \
  PYTHONPATH=backend/clients \
  .venv/bin/python -m rover_agent.agent --camera 0 --bridge ws://127.0.0.1:8000/ws --viz
```

The proxy variables are intentionally unset for the local WebSocket bridge. Without this, Python WebSocket clients may try to use a system proxy and fail to connect to `127.0.0.1`.

Frontend QR scanning:

- `frontend/src/components/CameraPreview.jsx` opens the browser camera.
- It now prefers the Mac built-in camera by matching device labels like `FaceTime`, `Built-in`, `Mac`, or `内置`.
- The browser must be allowed camera access.
- Supported QR text is sent to `POST /api/debug/qr`.

Operational notes for a full run:

1. Start backend first.
2. Start frontend second.
3. Start `rover_agent` third after the global camera is available.
4. Open `http://127.0.0.1:5173/#/dashboard`.
5. Allow browser camera permission.
6. Scan `采集优先` or `探索遗迹`.
7. The backend selects a target landmark and sends `cmd.robot`.
8. `rover_agent` receives the command, drives the corresponding rover, and streams `perception.pose`.
9. On arrival, `rover_agent` sends `state.event / robot_arrived`; the backend settles fuel or relic rewards.

Useful manual controls while `rover_agent.agent` is running:

- `s` then Enter: stop all rovers.
- `p r0` or `p r1`: print current visual position.
- `r0 25 30 5`: manually send rover `r0` to `(25, 30)` cm at speed `5`.
- `q` then Enter: quit agent and stop all rovers.

Manual API checks:

```bash
curl -s http://127.0.0.1:8000/api/state | python -m json.tool
curl -s -X POST http://127.0.0.1:8000/api/control/reset | python -m json.tool
curl -s -X POST http://127.0.0.1:8000/api/debug/qr \
  -H 'Content-Type: application/json' \
  -d '{"player_id":"p1","text":"采集优先"}' | python -m json.tool
```

Stopping everything:

```bash
pkill -f "uvicorn moonfall_runtime.server:app"
pkill -f "node /Users/jan/Desktop/MoonF/frontend/node_modules/.bin/vite"
pkill -f "rover_agent.agent"
```

Optional backend camera scanner:

```bash
MOONFALL_QR_CAMERA=1 PYTHONPATH=backend .venv/bin/python -m uvicorn moonfall_runtime.server:app --host 127.0.0.1 --port 8000
```

Use the frontend browser camera preview for normal local QR scanning.

## Simulation vs Real Hardware

By default the backend simulates rover motion so the frontend can be tested without real hardware.

Default:

- `MOONFALL_SIM_ROVERS=1`

For real hardware:

- Start backend with `MOONFALL_SIM_ROVERS=0`.
- Hardware controller connects to `ws://<backend-ip>:8000/ws`.
- Hardware listens for `cmd.robot`.
- Hardware sends `perception.pose` and `state.event / robot_arrived`.

## Tests

Run active backend tests:

```bash
.venv/bin/python -m unittest tests/test_qr_recognition.py tests/test_targeting.py -v
```

Frontend build check:

```bash
cd frontend
npm run build
```

## Current Caveats

- The old backend under `backend/app` has been deleted.
- Existing README/docs still describe the old four-player runtime in places.
- Some old tests reference deleted backend modules and should not be treated as current truth.
- Browser QR scanning uses `BarcodeDetector`; if unsupported, use backend `qr_camera.py` or another scanner client.
- Page load resets backend state intentionally.
- With real hardware, disable rover simulation.
