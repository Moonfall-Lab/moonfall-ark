# Insta360 Link 2C QR Skill Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read Moonfall card QR codes from an Insta360 Link 2C, map the decoded Chinese card name to the configured skill ID, and report a non-mutating Runtime event once per card presentation.

**Architecture:** A hardware-independent scanner service loads the existing YAML card definitions, decodes frames through OpenCV with ROI retry and ZXing fallback, and gates repeated presentations. A small UVC client owns the Link 2C capture loop and WebSocket transport; Runtime validates the same mapping before broadcasting `qr_skill_detected`.

**Tech Stack:** Python 3.11+, OpenCV, NumPy, zxing-cpp Python binding, PyYAML, websockets, FastAPI/Pydantic, unittest.

## Global Constraints

- Work only on branch `insta360-qr` in `C:\Users\x\Desktop\git\moonfall-ark-insta360-qr`.
- Do not identify players, select targets, classify player/global scope, execute card effects, or mutate world state.
- Use `backend/configs/moonfall.yaml` as the only card-name-to-skill-ID source of truth.
- Default to the Link 2C physical UVC stream at 1920x1080 and 30 FPS; do not depend on Insta360 Virtual Camera or CameraSDK.
- Preserve the unrelated baseline failure in `MvpIrContractTest.test_config_exposes_frontend_ids` and run new QR tests separately as proof.

---

### Task 1: Skill allowlist and presentation gate

**Files:**
- Create: `backend/app/services/qr_skill_scanner.py`
- Create: `tests/test_qr_skill_scanner.py`

**Interfaces:**
- Produces: `SkillDefinition(skill_id: str, skill_name: str)`.
- Produces: `load_skill_allowlist(config_path: Path) -> dict[str, SkillDefinition]`, keyed by QR text/card name.
- Produces: `QrPresentationGate(missing_frame_threshold: int)` and `observe(visible_values: set[str]) -> list[str]`.

- [ ] **Step 1: Write failing allowlist tests**

```python
class SkillAllowlistTest(unittest.TestCase):
    def test_loads_supplied_card_names_from_runtime_config(self):
        skills = load_skill_allowlist(BACKEND / "configs" / "moonfall.yaml")
        expected = {
            "探索遗迹": "explore_relic",
            "燃料掠夺": "fuel_raid",
            "月岩炮击": "moonrock_strike",
            "返航结算": "return_settle",
            "采集优先": "collect_priority",
            "神之祈愿": "divine_prayer",
            "瞬移偷窃": "teleport_steal",
            "月尘护符": "dust_ward",
            "核心修复": "ark_repair",
            "并发任务": "concurrent_ops",
        }
        self.assertEqual({name: skills[name].skill_id for name in expected}, expected)

    def test_rejects_duplicate_card_names(self):
        path = self.write_config({"inputs": {"cards": [
            {"id": "a", "name": "重复"}, {"id": "b", "name": "重复"}
        ]}})
        with self.assertRaisesRegex(ValueError, "duplicate card name"):
            load_skill_allowlist(path)
```

- [ ] **Step 2: Run allowlist tests and verify RED**

Run: `python -m unittest tests.test_qr_skill_scanner.SkillAllowlistTest -v`
Expected: import failure because `app.services.qr_skill_scanner` does not exist.

- [ ] **Step 3: Implement the allowlist**

```python
@dataclass(frozen=True)
class SkillDefinition:
    skill_id: str
    skill_name: str

def load_skill_allowlist(config_path: Path) -> dict[str, SkillDefinition]:
    with Path(config_path).open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    inputs = config.get("inputs", {})
    result: dict[str, SkillDefinition] = {}
    for section in ("cards", "relic_cards"):
        entries = inputs.get(section, [])
        if not isinstance(entries, list):
            raise ValueError(f"inputs.{section} must be a list")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"inputs.{section} entries must be objects")
            skill_id = str(entry.get("id", "")).strip()
            skill_name = str(entry.get("name", "")).strip()
            if not skill_id or not skill_name:
                raise ValueError(f"inputs.{section} entries require id and name")
            if skill_name in result:
                raise ValueError(f"duplicate card name: {skill_name}")
            result[skill_name] = SkillDefinition(skill_id, skill_name)
    return result
```

- [ ] **Step 4: Run allowlist tests and verify GREEN**

Run: `python -m unittest tests.test_qr_skill_scanner.SkillAllowlistTest -v`
Expected: both tests pass.

- [ ] **Step 5: Write failing presentation-gate tests**

```python
class QrPresentationGateTest(unittest.TestCase):
    def test_emits_once_until_value_is_absent_for_threshold(self):
        gate = QrPresentationGate(missing_frame_threshold=2)
        self.assertEqual(gate.observe({"采集优先"}), ["采集优先"])
        self.assertEqual(gate.observe({"采集优先"}), [])
        self.assertEqual(gate.observe(set()), [])
        self.assertEqual(gate.observe(set()), [])
        self.assertEqual(gate.observe({"采集优先"}), ["采集优先"])

    def test_tracks_multiple_values_independently(self):
        gate = QrPresentationGate(missing_frame_threshold=1)
        self.assertCountEqual(gate.observe({"采集优先", "核心修复"}), ["采集优先", "核心修复"])
        self.assertEqual(gate.observe({"核心修复"}), [])
        self.assertEqual(gate.observe({"采集优先", "核心修复"}), ["采集优先"])
```

- [ ] **Step 6: Run gate tests and verify RED**

Run: `python -m unittest tests.test_qr_skill_scanner.QrPresentationGateTest -v`
Expected: import or attribute failure for `QrPresentationGate`.

- [ ] **Step 7: Implement the presentation gate**

```python
class QrPresentationGate:
    def __init__(self, missing_frame_threshold: int = 5):
        if missing_frame_threshold < 1:
            raise ValueError("missing_frame_threshold must be at least 1")
        self.missing_frame_threshold = missing_frame_threshold
        self._active: set[str] = set()
        self._missing: dict[str, int] = {}

    def observe(self, visible_values: set[str]) -> list[str]:
        emitted = sorted(visible_values - self._active)
        for value in visible_values:
            self._active.add(value)
            self._missing[value] = 0
        for value in list(self._active - visible_values):
            misses = self._missing.get(value, 0) + 1
            if misses >= self.missing_frame_threshold:
                self._active.remove(value)
                self._missing.pop(value, None)
            else:
                self._missing[value] = misses
        return emitted
```

- [ ] **Step 8: Run Task 1 tests and commit**

Run: `python -m unittest tests.test_qr_skill_scanner -v`
Expected: all Task 1 tests pass.

```powershell
git add backend/app/services/qr_skill_scanner.py tests/test_qr_skill_scanner.py
git commit -m "feat: add QR skill allowlist and presentation gate"
```

### Task 2: OpenCV decoder with ROI retry and ZXing fallback

**Files:**
- Modify: `backend/app/services/qr_skill_scanner.py`
- Modify: `tests/test_qr_skill_scanner.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Produces: `QrDecoder.decode(frame: numpy.ndarray) -> set[str]`.
- Produces: constructor injection `QrDecoder(primary=None, fallback=None)` for deterministic tests.

- [ ] **Step 1: Write failing decoder orchestration tests**

```python
class QrDecoderTest(unittest.TestCase):
    def test_uses_primary_results_without_fallback(self):
        fallback = RecordingFallback({"不应调用"})
        decoder = QrDecoder(primary=StaticPrimary(["采集优先"]), fallback=fallback)
        self.assertEqual(decoder.decode(object()), {"采集优先"})
        self.assertEqual(fallback.calls, 0)

    def test_uses_fallback_when_primary_has_no_text(self):
        fallback = RecordingFallback({"神之祈愿"})
        decoder = QrDecoder(primary=StaticPrimary([]), fallback=fallback)
        self.assertEqual(decoder.decode(object()), {"神之祈愿"})
        self.assertEqual(fallback.calls, 1)
```

- [ ] **Step 2: Run decoder tests and verify RED**

Run: `python -m unittest tests.test_qr_skill_scanner.QrDecoderTest -v`
Expected: import or attribute failure for `QrDecoder`.

- [ ] **Step 3: Add runtime dependencies**

Append exact requirements:

```text
numpy>=1.26.0
opencv-python>=4.10.0
zxing-cpp>=2.3.0
```

Install in the worktree environment with `python -m pip install -r backend/requirements.txt`.

- [ ] **Step 4: Implement decoder backends and ROI retry**

Implement `OpenCvQrBackend.decode(frame) -> set[str]` using `detectAndDecodeMulti` first and `detectAndDecode` second. When points exist but text is empty, compute the bounded QR rectangle, add 20% padding, apply a 32-pixel white border, resize 3x with nearest-neighbor interpolation, and retry. Implement `ZxingQrBackend.decode(frame)` with `zxingcpp.read_barcodes`, restricted to QR Code format. `QrDecoder.decode` returns non-empty primary values or invokes fallback once.

- [ ] **Step 5: Run decoder tests and verify GREEN**

Run: `python -m unittest tests.test_qr_skill_scanner.QrDecoderTest -v`
Expected: both decoder tests pass.

- [ ] **Step 6: Validate all supplied card images**

Run a read-only test helper over `C:\Users\x\Desktop\git\卡牌\1.png` through `10.png`, decoding with `QrDecoder` and mapping with `load_skill_allowlist`.
Expected mappings: the ten pairs listed in Task 1, including `6.png -> divine_prayer`.

- [ ] **Step 7: Run Task 2 tests and commit**

Run: `python -m unittest tests.test_qr_skill_scanner -v`
Expected: all scanner tests pass.

```powershell
git add backend/app/services/qr_skill_scanner.py backend/requirements.txt tests/test_qr_skill_scanner.py
git commit -m "feat: decode QR skills with OpenCV and ZXing fallback"
```

### Task 3: Runtime QR recognition event contract

**Files:**
- Modify: `backend/app/core/constants.py`
- Modify: `backend/app/api/websocket_routes.py`
- Create: `tests/test_qr_skill_runtime.py`
- Modify: `docs/websocket_topics.md`

**Interfaces:**
- Produces: constant `TOPIC_INPUT_QR_SKILL = "input.qr_skill"`.
- Consumes: `load_skill_allowlist(CONFIG_PATH)`.
- Produces: WebSocket `state.event` with `event_type == "qr_skill_detected"` and no state mutation.

- [ ] **Step 1: Write failing valid-event and state-immutability test**

```python
def test_valid_qr_skill_broadcasts_event_without_mutating_state(self):
    before = self.client.get("/api/state").json()
    with self.client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_json({
            "topic": "input.qr_skill",
            "source": "insta360_link_2c",
            "timestamp": 1720000000.0,
            "payload": {
                "qr_text": "瞬移偷窃",
                "skill_id": "teleport_steal",
                "skill_name": "瞬移偷窃",
            },
        })
        event = websocket.receive_json()
    self.assertEqual(event["topic"], "state.event")
    self.assertEqual(event["payload"]["event_type"], "qr_skill_detected")
    self.assertEqual(self.client.get("/api/state").json(), before)
```

- [ ] **Step 2: Run valid-event test and verify RED**

Run: `python -m unittest tests.test_qr_skill_runtime.QrSkillRuntimeTest.test_valid_qr_skill_broadcasts_event_without_mutating_state -v`
Expected: received `error` with code `UNKNOWN_TOPIC`.

- [ ] **Step 3: Implement the topic and handler**

Add the constant to `KNOWN_TOPICS`, route it in `route_message`, and implement `_handle_qr_skill`. The handler loads the configured allowlist, requires all three string fields, verifies name/text equality and the configured ID, then logs and broadcasts:

```python
event_payload = {
    "event_type": "qr_skill_detected",
    "message": f"识别到技能卡：{skill.skill_name}",
    "data": {
        "qr_text": qr_text,
        "skill_id": skill.skill_id,
        "skill_name": skill.skill_name,
    },
}
```

- [ ] **Step 4: Run valid-event test and verify GREEN**

Run the command from Step 2.
Expected: one test passes.

- [ ] **Step 5: Write and run failing validation tests**

Add separate tests for unknown `qr_text`, mismatched `skill_id`, and missing `skill_name`; each sends the envelope and asserts an `error` message with code `INVALID_PAYLOAD`. Run the three tests and confirm they fail before tightening validation.

- [ ] **Step 6: Complete validation and document the topic**

Reject empty fields, unknown names, and any ID/name mismatch with `ValueError`. Add the exact request/event examples from the design to `docs/websocket_topics.md` and state explicitly that detection does not execute the skill.

- [ ] **Step 7: Run Task 3 tests and commit**

Run: `python -m unittest tests.test_qr_skill_runtime tests.test_qr_skill_scanner -v`
Expected: all QR tests pass.

```powershell
git add backend/app/core/constants.py backend/app/api/websocket_routes.py tests/test_qr_skill_runtime.py docs/websocket_topics.md
git commit -m "feat: accept QR skill recognition events"
```

### Task 4: Link 2C UVC client and operational verification

**Files:**
- Create: `backend/clients/insta360_qr_client.py`
- Create: `tests/test_insta360_qr_client.py`
- Modify: `docs/backend_integration.md`

**Interfaces:**
- Produces: `build_qr_skill_message(skill: SkillDefinition, timestamp: float) -> dict[str, object]`.
- Produces CLI options: `--camera-index`, `--width`, `--height`, `--fps`, `--ws-url`, `--preview`, `--missing-frame-threshold`, and `--validate-images`.
- Consumes: `QrDecoder`, `QrPresentationGate`, and `load_skill_allowlist`.

- [ ] **Step 1: Write failing message and CLI-default tests**

```python
def test_build_message_uses_stable_contract(self):
    message = build_qr_skill_message(SkillDefinition("ark_repair", "核心修复"), 123.5)
    self.assertEqual(message["topic"], "input.qr_skill")
    self.assertEqual(message["source"], "insta360_link_2c")
    self.assertEqual(message["timestamp"], 123.5)
    self.assertEqual(message["payload"]["qr_text"], "核心修复")
    self.assertEqual(message["payload"]["skill_id"], "ark_repair")

def test_cli_defaults_to_link_2c_capture_profile(self):
    args = parse_args([])
    self.assertEqual((args.width, args.height, args.fps), (1920, 1080, 30))
    self.assertEqual(args.ws_url, "ws://127.0.0.1:8000/ws")
```

- [ ] **Step 2: Run client tests and verify RED**

Run: `python -m unittest tests.test_insta360_qr_client -v`
Expected: import failure because `backend.clients.insta360_qr_client` does not exist.

- [ ] **Step 3: Implement message construction and CLI parsing**

Add `build_qr_skill_message` with the exact envelope above. Add an `argparse` parser with camera index 0, 1920x1080, 30 FPS, WebSocket URL `ws://127.0.0.1:8000/ws`, preview false, missing threshold 5, and optional image-directory validation.

- [ ] **Step 4: Run client unit tests and verify GREEN**

Run the command from Step 2.
Expected: both tests pass.

- [ ] **Step 5: Implement validation and camera modes**

Validation mode enumerates numeric PNG filenames, decodes each image, resolves it through the allowlist, prints `filename<TAB>qr_text<TAB>skill_id`, and exits non-zero for any undecodable or unknown image. Camera mode opens DirectShow on Windows, applies width/height/FPS/buffer settings, observes decoded values through the gate, sends new known skills over WebSocket, and optionally draws an overlay and preview window. Camera/read/network failures produce clear stderr messages and non-zero exit status.

- [ ] **Step 6: Document setup and commands**

Document dependency installation, selecting the physical `Insta360 Link 2C` device, finding the camera index, validation mode, headless mode, preview mode, card rearm behavior, and the fact that the client reports recognition only.

- [ ] **Step 7: Run image and contract verification**

Run:

```powershell
python backend\clients\insta360_qr_client.py --validate-images 'C:\Users\x\Desktop\git\卡牌'
python -m unittest tests.test_qr_skill_scanner tests.test_qr_skill_runtime tests.test_insta360_qr_client -v
```

Expected: validation reports 10 recognized files; all QR-specific tests pass.

- [ ] **Step 8: Run the full suite and record the known baseline**

Run: `python -m unittest discover -s tests -v`
Expected: QR tests pass; the pre-existing `test_config_exposes_frontend_ids` failure remains unchanged unless main has independently corrected it.

- [ ] **Step 9: Commit the client and documentation**

```powershell
git add backend/clients/insta360_qr_client.py tests/test_insta360_qr_client.py docs/backend_integration.md
git commit -m "feat: add Insta360 Link 2C QR scanner client"
```

### Task 5: Final verification and branch handoff

**Files:**
- Verify only; modify files only for defects reproduced by a failing QR test.

**Interfaces:**
- Confirms the public CLI, WebSocket contract, and supplied-card mapping.

- [ ] **Step 1: Re-run card image validation**

Run: `python backend\clients\insta360_qr_client.py --validate-images 'C:\Users\x\Desktop\git\卡牌'`
Expected: 10/10 recognized and exit code 0.

- [ ] **Step 2: Re-run all QR-specific tests**

Run: `python -m unittest tests.test_qr_skill_scanner tests.test_qr_skill_runtime tests.test_insta360_qr_client -v`
Expected: zero failures and zero errors.

- [ ] **Step 3: Check repository state and diff quality**

Run: `git status --short --branch`, `git diff main...HEAD --check`, and `git log --oneline main..HEAD`.
Expected: clean worktree, no whitespace errors, and focused commits for design, scanner core, decoder, Runtime event, and Link 2C client.

- [ ] **Step 4: Report the hardware-only check separately**

State whether a live Link 2C was available. If available, report the exact camera command and observed event. If unavailable, report the hardware smoke test as outstanding without weakening the image and automated test results.
