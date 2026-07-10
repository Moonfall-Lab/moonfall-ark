# Back-End MVP IR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `back-end` branch so the backend strictly follows `前后端对接文档 · Moonfall Runtime (MVP IR).md`.

**Architecture:** Keep the FastAPI application shell and replace the old cooperative world model with an MVP IR runtime state. A single world manager owns config loading, state mutation, event emission, command creation, and logging hooks used by REST and WebSocket routes.

**Tech Stack:** Python 3.8+, FastAPI, Pydantic v2, PyYAML, SQLite, standard-library `unittest`.

---

### Task 1: Contract Tests

**Files:**
- Create: `tests/test_mvp_ir_contract.py`

- [x] **Step 1: Write failing tests**

Create tests that assert `/api/state` returns the MD `state.world` payload shape, `/api/config` exposes config-driven IDs, REST inputs mutate faction vars, and debug endpoints emit events.

- [x] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_mvp_ir_contract -v`
Expected: failures for missing IR fields and missing routes.

### Task 2: IR Config And Models

**Files:**
- Modify: `backend/configs/moonfall.yaml`
- Modify: `backend/app/models/world.py`
- Modify: `backend/app/core/constants.py`

- [x] **Step 1: Implement config keys from the MD**

Add `game_id`, `schema_version`, `flow.phases`, `vars`, `factions`, `units`, `map.zones`, `inputs.cards`, and `director.events`.

- [x] **Step 2: Implement state models**

Replace global `fuel/core_hp/robots/players` with `global`, `factions`, `units`, `zones`, `rank_order`, and `winner`.

### Task 3: Runtime State And Logs

**Files:**
- Modify: `backend/app/runtime/world_state.py`
- Modify: `backend/app/services/event_logger.py`
- Modify: `backend/app/db/schema.sql`

- [x] **Step 1: Build state from config**

Initialize factions, vars, units, zones, phase, turn, session, and moon tier from config.

- [x] **Step 2: Add functional and AI logs**

Record functional logs for inputs/control/debug/state changes and AI logs for voice parsing and command generation.

### Task 4: REST And WebSocket Contract

**Files:**
- Modify: `backend/app/api/http_routes.py`
- Modify: `backend/app/api/websocket_routes.py`
- Modify: `backend/app/runtime/game_loop.py`

- [x] **Step 1: Implement MD REST routes**

Implement `/api/config`, `/api/config/load`, `/api/control/start`, `/api/control/reset`, `/api/input/declare_launch`, `/api/debug/set_var`, and `/api/debug/trigger_event`.

- [x] **Step 2: Implement MD WebSocket topics**

Accept `sensor.hr`, `input.voice`, `input.card`, and `input.declare_launch`; broadcast `state.world`, `state.event`, and commands using the unified envelope.

### Task 5: Integration Documentation

**Files:**
- Create: `docs/backend_integration.md`
- Create: `docs/ai_logs.md`
- Create: `docs/functional_logs.md`

- [x] **Step 1: Document frontend/backend connection methods**

Include base URL, `/ws`, REST route table, message examples, and cURL examples.

- [x] **Step 2: Document log semantics**

Explain AI logs and functional logs, including fields, sources, and when records are written.

### Task 6: Verification

**Files:**
- Test: `tests/test_mvp_ir_contract.py`

- [x] **Step 1: Run unit/API tests**

Run: `python -m unittest tests.test_mvp_ir_contract -v`
Expected: all tests pass.

- [x] **Step 2: Run import/compile check**

Run: `python -m compileall backend/app backend/clients tests`
Expected: exit code 0.
