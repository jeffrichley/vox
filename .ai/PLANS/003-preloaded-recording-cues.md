# Feature: Preloaded Recording Cues

The following plan should be complete, but it is important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Add audible start/stop recording cues for push-to-talk. Vox should preload the cue audio into memory during application startup so the first hotkey press does not stall on disk I/O or decode work. When the user presses the configured hotkey, Vox plays the start cue and begins recording. When the user releases the hotkey, Vox signals recording stop and then plays the end cue while the existing transcription/injection pipeline continues.

This is a user-visible UX enhancement for the active push-to-talk runtime only. It does not change transcription, injection, `vox devices`, or `vox test-mic`.

## User Story

As a Vox user
I want audible cues when recording starts and stops
So that I get immediate feedback that push-to-talk engaged and disengaged without looking at the terminal or tray/window

## Problem Statement

The current push-to-talk loop has no audible confirmation. Users must infer recording state from timing, the GUI surface, or trial and error. That creates uncertainty, especially when the hotkey is global and the terminal may not be in focus. The user specifically wants the cue assets loaded into memory at application startup to avoid first-use lag.

## Solution Statement

Introduce a small cue playback service that:

1. Loads packaged `start` and `end` cue assets from the Vox package at startup.
2. Decodes them once into NumPy arrays plus sample-rate metadata.
3. Exposes non-blocking `play_start()` and `play_end()` operations.
4. Wires startup preload into `handle_run()`.
5. Wires cue playback into the hotkey press/release lifecycle in `vox.hotkey.register`.

The implementation should keep the current lazy-import and headless-safe patterns. Missing/undecodable packaged cue assets should fail fast during startup with an actionable error. Playback failures at hotkey time should not block recording; they should surface as clear runtime warnings.

## Feature Metadata

**Feature Type**: Enhancement  
**Estimated Complexity**: Medium  
**Primary Systems Affected**: `vox.commands`, `vox.hotkey.register`, audio playback/runtime packaging, tests, docs  
**Dependencies**: `sounddevice`, `numpy`, package resources, direct `av` dependency for MP3 decode at preload time

## Traceability Mapping (Required When Applicable)

No SI/DEBT mapping for this feature.

## Branch Setup (Required)

Branch naming follows the plan filename:
- Plan: `.ai/PLANS/003-preloaded-recording-cues.md`
- Branch: `feat/003-preloaded-recording-cues`

Commands (PowerShell):

```powershell
$planFile = ".ai/PLANS/003-preloaded-recording-cues.md"
$planSlug = [System.IO.Path]::GetFileNameWithoutExtension($planFile)
$branchName = "feat/$planSlug"
git show-ref --verify --quiet "refs/heads/$branchName"
if ($LASTEXITCODE -eq 0) {
    git switch $branchName
} else {
    git switch -c $branchName
}
```

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/vox/commands.py:124` - Current `handle_run()` startup flow; model loading, runtime panel, and hotkey loop entry point.
- `src/vox/commands.py:156` - Existing nested `on_audio()` callback pattern and console error handling conventions.
- `src/vox/hotkey/register.py:116` - `_PushToTalkSession` owns press/release timing and is the right place to trigger cues without changing CLI/UI code paths.
- `src/vox/hotkey/register.py:169` - `_on_press()` is where recording starts today.
- `src/vox/hotkey/register.py:195` - `_on_release()` is where stop is signaled today; this is the accepted insertion point for the stop cue after stop is signaled.
- `src/vox/capture/stream.py:132` - `play_back()` already uses `sounddevice.play()` with NumPy arrays; reuse this playback surface rather than inventing a second audio backend.
- `tests/unit/test_commands.py:127` - Existing `handle_run()` tests capture callbacks and validate orchestration through mocks.
- `tests/unit/test_commands.py:323` - Existing command tests verify branching behavior by config mode and console messaging.
- `tests/unit/test_hotkey.py:21` - Existing hotkey tests mock the listener and runtime loop; extend this style for cue trigger assertions.
- `README.md:39` - Configuration and runtime docs surface for user-visible behavior updates.
- `README.md:70` - Existing Definition of Visible Done section that must be extended for cue audibility.
- `vox.toml.example:1` - Example config file; likely no new keys in this phase, but comments may need to mention default cues if surfaced in docs only.
- `pyproject.toml:20` - Runtime dependencies and packaging surface; if cue decoding uses `av` directly, declare it here instead of relying on transitive installation.

### New Files to Create

- `src/vox/audio_cues.py` - Cue preload/decode/cache/play service for start/end recording sounds.
- `tests/unit/test_audio_cues.py` - Unit tests for preload, decode, caching, playback dispatch, and actionable failures.
- `src/vox/assets/start.mp3` - Packaged start cue copied from the active media asset source.
- `src/vox/assets/end.mp3` - Packaged end cue copied from the active media asset source.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [python-sounddevice API overview](https://python-sounddevice.readthedocs.io/en/0.4.6/api/index.html)
  - Specific section: convenience functions using NumPy arrays (`play()`, `wait()`)
  - Why: Confirms the project’s existing playback approach is compatible with predecoded NumPy buffers.
- [PyAV documentation](https://pyav.org/docs/stable/)
  - Specific section: container/frame decode overview
  - Why: Guides direct MP3 decoding into in-memory audio frames at startup.
- [PyAV input container decode API](https://pyav.org/docs/6.2.0/api/container.html#input-containers)
  - Specific section: `InputContainer.decode(...)`
  - Why: Needed for deterministic decode of packaged MP3 cue assets into PCM arrays.
- [Python `importlib.resources` docs](https://docs.python.org/3/library/importlib.resources.html)
  - Specific section: `files()`
  - Why: Matches the project’s package-resource loading pattern already used for the tray icon.

### Patterns to Follow

**Naming Conventions:**

- Runtime modules use concise snake_case names such as `config.py`, `commands.py`, and `faster_whisper_backend.py`.
- Public helpers are re-exported from package `__init__` files only when they represent a stable surface.

**Error Handling:**

- `vox.cli` and `vox.commands` print actionable Rich messages and either exit or return early; see `src/vox/commands.py:162` and `src/vox/commands.py:178`.
- `config.py` distinguishes required startup validation errors from optional/defaulted settings; mirror that explicitness for cue preload failures.

**Lazy Import / Headless Safety:**

- `src/vox/capture/stream.py:37` lazily imports `sounddevice`.
- `src/vox/cli.py` lazily imports GUI and transcription surfaces to keep `vox --help` safe in headless environments.
- New cue code must not eagerly import heavy media/audio subsystems at module import time if that would regress help/packaging safety.

**Threading Pattern:**

- `_PushToTalkSession` uses a listener thread plus a processor queue; avoid blocking the key listener path.
- Cue playback should run in a lightweight background thread or via `sounddevice.play(..., blocking=False)` plus no immediate `wait()`.

**Package Resource Pattern:**

- `src/vox/gui/tray.py` loads `vox_icon.png` from package resources with `importlib.resources.files("vox.gui")`.
- Mirror that approach for cue assets under a package-local resource directory inside `src/vox`.

**Anti-Patterns to Avoid:**

- Do not read `media/audio/*` directly at runtime; those assets are not the packaged runtime surface.
- Do not rely on transitive dependencies for a direct feature contract if the module is imported explicitly by Vox code.
- Do not block hotkey press/release on synchronous file decode or `sd.wait()`.
- Do not add user config for custom cue files in this phase.

---

## IMPLEMENTATION PLAN

Use markdown checkboxes (`- [ ]`) for implementation phases and task bullets so execution progress can be tracked live.

## Plan Patch

### 2026-03-20: Configurable Cue Volume

- **Reason:** after live validation, the default cue playback is too loud; the runtime needs a user-configurable cue volume rather than a fixed full-scale playback level.
- **Scope add:** introduce optional `cue_volume` config and `VOX_CUE_VOLUME` env override, validated as a bounded float and applied only to start/end recording cues.
- **Default behavior change:** default cue playback volume becomes `0.5` so fresh installs and unchanged configs play cues at 50% of the previous level.
- **Non-goals:** no custom cue files, no separate start/end volumes, no change to mic capture/transcription levels, and no change to `vox devices` / `vox test-mic`.
- **Required updates:** `src/vox/config.py`, `src/vox/audio_cues.py`, `src/vox/commands.py`, `tests/unit/test_config.py`, `tests/unit/test_audio_cues.py`, `tests/unit/test_commands.py`, `README.md`, `vox.toml.example`, `docs/dev/status.md`.
- **Required gates:** `just lint`, `just format-check`, `just types`, `uv run pytest tests/unit/test_config.py -q`, `uv run pytest tests/unit/test_audio_cues.py -q`, `uv run pytest tests/unit/test_commands.py -q`, `just docs-check`, `just status`, `just quality && just test`.

### Phase 1: Cue Service Foundation

Create the packaged cue loading and playback service, including asset placement, decode logic, cache lifecycle, and startup validation surface.

#### Intent Lock

- **Source of truth:** this plan; `src/vox/capture/stream.py:132`; `pyproject.toml:20`; Python `importlib.resources` docs; PyAV decode docs.
- **Must:** preload both cues into memory at startup; store decoded PCM arrays plus sample rate; use packaged assets inside `src/vox`; expose a small API suitable for runtime orchestration.
- **Must Not:** decode on first hotkey event; read from `media/audio` at runtime; silently swallow missing asset/decode failures; add user-configurable cue file paths in this phase.
- **Acceptance criteria:**
  - packaged `start` and `end` cue assets exist under `src/vox/assets/`
  - cue preload returns decoded float32 PCM buffers with sample-rate metadata for both cues
  - preload fails fast with an actionable startup exception when a packaged cue asset is missing or undecodable
  - the cue service API is narrow, testable, and usable by runtime orchestration without touching hotkey code yet
- **Non-goals:**
  - hotkey press/release wiring
  - changes to transcription, injection, `vox devices`, or `vox test-mic`
  - user-configurable cue assets or cue-related settings
- **Provenance map:**
  - Cue asset bytes -> packaged resources under `src/vox/assets/`
  - Decoded playback buffers -> `audio_cues` cache created during startup preload
  - Playback backend -> existing `sounddevice` NumPy-array flow
- **Acceptance gates:** unit tests for preload/decode/cache pass; `uv run python -c "from vox.audio_cues import preload_default_cues"` succeeds; `just lint`, `just types`.

- [x] Add packaged cue asset files under `src/vox/assets/`, sourced from the existing repository media cues.
- [x] Add a new `src/vox/audio_cues.py` module that loads assets via `importlib.resources`.
- [x] Add decode logic that uses PyAV to read MP3 files into float32 NumPy arrays suitable for `sounddevice`.
- [x] Add an in-memory cache object or small service class for `start` and `end` cues plus sample rates.
- [x] Add explicit startup exceptions for missing/invalid packaged cue assets.
- [x] Decide and document whether playback API is class-based or module-level singleton; keep it minimal and testable.

### Phase 2: Runtime Integration

Wire the preloaded cue service into startup and hotkey press/release behavior without blocking the listener or transcription pipeline.

#### Intent Lock

- **Source of truth:** this plan; `src/vox/commands.py:124`; `src/vox/hotkey/register.py:169`; `src/vox/hotkey/register.py:195`.
- **Must:** preload cues during app startup before entering the hotkey loop; play start cue on hotkey press before recording begins; on release, signal stop first and then play the end cue; keep listener responsive.
- **Must Not:** delay first hotkey interaction on disk access; block `_on_press()` or `_on_release()` on `wait()`; change `vox devices` or `vox test-mic` behavior.
- **Acceptance criteria:**
  - `handle_run()` preloads default cues before `_run_push_to_talk_loop()` is invoked
  - valid hotkey press triggers the start cue immediately before the recording thread starts
  - valid hotkey release signals recording stop before the end cue callback fires
  - cue playback failures surface as clear runtime warnings without aborting capture/transcribe flow
  - existing GUI wrappers continue to call `handle_run()` without API changes
- **Non-goals:**
  - changing CLI command surfaces or config schema
  - adding synchronous playback waits in the hotkey path
  - modifying `vox devices` or `vox test-mic`
- **Provenance map:**
  - Startup preload trigger -> `handle_run()`
  - Start cue trigger -> `_PushToTalkSession._on_press()`
  - End cue trigger -> `_PushToTalkSession._on_release()` after `self.stop_event.set()`
  - Runtime warning surface -> existing Rich console print pattern from command layer or injected warning callback
- **Acceptance gates:** `handle_run()` tests verify preload before loop handoff; hotkey tests verify start on press and end on release after stop signal; no regression in existing run loop tests.

- [x] Update `handle_run()` to preload cues once during startup before the hotkey loop is invoked.
- [x] Extend hotkey runtime wiring so `_PushToTalkSession` accepts cue callbacks or a cue service dependency without hard-coding global state.
- [x] Trigger start cue immediately before the recording thread starts.
- [x] Trigger end cue immediately after `self.stop_event.set()` on release and before queue processing continues.
- [x] Add runtime warning behavior for playback failures that should not abort capture/transcription.
- [x] Keep API changes narrow enough that GUI wrappers (`stop_window`, `tray`) continue to call `handle_run()` unchanged.

### Phase 3: Testing, Packaging, and Documentation

Cover the new behavior with unit tests, make packaging explicit, and document the audible UX in README and status surfaces.

#### Intent Lock

- **Source of truth:** this plan; `tests/unit/test_commands.py:127`; `tests/unit/test_hotkey.py:21`; `README.md:52`; `README.md:70`; `docs/dev/status.md:7`.
- **Must:** add dedicated unit coverage for cue preload and trigger ordering; update user-facing docs; ensure package metadata supports runtime cue loading; run the repository quality gates.
- **Must Not:** ship undocumented cue behavior; leave asset packaging implicit if the build would omit them; regress existing CLI tests.
- **Acceptance criteria:**
  - dedicated unit tests cover cue preload success/failure, playback dispatch, and press/release trigger ordering
  - packaging metadata and runtime resource loading are explicit enough for packaged builds to load cue assets reliably
  - README and status docs describe audible recording cues and the final validation gate as `just quality && just test`
  - targeted tests and the repo final gate pass
- **Non-goals:**
  - introducing new integration-only test infrastructure for cue playback audio hardware
  - expanding the feature beyond documentation, packaging, and automated coverage required for this UX enhancement
  - changing unrelated CLI behavior or existing integration-test semantics
- **Provenance map:**
  - Test evidence -> new `tests/unit/test_audio_cues.py` plus updated command/hotkey tests
  - User-visible docs -> `README.md`, `docs/dev/status.md`
  - Package/runtime asset contract -> packaged files inside `src/vox`
- **Acceptance gates:** targeted tests pass; `just quality && just test` passes; manual run confirms audible cues on both first and later hotkey cycles.

- [x] Add `tests/unit/test_audio_cues.py` for preload success/failure and playback dispatch.
- [x] Update `tests/unit/test_commands.py` to assert cue preload occurs before `_run_push_to_talk_loop`.
- [x] Update `tests/unit/test_hotkey.py` to assert press/release cue callbacks fire in the intended order.
- [x] Update `pyproject.toml` if a direct `av` dependency or package-data inclusion needs to be made explicit.
- [x] Update `README.md` command/runtime behavior and visible-done steps to mention audible recording cues.
- [x] Update `docs/dev/status.md` with the new feature once implemented.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

1. **CREATE** `src/vox/assets/start.mp3` and `src/vox/assets/end.mp3`
   - **IMPLEMENT**: Copy the existing repository cue assets into the packaged runtime tree under `src/vox`.
   - **PATTERN**: Mirror package-local binary resource placement from `src/vox/gui/vox_icon.png`.
   - **IMPORTS**: None.
   - **GOTCHA**: Do not leave runtime code pointed at `media/audio/start.mp3` or `media/audio/end.mp3`.
   - **VALIDATE**: `uv run python -c "from importlib.resources import files; print((files('vox') / 'assets' / 'start.mp3').is_file())"`

2. **UPDATE** `pyproject.toml`
   - **IMPLEMENT**: Add direct runtime dependency on `av` if cue decode imports `av` directly; document rationale in the change/plan execution report. Confirm packaged asset inclusion remains valid under hatchling.
   - **PATTERN**: Follow existing dependency declaration style in `pyproject.toml:20`.
   - **IMPORTS**: `av>=...` only if used directly.
   - **GOTCHA**: Do not rely on `faster-whisper` to keep `av` transitively installed forever.
   - **VALIDATE**: `uv lock`; `uv run python -c "import av; print(av.__version__)"`

3. **CREATE** `src/vox/audio_cues.py`
   - **IMPLEMENT**: Add a small service that loads packaged cue assets, decodes them to float32 NumPy arrays, stores sample-rate metadata, and exposes preload/play methods for start/end cues.
   - **PATTERN**: Keep imports lazy/safe where possible, similar to `src/vox/capture/stream.py:37`.
   - **IMPORTS**: `numpy`, `importlib.resources`, `threading`, and `av` if chosen.
   - **GOTCHA**: Separate startup preload errors from runtime playback warnings.
   - **VALIDATE**: `uv run python -c "from vox.audio_cues import preload_default_cues; preload_default_cues(); print('ok')"`

4. **MIRROR** playback behavior from `src/vox/capture/stream.py`
   - **IMPLEMENT**: Reuse `sounddevice.play()`-compatible NumPy arrays for cue playback; avoid blocking with `wait()` in the hotkey path.
   - **PATTERN**: `src/vox/capture/stream.py:132`
   - **IMPORTS**: Prefer calling a shared playback helper or a narrowly scoped non-blocking variant.
   - **GOTCHA**: If you refactor capture playback helpers, do not break `vox test-mic` semantics that intentionally wait for playback completion.
   - **VALIDATE**: `uv run pytest tests/unit/test_audio_cues.py -q`

5. **UPDATE** `src/vox/commands.py`
   - **IMPLEMENT**: Preload default cues during `handle_run()` startup before `_run_push_to_talk_loop()` is called; pass cue callbacks/service into the hotkey loop.
   - **PATTERN**: Startup orchestration in `src/vox/commands.py:139`
   - **IMPORTS**: Cue preload/play API only in the runtime path.
   - **GOTCHA**: `vox devices` and `vox test-mic` should remain unchanged.
   - **VALIDATE**: `uv run pytest tests/unit/test_commands.py -q`

6. **UPDATE** `src/vox/hotkey/register.py`
   - **IMPLEMENT**: Extend `_PushToTalkSession` and `run_push_to_talk_loop()` to accept optional `on_recording_start` and `on_recording_stop` callbacks. Invoke start before `recording_thread.start()`. Invoke stop after `self.stop_event.set()`.
   - **PATTERN**: Existing callback injection style in `run_push_to_talk_loop(...)` and `_PushToTalkSession`.
   - **IMPORTS**: `Callable` only; keep the hotkey layer agnostic of concrete cue implementation.
   - **GOTCHA**: Do not fire cues for unrelated key presses or modifier-only events.
   - **VALIDATE**: `uv run pytest tests/unit/test_hotkey.py -q`

7. **CREATE** `tests/unit/test_audio_cues.py`
   - **IMPLEMENT**: Cover package-resource loading, decode/caching success, startup failure on missing asset/decode error, and non-blocking playback dispatch behavior.
   - **PATTERN**: Mock-heavy unit style from `tests/unit/test_commands.py`.
   - **IMPORTS**: `pytest`, `unittest.mock`, `numpy`.
   - **GOTCHA**: Keep tests deterministic; do not require a real output device.
   - **VALIDATE**: `uv run pytest tests/unit/test_audio_cues.py -q`

8. **UPDATE** `tests/unit/test_commands.py`
   - **IMPLEMENT**: Assert startup preload happens before hotkey loop handoff and that cue service wiring is present in `handle_run()`.
   - **PATTERN**: Callback capture and orchestration assertions in `tests/unit/test_commands.py:131`
   - **IMPORTS**: Existing test scaffolding only.
   - **GOTCHA**: Preserve current tests for clipboard/paste/type branches.
   - **VALIDATE**: `uv run pytest tests/unit/test_commands.py -q`

9. **UPDATE** `tests/unit/test_hotkey.py`
   - **IMPLEMENT**: Add assertions that the start callback fires on valid press and that the stop callback fires after stop is signaled on release.
   - **PATTERN**: Listener mocking in `tests/unit/test_hotkey.py:25`
   - **IMPORTS**: Existing `keyboard` and `mock` test setup.
   - **GOTCHA**: Callback order matters; avoid tests that only assert call count.
   - **VALIDATE**: `uv run pytest tests/unit/test_hotkey.py -q`

10. **UPDATE** `README.md`
    - **IMPLEMENT**: Document audible start/stop cues in the command description and visible-done steps.
    - **PATTERN**: User-facing runtime behavior bullets in `README.md:52`
    - **IMPORTS**: None.
    - **GOTCHA**: Also correct the repo-rule mismatch and use the final gate wording `just quality && just test`.
    - **VALIDATE**: `rg -n "cue|quality && just test|audible" README.md`

11. **UPDATE** `docs/dev/status.md`
    - **IMPLEMENT**: Add the feature to current/recently-completed status after implementation and append diary evidence.
    - **PATTERN**: Existing diary entry format in `docs/dev/status.md:23`
    - **IMPORTS**: None.
    - **GOTCHA**: Keep status concise and user-visible.
    - **VALIDATE**: `Get-Content docs\\dev\\status.md`

12. **VALIDATE** repository gates
    - **IMPLEMENT**: Run targeted tests during implementation, then the repo final gate.
    - **PATTERN**: `.ai/RULES.md` required quality gates.
    - **IMPORTS**: None.
    - **GOTCHA**: Resolve warnings where feasible; document any accepted residual warning with rationale.
    - **VALIDATE**: `just quality && just test`

---

## TESTING STRATEGY

### Unit Tests

- Add focused tests for cue preload and decoding without requiring actual audio hardware.
- Mock package-resource reads and `av.open()`/decode results to verify normalization to float32 arrays.
- Mock playback dispatch so tests verify invocation and ordering, not audible output.
- Extend `handle_run()` tests to prove preload occurs before `_run_push_to_talk_loop()`.
- Extend hotkey tests to prove:
  - unrelated keys do not trigger cues
  - valid press triggers start cue once
  - valid release signals stop and then triggers end cue

### Integration Tests

- No new dedicated integration test is required for this phase if unit coverage proves orchestration and manual validation covers audible output.
- Existing integration tests for capture/transcribe/inject should remain unchanged and continue passing.

### Edge Cases

- Missing packaged cue file.
- Decode failure for packaged MP3.
- Playback error on systems with no usable output device.
- Rapid repeated hotkey taps.
- Empty recording where the end cue still plays but transcription yields no speech.
- Stop event from tray/stop window without any hotkey action should not trigger cues.

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and correct feature behavior.

### Level 1: Syntax & Style

- `just lint`
- `just format-check`
- `just types`

### Level 2: Unit Tests

- `uv run pytest tests/unit/test_audio_cues.py -q`
- `uv run pytest tests/unit/test_commands.py -q`
- `uv run pytest tests/unit/test_hotkey.py -q`

### Level 3: Integration Tests

- `uv run pytest tests/integration -q`

### Level 4: Manual Validation

- `uv run vox`
- Press and hold the configured hotkey once immediately after startup: confirm the start cue is audible with no first-use lag.
- Release the hotkey: confirm the end cue is audible after release and before/while transcription proceeds.
- Repeat the cycle multiple times: confirm cue timing stays consistent.
- Switch to tray mode (`VOX_TRAY=1` or config) and verify cues behave the same.

### Level 5: Final Gate

- `just quality && just test`

For user-visible behavior, verify the application surface directly rather than relying only on mocks.

---

## OUTPUT CONTRACT (Required For User-Visible Features)

- Exact output artifacts/surfaces:
  - `vox` / `vox run` push-to-talk runtime
  - Packaged cue assets under `src/vox/assets/`
  - Audible start cue on valid hotkey press
  - Audible end cue on valid hotkey release after recording stop is signaled
- Verification commands:
  - `uv run python -c "from importlib.resources import files; print((files('vox') / 'assets' / 'start.mp3').is_file(), (files('vox') / 'assets' / 'end.mp3').is_file())"`
  - `uv run vox`
  - `just quality && just test`

## DEFINITION OF VISIBLE DONE (Required For User-Visible Features)

- A human can directly verify completion by:
  - running `uv run vox`
  - pressing the configured hotkey immediately after startup and hearing the start cue with no noticeable first-use delay
  - releasing the hotkey and hearing the end cue as recording ends
  - repeating the hotkey cycle and confirming transcription/injection still behaves as before

## INPUT/PREREQUISITE PROVENANCE (Required When Applicable)

- Pre-existing dependency:
  - `media/audio/start.mp3` copied into packaged runtime asset path during implementation
  - `media/audio/end.mp3` copied into packaged runtime asset path during implementation
- Pre-existing dependency:
  - `sounddevice` playback surface already in repo via `src/vox/capture/stream.py`
- Planned direct dependency:
  - `av` decode runtime, installed via `uv sync` / `uv lock` if made direct in `pyproject.toml`

---

## ACCEPTANCE CRITERIA

- [x] Vox preloads default start/end cues into memory during application startup before entering the hotkey loop.
- [x] The first valid hotkey press after startup plays the start cue without decode/disk lag.
- [x] On hotkey release, Vox signals recording stop and then plays the end cue.
- [x] Cue playback does not block the listener or regress capture/transcribe/inject behavior.
- [x] Packaged builds/load paths use package resources, not `media/audio` runtime paths.
- [x] Missing or invalid packaged cue assets fail with a clear startup error.
- [x] Playback-device/runtime cue failures are surfaced clearly and do not silently disable the main workflow.
- [x] `vox devices` and `vox test-mic` behavior remains unchanged.
- [x] Unit tests cover preload and press/release trigger ordering.
- [x] `just quality && just test` passes.
- [x] README and status docs reflect the new audible cue behavior.

---

## COMPLETION CHECKLIST

- [x] All tasks completed in order
- [ ] Each task validation passed immediately
- [x] All validation commands executed successfully
- [x] Full test suite passes (unit + integration)
- [x] No linting or type checking errors
- [ ] Manual testing confirms audible cues work on first and repeated use
- [ ] Acceptance criteria all met
- [x] Code reviewed for quality and maintainability

---

## NOTES

- Recommended implementation path: keep the feature self-contained and dependency-light by adding one focused cue module instead of spreading media logic across capture/hotkey/CLI.
- The current repository contains `start.mp3` and `end.mp3` under `media/audio`, but those files are not part of the active packaged runtime surface. Copy them under `src/vox/assets/` for runtime use.
- If implementation reveals that direct MP3 decode is more fragile than expected on a target platform, the fallback plan is to convert the packaged cue assets to WAV and keep the same preload/play API. Do not make that switch silently; patch the plan and document the asset provenance change.
- Confidence score for one-pass execution: 8/10.

## Execution Report

### Completion Status

- Implemented all planned code, test, packaging, and documentation tasks for Phases 1-3.
- Automated validation passed, including the repo final gate `just quality && just test`.
- Manual audible validation remains pending because this session could not interact with a live desktop audio/hotkey environment.

### Phase Intent Checks Run

- Phase 1: Cue Service Foundation -> locked before implementation; acceptance gates satisfied by packaged assets, preload/decode service, and unit coverage.
- Phase 2: Runtime Integration -> locked before implementation; acceptance gates satisfied by `handle_run()` preload ordering, hotkey callback wiring, and warning-path tests.
- Phase 3: Testing, Packaging, and Documentation -> locked before implementation; acceptance gates satisfied by targeted unit tests, doc updates, and full repo gate pass.

### Commands Run And Outcomes

- `uv run python -c "from importlib.resources import files; print((files('vox') / 'assets' / 'start.mp3').is_file())"` -> initial validation blocked by local editable-script lock when `uv run` tried to resync; repeated with `uv run --no-sync ...` -> pass (`True`)
- `uv lock` -> pass
- `uv run python -c "from vox.audio_cues import preload_default_cues; preload_default_cues(); print('ok')"` -> initial validation blocked by the same local editable-script lock; repeated with `uv run --no-sync ...` -> pass (`ok`)
- `uv run --no-sync pytest tests/unit/test_audio_cues.py -q` -> pass (`7 passed`)
- `uv run --no-sync pytest tests/unit/test_commands.py -q` -> pass (`16 passed`)
- `uv run --no-sync pytest tests/unit/test_hotkey.py -q` -> pass (`11 passed`)
- `just lint` -> pass
- `just format-check` -> pass via `just quality`
- `just types` -> pass
- `just docs-check` -> pass
- `just status` -> pass
- `uv run --no-sync pytest tests/integration -q` -> pass (`2 passed`)
- `uv run --no-sync python -c "from importlib.resources import files; print((files('vox') / 'assets' / 'start.mp3').is_file(), (files('vox') / 'assets' / 'end.mp3').is_file())"` -> pass (`True True`)
- `just quality` -> pass
- `just test` -> pass (`99 passed`)
- `just quality && just test` -> pass

### Output Artifacts / Surfaces

- Packaged cue assets: `src/vox/assets/start.mp3`, `src/vox/assets/end.mp3`
- Cue preload/playback service: `src/vox/audio_cues.py`
- Runtime integration: `src/vox/commands.py`, `src/vox/hotkey/register.py`
- Test evidence: `tests/unit/test_audio_cues.py`, `tests/unit/test_commands.py`, `tests/unit/test_hotkey.py`
- User-visible docs: `README.md`, `docs/dev/status.md`

### Partial / Blocked Items

- Manual validation of audible cue playback in a live `uv run vox` session is still pending. This requires an interactive desktop session with microphone/output devices and a usable global hotkey environment.

### 2026-03-20 Follow-up: Configurable Cue Volume

- Added optional `cue_volume` config and `VOX_CUE_VOLUME` env override, validated as a bounded float in `src/vox/config.py`.
- Default cue playback volume is now `0.5`, which halves cue loudness for unchanged configs while remaining configurable.
- Applied cue scaling at playback time in `src/vox/audio_cues.py` so preload caching remains unchanged.
- Wired runtime cue callbacks to pass the configured volume through `src/vox/commands.py`.
- Updated test coverage in `tests/unit/test_config.py`, `tests/unit/test_audio_cues.py`, and `tests/unit/test_commands.py`.
- Updated docs in `README.md`, `vox.toml.example`, and `docs/dev/status.md`.
- Validation evidence:
  - `uv run --no-sync pytest tests/unit/test_config.py -q` -> pass (`30 passed`)
  - `uv run --no-sync pytest tests/unit/test_audio_cues.py -q` -> pass (`7 passed`)
  - `uv run --no-sync pytest tests/unit/test_commands.py -q` -> pass (`17 passed`)
  - `just docs-check` -> pass
  - `just status` -> pass
  - `just quality && just test` -> pass (`104 passed`)
