# Feature: 001-push-to-talk — Vox MVP (Push-to-Talk Voice Input Layer)

The following plan should be complete, but it is important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files etc.

## Feature Description

Implement the full **Vox MVP** from `.ai/SPECS/001-push-to-talk/PRD.md`: a push-to-talk voice input layer that captures speech via a global hotkey, transcribes it locally with faster-whisper, and injects the text into the system (clipboard and optionally into the focused window). When this plan is completed, a user can install Vox, configure a hotkey and optional device/model, run `vox run`, press the hotkey, speak, release, and see the transcribed text in the clipboard (and optionally in the focused window) with no cloud calls and no silent failures.

## User Story

As a **user / operator of an agent workflow system**, I want to **press a key, speak, and have the text appear where I need it (clipboard and/or focused field)** so that **voice becomes actionable input without switching apps or using cloud transcription**.

## Problem Statement

Users need a local, always-available voice-to-text layer that integrates at the system level (global hotkey, clipboard, optional keystroke injection) and can later feed agents (Pepper, GROVE, etc.). Today there is no such tool in the repo; the package `src/vox` does not exist and the build fails.

## Solution Statement

Deliver the complete MVP in four phases: (1) foundation and audio capture with config and CLI `vox devices` / `vox test-mic`; (2) faster-whisper transcription wired to capture output; (3) injection (clipboard + optional paste/type) and global hotkey with `vox run`; (4) polish, Rich CLI output, README, and config example. All MVP scope from the PRD is covered so that plan completion = MVP ready to use.

## Current Status (Repo Reality)

- Phase 1 and Phase 2 are implemented and gated by `just test quality`.
- Phase 3 (global hotkey + injection + `vox run`) is not implemented yet.
- Phase 4 (example config + final MVP walkthrough docs) is partially complete (README exists, but `vox.toml.example` is not added yet).

## Feature Metadata

**Feature Type:** New Capability  
**Estimated Complexity:** High  
**Primary Systems Affected:** New package `src/vox` (cli, config, capture, transcribe, inject, hotkey), `tests/`, `pyproject.toml`, `README.md`  
**Dependencies:** faster-whisper, sounddevice, Rich, Typer; Python ≥3.12, uv  
**Dev quality gates:** `pytest-drill-sergeant` (strict AAA + marker enforcement)

## Traceability Mapping

- Roadmap system improvements: `None`
- Debt items: `None`
- **No SI/DEBT mapping for this feature.**

## Branch Setup (Required)

Branch naming follows the plan filename:
- Plan: `.ai/PLANS/001-push-to-talk.md`
- Branch: `feat/001-push-to-talk`

Commands (must be executable as written):

```bash
PLAN_FILE=".ai/PLANS/001-push-to-talk.md"
PLAN_SLUG="$(basename "$PLAN_FILE" .md)"
BRANCH_NAME="feat/${PLAN_SLUG}"
git show-ref --verify --quiet "refs/heads/${BRANCH_NAME}" \
  && git switch "${BRANCH_NAME}" \
  || git switch -c "${BRANCH_NAME}"
```

On Windows PowerShell (if the above is run in sh/git-bash):

```powershell
$PLAN_FILE = ".ai/PLANS/001-push-to-talk.md"
$PLAN_SLUG = [System.IO.Path]::GetFileNameWithoutExtension($PLAN_FILE)
$BRANCH_NAME = "feat/$PLAN_SLUG"
git switch $BRANCH_NAME 2>$null; if ($LASTEXITCODE -ne 0) { git switch -c $BRANCH_NAME }
```

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `.ai/SPECS/001-push-to-talk/PRD.md` — Full MVP scope, architecture, CLI surface, success criteria, phases 1–4.
- `.ai/RULES.md` — Workflow invariants, quality gates, non-negotiables, architecture boundaries, CLI/UX rules.
- `.ai/REF/project-types/cli-tool.md` — Rich output, no raw JSON by default, validation expectations.
- `.ai/REF/testing-and-gates.md` — Baseline loop and final gate (use `just test quality` in this repo).
- `pyproject.toml` — Project name `vox`, Python 3.12+, hatchling build, packages `src/vox`, pytest/mypy/ruff config, no runtime deps yet.
- `justfile` — Targets: `test`, `lint`, `format-check`, `types`, `quality`, `e2e`.

### New Files to Create

- `src/vox/__init__.py`
- `src/vox/cli.py` — CLI entry (Typer or argparse); commands: run, devices, test-mic.
- `src/vox/config.py` — Config schema and load from file/env; validation, no silent fallbacks.
- `src/vox/capture/__init__.py`, `src/vox/capture/stream.py` (or single module) — Audio capture, device enumeration, stream start/stop.
- `src/vox/transcribe/__init__.py`, `src/vox/transcribe/faster_whisper_backend.py` — faster-whisper wrapper; audio in → text out.
- `src/vox/inject/__init__.py`, `src/vox/inject/clipboard.py`, optional `inject/keystroke.py` — Clipboard (required), optional paste/type.
- `src/vox/hotkey/__init__.py`, `src/vox/hotkey/register.py` — Global hotkey registration; start/stop callback.
- `tests/unit/` — Tests for config, capture, transcribe, inject (with mocks).
- `tests/integration/` — Capture → transcribe; optional capture → transcribe → inject (clipboard).
- `tests/e2e/` — Optional: full vox run simulation or manual checklist.
- `docs/dev/` — Optional status/roadmap updates per `.ai/REF/status-surfaces.md`.
- Example config: `vox.toml.example` or documented in README.

### Relevant Documentation (read before implementing)

- [faster-whisper GitHub](https://github.com/SYSTRAN/faster-whisper) — Installation, `WhisperModel`, `transcribe()`, model sizes, compute_type, generator segments.
- [faster-whisper Usage](https://github.com/SYSTRAN/faster-whisper#usage) — Code examples; segments are a generator (must iterate to run).
- [sounddevice](https://python-sounddevice.readthedocs.io/) — Input device list, stream recording, sample rate.
- [Rich](https://rich.readthedocs.io/) — Tables, panels for CLI output per project rules.
- [pynput](https://pynput.readthedocs.io/) — Global hotkey and keyboard controller (if chosen for hotkey + optional injection).

### Patterns to Follow

- **Naming:** snake_case modules and functions; Google-style docstrings; type hints everywhere (`mypy` strict).
- **Error handling:** No silent fallbacks for required config/device; raise with clear, actionable messages (e.g. "Microphone not found: check VOX_DEVICE_ID or run `vox devices`").
- **Imports:** Use absolute imports from `vox.*`; no relative imports (ruff TID ban).
- **Tests:** `tmp_path` for temp files; no hardcoded global temp paths; pytest markers `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e` where applicable.
- **CLI:** Rich tables/panels for `vox devices` and any listing; no raw JSON as default.

---

## IMPLEMENTATION PLAN

Use markdown checkboxes (`- [ ]`) for implementation phases and task bullets so execution progress can be tracked live.

### Phase 1: Foundation and capture

**Intent Lock**

- **Source of truth:** `.ai/SPECS/001-push-to-talk/PRD.md` §4 MVP Scope (in scope), §6 Directory structure, §7.2 Audio capture, §7.5 Configuration, §7.6 CLI (devices, test-mic).
- **Must:** Package `src/vox` exists and builds; config loads from file and/or env and validates required fields with explicit errors; `vox devices` lists audio input devices; `vox test-mic` records for N seconds then **plays back** the recording (so user can verify mic and level); no transcription or injection in this phase.
- **Must not:** Silent fallbacks for missing config; hardcoded device or paths; skip validation; test-mic without play-back.
- **Provenance:** Config schema and example live in repo; device list from sounddevice (or chosen lib); playback via same audio lib (e.g. sounddevice output stream).
- **Acceptance criteria:** (1) `src/vox` imports and package builds with uv. (2) Config load fails with field-specific error when required field (e.g. hotkey) missing. (3) `vox devices` prints Rich table of devices. (4) `vox test-mic --seconds 2` records, then plays back the recording, then exits 0; no transcription yet. (5) Unit tests for config and capture pass.
- **Non-goals:** Transcription; injection; global hotkey; `vox run`. No faster-whisper or clipboard/hotkey deps in this phase.
- **Acceptance gates:** `just test quality`; `uv run vox devices` exits 0 and prints device list; `uv run vox test-mic --seconds 2` records then plays back without error (no transcribe yet).

**Tasks:**

- [x] CREATE `src/vox/` package layout: `__init__.py`, `cli.py`, `config.py`, `capture/__init__.py`, placeholder `transcribe/__init__.py`, `inject/__init__.py`, `hotkey/__init__.py`.
- [x] ADD to `pyproject.toml`: runtime dependencies (e.g. `sounddevice`, `rich`); ensure `[tool.hatchling.build] packages = ["src/vox"]` (or add `[tool.hatch.build.targets.wheel]` if hatch version requires it). Pin versions with rationale in plan.
- [x] IMPLEMENT config: schema (hotkey, device_id, model_size, compute_type, injection_mode, config file path); load from `vox.toml` / `~/.config/vox/vox.toml` and env; validate required fields; raise with field-specific errors.
- [x] IMPLEMENT capture: list devices (sounddevice), start/stop stream, return buffer (e.g. numpy float32 or int16) at 16 kHz mono for later faster-whisper.
- [x] IMPLEMENT CLI: `vox devices` (Rich table of device id and name), `vox test-mic [--device ID] [--seconds N]` (record for N seconds, then **play back** the recording so user can verify capture; no transcribe in Phase 1).
- [x] ADD unit tests: config validation (missing field, invalid value); capture device list and record-to-buffer (mock or real device).
- [x] VALIDATE: `just test quality`; `uv run vox devices`; `uv run vox test-mic --seconds 2`.

### Phase 2: Local transcription (faster-whisper)

**Intent Lock**

- **Source of truth:** `.ai/SPECS/001-push-to-talk/PRD.md` §7.3 Transcription, §8 Core dependencies (faster-whisper), §12 Phase 2 deliverables.
- **Must:** `transcribe` module uses `faster_whisper.WhisperModel`; accepts audio (file path or buffer at 16 kHz mono); returns plain text; model size and compute_type from config; iterate segments to force completion; no cloud calls.
- **Must not:** Assume system FFmpeg (faster-whisper uses PyAV); silent failure on model load or inference.
- **Provenance:** Model from Hugging Face auto-download or local path; document in README.
- **Acceptance criteria:** (1) Unit test: fixture audio file → transcribe → non-empty string. (2) Integration: capture → write WAV → transcribe → assert text. (3) `vox test-mic --seconds 3` runs capture → play back → transcribe and prints transcribed text. (4) README documents model download and GPU/CPU/int8. (5) All quality and test gates pass.
- **Non-goals:** Injection (clipboard/keystroke); global hotkey; `vox run`. No pyperclip/pynput in this phase.
- **Acceptance gates:** Unit test with fixture audio → transcribe → assert text; `vox test-mic --seconds 3` runs capture → play back → transcribe and prints text; `just test quality`.

**Tasks:**

- [x] ADD dependency `faster-whisper` to `pyproject.toml` with pinned version and rationale.
- [x] IMPLEMENT `src/vox/transcribe/faster_whisper_backend.py`: load model by size/path and compute_type; `transcribe(audio_path_or_buffer)` → plain text; handle generator (list(segments)); raise on model not found or inference error.
- [x] WIRE capture output to transcribe input: convert capture buffer to format faster-whisper accepts (e.g. write to temp WAV at 16 kHz mono or pass buffer if API supports).
- [x] EXTEND CLI: `vox test-mic [--device ID] [--seconds N]` runs capture → play back → transcribe and prints transcribed text.
- [x] ADD unit tests: transcribe with small fixture audio file (in repo or generated); integration test: capture (mock or short real) → transcribe → assert non-empty string.
- [x] DOCUMENT in README: model download (first run or explicit), optional GPU (CUDA 12 / cuDNN 9), CPU/int8.
- [x] VALIDATE: `just test quality`; run `vox test-mic --seconds 3` and confirm printed text.

### Phase 3: Injection and hotkey (full push-to-talk loop)

**Intent Lock**

- **Source of truth:** `.ai/SPECS/001-push-to-talk/PRD.md` §7.1 Push-to-talk, §7.4 Injection, §10 CLI (`vox run`), §12 Phase 3 deliverables.
- **Must:** Clipboard injection (required); optional paste/type into focused window; global hotkey registration; on key down start capture, on key up stop capture → transcribe → inject; `vox run` runs this loop; clear errors for mic/model/injection failure.
- **Must not:** Silent truncation of text; skip clipboard when injection fails without clear error.
- **Provenance:** Hotkey and injection mode from config; pynput or chosen lib for hotkey and optional keystroke.
- **Acceptance criteria:** (1) Clipboard module sets text and raises on failure. (2) Optional keystroke module implementable and behind config. (3) Hotkey registers from config; on release runs capture → transcribe → inject. (4) `vox run` starts, registers hotkey, and on trigger places text in clipboard (and optionally in focused field). (5) Integration test: mock capture+transcribe → inject → assert clipboard. (6) Errors for mic/model/injection are actionable. (7) `just test quality` passes.
- **Non-goals:** Tray icon; background service; README/config example polish (Phase 4). No new docs beyond inline/error messages in this phase.
- **Acceptance gates:** `vox run` starts and registers hotkey; manual test: focus text field, press hotkey, speak, release → text in clipboard and optionally in field; integration test simulates trigger and verifies clipboard content; `just test quality`.

**Tasks:**

- [ ] ADD dependencies: `pyperclip` (or platform clipboard); `pynput` (or chosen) for global hotkey and optional keyboard injection.
- [ ] IMPLEMENT `src/vox/inject/clipboard.py`: set clipboard to string; raise on failure with clear message.
- [ ] IMPLEMENT optional `src/vox/inject/keystroke.py`: paste (e.g. Ctrl+V) or type text into focused window; configurable on/off; document OS permissions (accessibility).
- [ ] IMPLEMENT `src/vox/hotkey/register.py`: register global hotkey from config; on press start capture callback, on release stop capture and invoke callback with audio buffer (or path).
- [ ] IMPLEMENT main loop in `cli.py`: `vox run` loads config, registers hotkey; on trigger: capture until release → transcribe(audio) → inject(text); loop until exit.
- [ ] ADD integration test: mock capture + transcribe returning fixed string → inject to clipboard → assert clipboard content (or mock clipboard).
- [ ] ADD error handling: mic unavailable, model not found, injection failed — all with actionable messages.
- [ ] VALIDATE: `just test quality`; manual: `vox run`, hotkey, speak, release, check clipboard (and optional focused field).

### Phase 4: Polish and docs (shippable MVP)

**Intent Lock**

- **Source of truth:** `.ai/SPECS/001-push-to-talk/PRD.md` §11 Success criteria, §12 Phase 4, §7.6 CLI (Rich output), README and config example.
- **Must:** README with install, config, run instructions; example config file; Rich tables/panels for `vox devices` and any list output; final gate `just test quality`; "Definition of Visible Done" satisfiable.
- **Must not:** Leave CLI as raw print; ship without README or config example.
- **Provenance:** README and example config in repo; any accepted warnings documented with rationale.
- **Acceptance criteria:** (1) README covers install, config location, env overrides, `vox run`/`vox devices`/`vox test-mic`, model setup, OS permissions, Definition of Visible Done. (2) `vox.toml.example` exists with hotkey, device_id, model_size, compute_type, injection_mode and comments. (3) `vox devices` (and any list) uses Rich table/panel; no raw JSON default. (4) Warnings from `just test quality` fixed or documented with rationale. (5) `docs/dev/status.md` (or equivalent) updated for MVP complete. (6) New user can complete Definition of Visible Done using README. (7) `just test quality` passes.
- **Non-goals:** New features or new code paths; agent wiring; tray/installer. Only polish, docs, and status.
- **Acceptance gates:** New user can follow README to install (uv), configure (hotkey, optional device/model), run `vox run`, and complete push-to-talk successfully; `just test quality`; all acceptance criteria below met.

**Tasks:**

- [ ] UPDATE README: project description; install (`uv sync` or pip install -e .); config file location and env overrides; commands `vox run`, `vox devices`, `vox test-mic`; model setup (first run / GPU/CPU); OS permissions (mic, accessibility if keystroke); "Definition of Visible Done" steps.
- [ ] ADD example config: `vox.toml.example` or equivalent with hotkey, device_id, model_size, compute_type, injection_mode; document each key.
- [ ] ENSURE Rich usage: `vox devices` outputs Rich table; any other list/status use Rich panel/table; no raw JSON as default.
- [ ] REVIEW warnings: run `just test quality`; fix or document any accepted residual warnings with rationale and owner/target.
- [ ] ADD or UPDATE `docs/dev/status.md` (or roadmap) per `.ai/REF/status-surfaces.md` to reflect MVP complete.
- [ ] VALIDATE: Full pass `just test quality`; walk through README as new user; confirm Definition of Visible Done.

---

## Phase Intent Check Report (all phases)

*Generated per `.ai/COMMANDS/phase-intent-check.md`. Treat Must/Must Not as binding during implementation. After each phase: update plan checklist, run status-sync if applicable, append evidence in Execution Report.*

### Phase 1: Foundation and capture — **Locked**

| Item | Detail |
|------|--------|
| **Source docs** | `.ai/SPECS/001-push-to-talk/PRD.md` §4 MVP Scope, §6 Directory structure, §7.2 Audio capture, §7.5 Configuration, §7.6 CLI (devices, test-mic); `.ai/RULES.md` |
| **Must** | Package `src/vox` exists and builds; config loads from file/env and validates required fields with explicit errors; `vox devices` lists devices; `vox test-mic` records N seconds then plays back the recording; no transcription or injection in this phase |
| **Must not** | Silent fallbacks for missing config; hardcoded device or paths; skip validation; test-mic without play-back |
| **Exact acceptance gates** | `just test quality`; `uv run vox devices` (exit 0, device list); `uv run vox test-mic --seconds 2` (exit 0, record then play back, no transcribe) |

### Phase 2: Local transcription (faster-whisper) — **Locked**

| Item | Detail |
|------|--------|
| **Source docs** | `.ai/SPECS/001-push-to-talk/PRD.md` §7.3 Transcription, §8 Core dependencies (faster-whisper), §12 Phase 2; `.ai/RULES.md` |
| **Must** | `transcribe` uses `faster_whisper.WhisperModel`; accepts audio (path or 16 kHz mono buffer); returns plain text; model size/compute_type from config; iterate segments; no cloud calls |
| **Must not** | Assume system FFmpeg; silent failure on model load or inference |
| **Exact acceptance gates** | Unit test: fixture audio → transcribe → assert text; `vox test-mic --seconds 3` runs capture + transcribe and prints text; `just test quality` |

### Phase 3: Injection and hotkey (full push-to-talk loop) — **Locked**

| Item | Detail |
|------|--------|
| **Source docs** | `.ai/SPECS/001-push-to-talk/PRD.md` §7.1 Push-to-talk, §7.4 Injection, §10 CLI (`vox run`), §12 Phase 3; `.ai/RULES.md` |
| **Must** | Clipboard injection (required); optional paste/type; global hotkey; on key down start capture, on key up stop → transcribe → inject; `vox run` runs loop; clear errors for mic/model/injection |
| **Must not** | Silent truncation of text; skip clipboard on injection failure without clear error |
| **Exact acceptance gates** | `vox run` starts and registers hotkey; manual: focus field, hotkey, speak, release → text in clipboard (and optionally field); integration test: trigger → verify clipboard; `just test quality` |

### Phase 4: Polish and docs (shippable MVP) — **Locked**

| Item | Detail |
|------|--------|
| **Source docs** | `.ai/SPECS/001-push-to-talk/PRD.md` §11 Success criteria, §12 Phase 4, §7.6 CLI (Rich), README/config example; `.ai/RULES.md`; `.ai/REF/status-surfaces.md` |
| **Must** | README (install, config, run); example config file; Rich for `vox devices`/lists; `just test quality`; Definition of Visible Done satisfiable |
| **Must not** | CLI as raw print only; ship without README or config example |
| **Exact acceptance gates** | New user follows README → install, configure, `vox run`, push-to-talk success; `just test quality`; all plan Acceptance criteria met |

---

## STEP-BY-STEP TASKS

Execute in order. Each task is atomic and independently testable.

### Phase 1 (Foundation and capture)

1. **CREATE** `src/vox/__init__.py` — Package version or minimal export; **VALIDATE** `uv run python -c "import vox; print(vox)"`.
2. **CREATE** `src/vox/config.py` — Dataclass or Pydantic schema: hotkey, device_id (optional), model_size, compute_type, config_path, injection_mode; load from file then env override; validate required (e.g. hotkey); raise ValueError with field name. **PATTERN:** Fail-fast, no defaults for required. **VALIDATE** unit test: missing hotkey raises with message containing "hotkey".
3. **CREATE** `src/vox/capture/__init__.py` and `capture/stream.py` — `list_devices()` → list of (id, name); `record_until_stop(device_id, sample_rate=16000, channels=1)` → numpy array or bytes (16 kHz mono). Use sounddevice. **VALIDATE** unit test with default device or mock.
4. **UPDATE** `pyproject.toml` — Add `dependencies = ["sounddevice>=0.4.6", "rich>=13.0.0"]` (or current versions); ensure hatch build includes `src/vox`. **VALIDATE** `uv sync` and `uv run python -c "import vox"`.
5. **CREATE** `src/vox/cli.py` — Entry: `vox` or `python -m vox`; subcommands: `devices`, `test-mic`. `devices`: list capture.list_devices() in Rich table. `test-mic`: capture.record for N seconds (default 2), then **play back** the recording (e.g. sounddevice playback or same lib); no transcribe. **IMPORTS:** Typer or argparse, Rich. **VALIDATE** `uv run vox devices`; `uv run vox test-mic --seconds 2` (user hears play-back).
6. **CREATE** `src/vox/transcribe/__init__.py`, `src/vox/inject/__init__.py`, `src/vox/hotkey/__init__.py` — Empty or placeholder exports so package structure exists.
7. **ADD** `tests/unit/test_config.py`, `tests/unit/test_capture.py` — Config validation; capture list_devices and record. **VALIDATE** `just test`.
8. **VALIDATE** `just test quality`.

### Phase 2 (Transcription)

9. **UPDATE** `pyproject.toml` — Add `faster-whisper` (pin version, e.g. `>=1.0.0,<2`). **VALIDATE** `uv sync`.
10. **CREATE** `src/vox/transcribe/faster_whisper_backend.py` — `WhisperModel(model_size_or_path, device="cpu"|"cuda", compute_type=...)`; `transcribe(audio_path: Path | bytes)` → str; convert segments to single text; iterate generator. **VALIDATE** unit test with small WAV fixture.
11. **WIRE** capture output to transcribe: in test-mic, after record and play-back, write capture buffer to temp WAV 16 kHz mono, call transcribe, print text. **VALIDATE** `vox test-mic --seconds 3` plays back then prints text.
12. **ADD** `tests/unit/test_transcribe.py`, `tests/integration/test_capture_transcribe.py` — Fixture audio → text; capture → transcribe. **VALIDATE** `just test`.
13. **UPDATE** README — Model download, GPU/CPU, int8. **VALIDATE** `just test quality`.

### Phase 3 (Injection and hotkey)

14. **UPDATE** `pyproject.toml` — Add `pyperclip`, `pynput` (or chosen). **VALIDATE** `uv sync`.
15. **CREATE** `src/vox/inject/clipboard.py` — `set_clipboard(text: str)`; use pyperclip; raise on failure. **VALIDATE** unit test (mock or real clipboard).
16. **CREATE** `src/vox/inject/keystroke.py` (optional) — `paste_text(text)` or `type_text(text)`; pynput keyboard controller; config flag to enable. **VALIDATE** unit test with mock.
17. **CREATE** `src/vox/hotkey/register.py` — Register hotkey from config (e.g. pynput); on_press start recording (set flag or start thread), on_release stop and call callback with buffer/path. **VALIDATE** unit test with mock listener.
18. **UPDATE** `src/vox/cli.py` — `vox run`: load config, register hotkey; on trigger: capture → write temp WAV → transcribe → inject (clipboard + optional keystroke). Loop until Ctrl+C. **VALIDATE** manual: run, press hotkey, speak, release; check clipboard.
19. **ADD** integration test: mock capture+transcribe, inject to clipboard, assert clipboard equals transcribed string. **VALIDATE** `just test quality`.

### Phase 4 (Polish and docs)

20. **UPDATE** README — Full install, config (file + env), commands, model setup, permissions, Definition of Visible Done. **VALIDATE** Read through as new user.
21. **CREATE** `vox.toml.example` — hotkey, device_id, model_size, compute_type, injection_mode; comments. **VALIDATE** `vox run` can load it when copied to config path.
22. **ENSURE** Rich: `vox devices` table; any other lists/status in Rich. **VALIDATE** `vox devices` output.
23. **RUN** `just test quality`; fix or document warnings. **VALIDATE** Clean or documented.
24. **UPDATE** `docs/dev/status.md` (or create) — MVP complete, current focus. **VALIDATE** Per status-surfaces.md.

---

## TESTING STRATEGY

### Unit tests

- Config: valid load, missing required field, invalid value → explicit error.
- Capture: list_devices (mock or real); record returns buffer of expected shape/dtype.
- Transcribe: fixture WAV → non-empty string; invalid path → error.
- Inject: set_clipboard (mock or real); optional keystroke mock.
- Hotkey: register/unregister; callback invoked on key release (mock).

### Integration tests

- Capture → transcribe: record short buffer, write WAV, transcribe → assert text.
- Capture → transcribe → inject: mock or short real capture, transcribe, set clipboard → assert clipboard.

### Edge cases

- No microphone; invalid device_id; model not found; empty audio (silence) → transcribe returns empty or short string; clipboard fail on headless.

---

## VALIDATION COMMANDS

### Level 1: Syntax & style

- `just format` then `just format-check`
- `just lint`

### Level 2: Types and quality

- `just types`
- `just test quality` (pytest + full quality toolchain)

### Level 3: Tests

- `just test`
- Final gate: `just test quality`

### Level 4: Manual (MVP)

- `uv run vox devices` — table of devices.
- `uv run vox test-mic --seconds 2` — records then plays back (Phase 1); after Phase 2 also transcribes and prints text.
- `uv run vox run` — starts; press configured hotkey, speak, release; paste from clipboard (and optionally see text in focused field).

### Level 5: E2E (optional)

- `just e2e` if e2e tests are added (e.g. vox run with mock hotkey and assert clipboard).

---

## OUTPUT CONTRACT (Required)

- **Artifacts/surfaces:**
  - CLI: `vox run`, `vox devices`, `vox test-mic` (entry via `uv run vox` or installed `vox`).
  - Config file: `vox.toml` (or equivalent) in documented location; example in repo.
  - Clipboard: transcribed text after each push-to-talk cycle when `vox run` is active.
- **Verification commands:**
  - `uv run vox devices` → exit 0, Rich table of devices.
  - `uv run vox test-mic --seconds 3` → exit 0, play-back of recording then transcribed text printed.
  - Manual: `uv run vox run` → hotkey → speak → release → paste from clipboard shows transcribed text.

## DEFINITION OF VISIBLE DONE (Required)

A human can directly verify MVP completion by:

1. **Install:** From repo run `uv sync` (or `pip install -e .`).
2. **Configure:** Copy `vox.toml.example` to config path (e.g. `~/.config/vox/vox.toml`); set hotkey and optionally device/model.
3. **Run:** Execute `uv run vox run` (or `vox run` if installed).
4. **Trigger:** Focus any text field (or leave focus anywhere); press and hold (or toggle) the configured hotkey; speak a short phrase; release the key.
5. **Verify:** Paste from clipboard (Ctrl+V / Cmd+V) and see the transcribed phrase. If injection includes "paste into focused window," the text also appears in the focused field without manual paste.
6. **Errors:** If mic or model is missing, a clear error message appears (no silent failure).

## INPUT/PREREQUISITE PROVENANCE

- **Generated during this feature:** Fixture audio for tests (generated in tests). Example config `vox.toml.example` is planned for Phase 4 (not added yet).
- **Pre-existing / external:** faster-whisper model: auto-download from Hugging Face on first use, or load from local path; refresh: delete cache or set path. Microphone: user must have input device; list via `vox devices`.

---

## MVP COMPLETENESS MAPPING (PRD → Plan)

This mapping is the “no gaps” checklist. Each PRD MVP requirement must map to:
- concrete code locations (files/modules)
- concrete user surface (CLI command / behavior)
- concrete verification (tests and/or manual steps)

| Status | PRD MVP requirement | Implementation mapping (code → surface → verification) |
|--------|---------------------|---------------------------------------------------------|
| **Pending** | **Push-to-talk (hold or toggle key)** | **Code:** `src/vox/hotkey/` (TBD), `src/vox/cli.py` `vox run` loop (TBD) → **Surface:** `vox run` starts listener; press/hold/release hotkey triggers capture/transcribe/inject → **Verify:** manual hotkey cycle + integration test with mocked hotkey/capture |
| **Completed (Phase 1)** | **Local speech capture (default or configured mic)** | **Code:** `src/vox/capture/stream.py` (`list_devices`, `record_seconds`, `play_back`) + `src/vox/config.py` (`device_id`) → **Surface:** `vox devices`, `vox test-mic --device ...` → **Verify:** unit tests `tests/unit/test_capture.py`; manual `vox test-mic` playback |
| **Completed (Phase 2)** | **Local transcription with faster-whisper** | **Code:** `src/vox/transcribe/faster_whisper_backend.py` (`load_model`, `transcribe`) + `src/vox/transcribe/exceptions.py` (`TranscriptionError`) → **Surface:** `vox test-mic` prints transcription → **Verify:** unit/integration tests `tests/unit/test_transcribe.py`, `tests/integration/test_capture_transcribe.py` |
| **Pending** | **Text injection: clipboard (minimum)** | **Code:** `src/vox/inject/clipboard.py` (TBD) → **Surface:** `vox run` puts transcription on clipboard → **Verify:** integration test with mocked clipboard + manual paste |
| **Pending** | **Text injection: optional paste/type into focused window** | **Code:** `src/vox/inject/keystroke.py` (optional, TBD) + config `injection_mode` → **Surface:** optional paste/type after clipboard set → **Verify:** manual only (OS permissions), plus unit test with mocks |
| **Pending** | **Global hotkey, always-available** | **Code:** `src/vox/hotkey/register.py` (TBD) → **Surface:** hotkey works regardless of terminal focus → **Verify:** manual |
| **Partial** | **CLI: `vox run`, `vox devices`, `vox test-mic`** | **Code:** `src/vox/cli.py` has `devices` + `test-mic`; `run` is TBD → **Surface:** `vox devices` + `vox test-mic` work; `vox run` pending → **Verify:** `just test quality` passes; manual `vox devices`/`vox test-mic` |
| **Completed (Phase 1+)** | **Config from file and/or env; no silent fallbacks** | **Code:** `src/vox/config.py` (`load_config`, `validate_config`, `ConfigError`) + env override map → **Surface:** env vars override file; missing hotkey fails fast → **Verify:** unit tests `tests/unit/test_config.py` |
| **Partial** | **Clear, actionable errors (mic, model, injection)** | **Code:** `ConfigError` and `TranscriptionError` exist; injection/hotkey errors TBD → **Surface:** CLI prints actionable message for config/transcribe failures → **Verify:** unit tests cover config errors; manual for model load failures |
| **Completed (Phase 1)** | **Python 3.12+, uv, `src/vox` layout** | **Code:** `pyproject.toml`, `src/vox/*` package layout → **Surface:** `uv run vox ...` works → **Verify:** `just test quality` |
| **Completed (ongoing gate)** | **Quality gates: `just test quality`** | **Code:** `justfile` targets + tool config in `pyproject.toml` → **Surface:** single command gate → **Verify:** `just test quality` passes (includes strict pytest-drill-sergeant rules) |
| **Partial** | **README and config example** | **Code:** `README.md` exists; `vox.toml.example` still pending → **Surface:** new user docs are usable but missing copy-paste config example → **Verify:** follow README; add example in Phase 4 |
| **Completed (for existing commands)** | **Rich CLI output (tables/panels); no raw JSON default** | **Code:** `src/vox/cli.py` uses Rich for `vox devices` output → **Surface:** Rich device table → **Verify:** manual `vox devices` |

**Plan completion ⇒ entire MVP ready to use** (push-to-talk loop + injection + `vox run` + example config).

## ACCEPTANCE CRITERIA

- [ ] All PRD MVP in-scope items implemented: push-to-talk, local capture, faster-whisper transcription, clipboard injection, optional keystroke injection, global hotkey, config from file/env, CLI `vox run` / `vox devices` / `vox test-mic`.
- [ ] `just test quality` passes with no unresolved warnings (or documented with rationale).
- [ ] Unit tests for config, capture, transcribe, inject; integration tests for capture→transcribe and capture→transcribe→inject.
- [ ] README and config example enable a new user to install, configure, and run push-to-talk successfully.
- [ ] Definition of Visible Done is testable by a human (steps above).
- [ ] No silent fallbacks for required config or device; errors are actionable.
- [ ] Rich output for `vox devices` (and any list/status); no raw JSON as default.

---

## COMPLETION CHECKLIST

- [ ] All tasks in Phases 1–4 completed in order.
- [ ] Each task validation passed when run.
- [ ] `just test quality` passes.
- [ ] Manual test: `vox run` + hotkey + speak + release → text in clipboard (and optionally in field).
- [ ] README and vox.toml.example in place; Definition of Visible Done verified.
- [ ] Acceptance criteria all met; MVP ready to use.

---

## EXECUTION REPORT

### Phase 1: Foundation and capture — Completed 2026-03-17

**Branch:** `feat/001-push-to-talk` (created from main).

**Commands run and outcomes:**
- `just test quality` — passed (pytest, ruff format/lint, mypy, xenon, vulture, darglint, pip-audit, bandit, radon, pylint duplicate-code, docstr-coverage).
- `uv run vox devices` — exit 0; Rich table of audio input devices printed.
- `uv run vox test-mic --seconds 1` — exit 0; recorded then played back; "Done." printed.

**Files created:**
- `src/vox/__init__.py`, `src/vox/cli.py`, `src/vox/config.py`
- `src/vox/capture/__init__.py`, `src/vox/capture/stream.py`
- `src/vox/transcribe/__init__.py`, `src/vox/inject/__init__.py`, `src/vox/hotkey/__init__.py`
- `tests/__init__.py`, `tests/unit/__init__.py`, `tests/unit/test_config.py`, `tests/unit/test_capture.py`
- `scripts/.gitkeep`

**Files modified:**
- `pyproject.toml` — dependencies (numpy, sounddevice, rich, typer), `[project.scripts]` vox = "vox.cli:main"

**Intent lock / acceptance gates:**
- Package `src/vox` exists and builds with uv.
- Config load fails with field-specific error when hotkey missing (unit test).
- `vox devices` prints Rich table of devices.
- `vox test-mic --seconds 2` (or 1) records then plays back; no transcription.

**Notes:**
- sounddevice has no py.typed; one `# type: ignore[import-untyped]` in `capture/stream.py` with inline rationale.

### Phase 2: Local transcription (faster-whisper) — Completed 2026-03-17

**Branch:** `feat/001-push-to-talk` (unchanged).

**Commands run and outcomes:**
- `just test quality` — passed.
- `vox test-mic --seconds 3` — capture → play back → transcribe and print text (model from config or defaults base/float32).

**Files created:**
- `src/vox/transcribe/faster_whisper_backend.py` — load_model(), transcribe(audio path | ndarray) → str; tiny/base/small etc., CPU/CUDA, float32/int8.
- `tests/integration/__init__.py`, `tests/integration/test_capture_transcribe.py`
- `tests/unit/test_transcribe.py` — unit tests (silent audio, 2d array, load_model) + integration (capture → transcribe).

**Files modified:**
- `pyproject.toml` — dependency `faster-whisper>=1.0.0,<2`.
- `src/vox/transcribe/__init__.py` — export load_model, transcribe.
- `src/vox/cli.py` — test-mic: after play_back, load config (or defaults), call transcribe(samples), print "Transcription:" or "(no speech detected)"; README.
- `README.md` — Install, Commands, Configuration, Transcription model (first run download, CPU int8, GPU CUDA/cuDNN).

**Intent lock / acceptance gates:**
- Unit test: fixture/silent audio → transcribe → string (empty allowed).
- Integration: capture → transcribe → string.
- `vox test-mic --seconds 3` runs capture → play back → transcribe and prints text.
- README documents model download, GPU/CPU, int8.

**Notes:**
- test-mic uses get_config() for model_size/compute_type; on ValueError (no config) uses defaults base/float32 so test-mic works without ~/.vox/vox.toml.
- Transcribe tests marked @pytest.mark.slow (load real tiny model).

### Post-Phase 2 hardening (quality gates + custom errors) — Completed 2026-03-17

This work tightened “no silent failures” and raised test quality standards.

**What changed:**
- Added **domain exceptions**:
  - `src/vox/config.py`: `ConfigError` wraps config validation failures (still a `ValueError` subtype).
  - `src/vox/transcribe/exceptions.py`: `TranscriptionError` wraps model-load/inference failures.
- Enabled **pytest-drill-sergeant** in strict mode (AAA + marker enforcement) and updated tests to comply.

**Commands run and outcomes:**
- `just test quality` — passed with `pytest-drill-sergeant` enabled.

---

## NOTES

- **Library choices:** sounddevice (cross-platform, simple; supports both input and output streams for record and play-back); pyperclip (clipboard); pynput (hotkey + optional keyboard injection). If pynput global hotkey is problematic on a target OS, document and consider platform-specific fallback in a follow-up.
- **test-mic play-back:** `vox test-mic` must play back the recorded audio after capture so the user can verify mic and level before relying on transcription; order is record → play back → (Phase 2+) transcribe and print.
- **faster-whisper:** Pin major version in pyproject; document GPU (CUDA 12 / cuDNN 9) and CPU/int8 in README. Model sizes: default `tiny` or `base` for speed; user can set `large-v3` etc. in config.
- **Hatch build:** If `uv run` fails with "Unable to determine which files to ship," ensure `src/vox` exists and `[tool.hatchling.build] packages = ["src/vox"]` (or equivalent for your hatch version) is set.
- **Commit policy:** Commit at end of each phase per RULES.md; separate commits for UX polish and docs if desired.
