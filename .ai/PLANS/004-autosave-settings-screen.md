# Feature: Autosave Configuration Screen

The following plan should be complete, but it is important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Add a desktop configuration screen for Vox that lets users change core settings without editing TOML manually. The screen must autosave valid changes to the config file with no `Save` or `Cancel` buttons, while preserving the repo's current CLI-first architecture, strict validation style, and headless-safe import boundaries.

The settings screen should cover the user-facing controls already discussed:

- `Recording`: hotkey, input device, test mic
- `Transcription`: model size, compute device, compute type
- `Output`: injection mode, cue volume, test cue
- `Runtime`: use tray, restart/apply guidance

## User Story

As a Vox user
I want a desktop settings screen that persists changes automatically
So that I can tune voice-input behavior quickly without hand-editing config files or remembering TOML keys

## Problem Statement

Vox currently relies on file and environment-based configuration only. That is acceptable for early adopters, but it creates friction for common adjustments like changing cue volume, device selection, or injection mode. A settings surface is needed, but it must not behave like a heavyweight preferences app. The user explicitly does not want `Save` or `Cancel`; the screen must persist each completed valid change automatically.

The main technical constraint is that Vox is a Python CLI/runtime tool, not a general GUI app. Current GUI code is intentionally narrow and import-lazy. The system tray runs through `pystray`, while the stop window uses Tk. The settings feature therefore needs a design that keeps the existing runtime stable, avoids hidden Tk/pystray event-loop coupling, and preserves config validation guarantees.

## Solution Statement

Implement a standalone `vox settings` GUI entrypoint using Tk/ttk and autosave semantics:

- Add file-backed config persistence helpers in `src/vox/config.py`
- Keep validation centralized in the config layer
- Launch the settings window as a standalone runtime surface, not as an in-process child of the tray loop
- Wire tray and stop-window affordances to launch that standalone settings surface
- Persist each valid completed change immediately with atomic writes
- Debounce slider writes; commit text-like fields only on explicit edit completion
- Surface environment overrides in the UI so users understand when disk-backed values are being superseded

This approach fits the current architecture, avoids introducing a new GUI framework, and minimizes the risk of tray/Tk mainloop conflicts.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: High
**Primary Systems Affected**: `src/vox/config.py`, `src/vox/cli.py`, `src/vox/gui/*`, docs, unit tests
**Dependencies**: stdlib `tkinter` / `tkinter.ttk`, existing `pystray`, existing config/runtime helpers

## Traceability Mapping

No SI/DEBT mapping for this feature.

## Branch Setup

Branch naming must follow the plan filename:
- Plan: `.ai/PLANS/<NNN>-<feature>.md`
- Branch: `feat/<NNN>-<feature>`

Commands:

```bash
PLAN_FILE=".ai/PLANS/004-autosave-settings-screen.md"
PLAN_SLUG="$(basename "$PLAN_FILE" .md)"
BRANCH_NAME="feat/${PLAN_SLUG}"
git show-ref --verify --quiet "refs/heads/${BRANCH_NAME}" \
  && git switch "${BRANCH_NAME}" \
  || git switch -c "${BRANCH_NAME}"
```

PowerShell equivalent:

```powershell
$planFile = ".ai/PLANS/004-autosave-settings-screen.md"
$planSlug = [System.IO.Path]::GetFileNameWithoutExtension($planFile)
$branchName = "feat/$planSlug"
git show-ref --verify --quiet "refs/heads/$branchName"
if ($LASTEXITCODE -eq 0) {
    git switch $branchName
} else {
    git switch -c $branchName
}
```

## Plan Patch

- Added a PowerShell-safe `## Branch Setup` command block so branch setup is executable in the repository's current shell environment.

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/vox/config.py:120-223` - Config path search, TOML load, and env override precedence. Needed to separate file-backed editing from env-overridden effective config.
- `src/vox/config.py:288-414` - Validation contract and field-specific error behavior. Mirror this style for settings edits and persistence failures.
- `src/vox/config.py:515-531` - `get_config()` output contract used by runtime surfaces.
- `src/vox/cli.py:73-106` - Lazy GUI import boundary in `_run_impl()`. New settings entrypoint must preserve headless-safe CLI behavior.
- `src/vox/cli.py:125-180` - Existing Typer command registration pattern for user-facing commands.
- `src/vox/gui/stop_window.py:44-116` - Current Tk window setup and worker coordination pattern; use this as the local GUI style baseline.
- `src/vox/gui/tray.py:38-85` - Tray lifecycle and menu wiring. Important constraint: avoid mixing a long-lived Tk mainloop directly inside `pystray` callbacks.
- `src/vox/gui/__init__.py:1-9` - GUI package export boundary; update cleanly if a settings launcher/window is added.
- `tests/unit/test_cli.py:132-243` - Existing CLI error-handling tests; mirror for any `vox settings` command and launcher failures.
- `tests/unit/test_config.py:116-268` - Current config path/load/env tests; extend for file-backed write helpers and atomic persistence semantics.
- `README.md:39-77` - Public configuration and usage surface that must be updated if `vox settings` is added.
- `docs/dev/status.md:7-34` - Required status surface to sync after implementation.
- `.ai/RULES.md:8-87` - Workflow invariants, quality gates, fail-fast validation, and user-visible plan requirements.
- `.ai/REF/project-types/cli-tool.md` - CLI-tool-specific planning and validation expectations.
- `.ai/REF/status-surfaces.md` - Required docs/status surfaces to update when user-visible CLI/runtime behavior changes.

### New Files to Create

- `src/vox/gui/settings_window.py` - Standalone Tk/ttk settings UI with autosave controls and inline status feedback.
- `src/vox/gui/settings_launcher.py` - Thin launcher for opening the settings window safely from CLI/tray/stop-window contexts.
- `tests/unit/test_settings_window.py` - Unit coverage for autosave behavior, field commit rules, and status feedback orchestration.
- `tests/unit/test_settings_launcher.py` - Launcher and subprocess/dispatch coverage for tray/stop-window entrypoints.

### Existing Files Likely To Update

- `src/vox/config.py`
- `src/vox/cli.py`
- `src/vox/gui/__init__.py`
- `src/vox/gui/stop_window.py`
- `src/vox/gui/tray.py`
- `tests/unit/test_cli.py`
- `tests/unit/test_config.py`
- `README.md`
- `vox.toml.example`
- `docs/dev/status.md`

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [Tkinter](https://docs.python.org/3/library/tkinter.html)
  - Specific section: top-level windows, event loop, widget model
  - Why: Needed to keep the settings window within supported stdlib GUI patterns
- [tkinter.ttk](https://docs.python.org/3/library/tkinter.ttk.html)
  - Specific section: themed widgets, combobox, scale, notebook/frame patterns
  - Why: Use native-feeling controls without adding a new dependency
- [pystray Usage](https://pystray.readthedocs.io/en/latest/usage.html)
  - Specific section: menu callbacks and icon lifecycle
  - Why: Confirms why tray-driven settings launch should stay narrow and non-blocking
- [pystray Reference](https://pystray.readthedocs.io/en/stable/reference.html)
  - Specific section: `Icon`, menu item callback behavior
  - Why: Needed before wiring a `Settings...` action from the tray
- [tempfile](https://docs.python.org/3.14/library/tempfile.html)
  - Specific section: named temporary files
  - Why: Required for atomic config persistence
- [os.replace](https://docs.python.org/3.12/library/os.html#os.replace)
  - Specific section: atomic replacement semantics
  - Why: Use explicit replace semantics for robust config writes

### Patterns to Follow

**Naming Conventions:**

- Module and function names are snake_case: `run_stop_window`, `get_config`, `load_config`
- User-facing config keys are flat TOML-style keys, not nested GUI-specific state objects
- Error types are explicit (`ConfigError`, `TranscriptionError`) and surfaced with field-specific messages

**Error Handling:**

- Validate inputs centrally and fail fast with specific field names in the message
- Return/print user-safe errors at CLI boundaries; do not silently fall back when required contract fields are invalid
- Preserve lazy imports for GUI code so help/version/headless paths remain safe

**GUI Pattern:**

- Current GUI code is intentionally small and synchronous around Tk setup
- Keep the settings window self-contained; do not spread widget state into unrelated runtime modules
- Prefer launcher indirection over directly embedding another event loop inside tray callbacks

**Config Pattern:**

- Current `get_config()` returns effective runtime config after env overrides
- The settings screen must edit the disk-backed TOML config, not the already-overridden effective runtime dict
- Persist writes atomically and deterministically

---

## IMPLEMENTATION PLAN

Use markdown checkboxes (`- [ ]`) for implementation phases and task bullets so execution progress can be tracked live.

- [x] Phase 1: Persistent Config Foundation
- [x] Phase 2: Standalone Autosave Settings Window
- [x] Phase 3: Runtime Launch Integration
- [x] Phase 4: Tests, Docs, and Visible-Done Proof

### Phase 1: Persistent Config Foundation

Define the file-backed config editing contract that the UI will rely on. This phase creates explicit separation between:

- effective runtime config (`get_config()` / env overrides)
- persisted user config (`~/.vox/vox.toml` or `VOX_CONFIG`)

#### Intent Lock

- Source of truth:
  - `src/vox/config.py:120-223`
  - `src/vox/config.py:288-414`
  - `.ai/RULES.md:8-49`
  - [tempfile](https://docs.python.org/3.14/library/tempfile.html)
  - [os.replace](https://docs.python.org/3.12/library/os.html#os.replace)
- Must:
  - Add explicit helpers to read, validate, serialize, and atomically write file-backed config
  - Preserve current env override behavior for runtime reads
  - Validate before persistence; never write known-invalid config
  - Keep TOML output deterministic and human-editable
  - Surface env-overridden fields to callers so the UI can warn users
- Must Not:
  - Mutate `get_config()` into a GUI-specific API
  - Save env-derived values back into the file by default
  - Introduce silent fallback defaults for invalid required fields
  - Add a dependency just for TOML writing unless the plan is patched explicitly
- Provenance map:
  - File path resolution -> `src/vox/config.py:120-144`
  - Validation rules -> `src/vox/config.py:288-414`
  - Atomic write semantics -> stdlib docs above
  - User-facing error style -> existing `ConfigError` pattern
- Acceptance gates:
  - `uv run pytest tests/unit/test_config.py -q`
  - `just lint`
  - `just types`

**Acceptance Criteria:**

- File-backed config can be loaded without env overrides applied
- Valid edited config can be serialized and written atomically
- Invalid edited config is rejected before write with field-specific errors
- The UI-facing config helpers expose enough metadata to identify env-overridden fields

**Non-Goals:**

- General-purpose config migration tooling
- Arbitrary TOML round-trip preservation beyond supported Vox keys
- Changing runtime env override precedence

**Tasks:**

- [x] Add a file-backed config read helper that returns the editable TOML-sourced dict without env overrides
- [x] Add a serializer/writer pair for deterministic TOML output and atomic replace
- [x] Add a targeted update helper or equivalent flow for "validate edited dict, then write"
- [x] Add an env-override inspection helper so the UI can flag overridden fields
- [x] Extend config tests for write success, invalid write rejection, and atomic/replace behavior expectations

### Phase 2: Standalone Autosave Settings Window

Build the actual settings screen as a standalone Tk/ttk surface with autosave semantics and no save/cancel flow.

#### Intent Lock

- Source of truth:
  - `src/vox/gui/stop_window.py:44-116`
  - `src/vox/config.py:288-414`
  - [Tkinter](https://docs.python.org/3/library/tkinter.html)
  - [tkinter.ttk](https://docs.python.org/3/library/tkinter.ttk.html)
- Must:
  - Implement `Recording`, `Transcription`, `Output`, and `Runtime` sections
  - Remove `Save` and `Cancel` entirely
  - Persist each valid completed change automatically
  - Debounce slider-backed writes such as `cue_volume`
  - Commit text-like fields such as hotkey only on edit completion (`Enter`, focus loss, or explicit capture action)
  - Show inline/status feedback for `Saved`, validation errors, and restart-required changes
  - Provide `Test mic` and `Test cue` affordances without requiring the full run loop
- Must Not:
  - Persist transient invalid states on every keystroke
  - Introduce a second source of truth for validation rules
  - Require a tray session for the settings screen to function
  - Add custom cue-file selection or other out-of-scope settings
- Provenance map:
  - Widget/event style -> `src/vox/gui/stop_window.py:80-114`
  - Field validation -> `src/vox/config.py:288-414`
  - Autosave semantics -> user requirement from this conversation
  - Cue-volume and runtime fields -> current README/config surfaces
- Acceptance gates:
  - `uv run pytest tests/unit/test_settings_window.py -q`
  - `uv run pytest tests/unit/test_config.py -q`
  - `just lint`
  - `just types`

**Acceptance Criteria:**

- The settings window exposes the required `Recording`, `Transcription`, `Output`, and `Runtime` sections
- There are no `Save` or `Cancel` buttons anywhere in the flow
- Dropdown/toggle changes persist automatically after a valid selection
- Slider-backed changes debounce filesystem writes
- Text-like fields persist only after valid edit completion
- The screen shows user-visible saved/error/restart-needed feedback

**Non-Goals:**

- Arbitrary advanced preferences beyond the agreed settings list
- Custom cue file selection
- A full visual redesign of existing Vox runtime windows

**Tasks:**

- [x] Create `settings_window.py` with a narrow controller/view boundary so persistence logic is testable without a real Tk mainloop
- [x] Build grouped controls for hotkey, device, model, compute settings, injection mode, cue volume, and `use_tray`
- [x] Implement autosave orchestration:
  - immediate writes for dropdowns/toggles
  - debounced writes for slider movement
  - commit-on-finish writes for text-like fields
- [x] Add user-visible status messaging for saved/error/restart-needed states
- [x] Add UI affordances for `Restore defaults`, `Test mic`, and `Test cue`, with explicit confirmation for restore
- [x] Show warnings when env vars currently override file-backed values

### Phase 3: Runtime Launch Integration

Make the settings screen discoverable from the CLI and from existing runtime surfaces without destabilizing tray behavior.

#### Intent Lock

- Source of truth:
  - `src/vox/cli.py:73-180`
  - `src/vox/gui/tray.py:38-85`
  - `src/vox/gui/__init__.py:1-9`
  - [pystray Usage](https://pystray.readthedocs.io/en/latest/usage.html)
  - [pystray Reference](https://pystray.readthedocs.io/en/stable/reference.html)
- Must:
  - Add a standalone `vox settings` command with lazy GUI import behavior
  - Provide a launcher path usable from tray and stop-window surfaces
  - Keep tray callbacks non-blocking and operationally simple
  - If the settings window is launched from a running tray session, prefer subprocess/standalone launch over in-process nested mainloop coupling
  - Preserve current `vox`, `vox run`, `vox devices`, and `vox test-mic` behavior
- Must Not:
  - Break `vox --help` or headless import safety
  - Couple tray shutdown logic to the settings window lifecycle
  - Launch multiple competing settings writers without an explicit strategy
- Provenance map:
  - CLI command style -> `src/vox/cli.py:125-180`
  - Tray callback behavior -> `src/vox/gui/tray.py:69-85`
  - GUI export boundary -> `src/vox/gui/__init__.py:1-9`
  - Launch strategy rationale -> `pystray` docs plus current tray architecture
- Acceptance gates:
  - `uv run pytest tests/unit/test_cli.py -q`
  - `uv run pytest tests/unit/test_settings_launcher.py -q`
  - existing tray/CLI tests remain green

**Acceptance Criteria:**

- `vox settings` opens the settings screen through a lazy-import-safe CLI command
- Tray integration can launch settings without blocking or destabilizing the tray loop
- Existing `vox`, `vox run`, `vox devices`, and `vox test-mic` flows remain behaviorally unchanged
- Launcher failures surface through existing user-facing error patterns

**Non-Goals:**

- Turning Vox into a long-lived multi-window desktop app shell
- Tight in-process coupling between `pystray` and a second Tk lifecycle
- Solving multi-instance config locking beyond a clear documented strategy for this feature

**Tasks:**

- [x] Add a `vox settings` Typer command with error handling consistent with other user-facing commands
- [x] Create a settings launcher helper that can:
  - run the settings window directly in CLI mode
  - launch a detached/standalone settings process from tray or stop-window contexts
- [x] Add `Settings...` entry points to tray and stop-window surfaces if that can be done without degrading the current minimal UX
- [x] Keep launcher failure paths user-visible and test-covered

### Phase 4: Tests, Docs, and Visible-Done Proof

Finish the feature by proving the autosave workflow, documenting it, and syncing the repo status surfaces.

#### Intent Lock

- Source of truth:
  - `README.md:39-77`
  - `docs/dev/status.md:7-34`
  - `.ai/RULES.md:38-87`
  - `.ai/REF/status-surfaces.md`
  - `.ai/REF/project-types/cli-tool.md`
- Must:
  - Document how to open the settings screen and how autosave behaves
  - Update example config/doc surfaces to reflect GUI-managed settings
  - Keep final validation aligned with repo quality gates
  - Include explicit visible-done proof for the new screen and autosave behavior
- Must Not:
  - Ship a user-visible feature without README/status updates
  - Omit manual validation for GUI/runtime behavior
  - Treat warnings as acceptable without documenting them
- Provenance map:
  - Public usage copy -> `README.md`
  - Current status surface -> `docs/dev/status.md`
  - Required gates -> `.ai/RULES.md`
- Acceptance gates:
  - `just docs-check`
  - `just status`
  - `just quality && just test`

**Acceptance Criteria:**

- README documents how to open and use the autosave settings screen
- Status surfaces reflect the new user-visible capability
- Validation evidence exists for the feature-specific tests and the final repo gate
- Manual visible-done checks are documented and executable

**Non-Goals:**

- Expanding docs into a full end-user manual
- Adding hardware-dependent automated GUI tests that are unsuitable for CI

**Tasks:**

- [x] Add/extend unit tests for autosave commit behavior, env-override warnings, launcher behavior, and CLI dispatch
- [x] Update README usage/config sections with `vox settings`, autosave semantics, and restart/apply notes
- [x] Update `vox.toml.example` if any keys or comments should better align with the GUI surface
- [x] Update `docs/dev/status.md`
- [x] Append execution evidence to this plan under `## Execution Report`

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### UPDATE `src/vox/config.py`

- **IMPLEMENT**: Separate file-backed config loading from env-overridden effective config so the settings UI can read/write the persisted user config without flattening runtime overrides into disk state.
- **PATTERN**: Mirror current path resolution and validation behavior from `src/vox/config.py:120-223` and `src/vox/config.py:288-414`.
- **IMPORTS**: Use stdlib helpers only unless a plan patch explicitly approves a TOML writer dependency.
- **GOTCHA**: Python 3.12 includes `tomllib` read support but not TOML writing; implement deterministic manual serialization carefully and keep scope limited to known flat keys.
- **VALIDATE**: `uv run pytest tests/unit/test_config.py -q`

### CREATE `src/vox/gui/settings_window.py`

- **IMPLEMENT**: Build a standalone Tk/ttk settings surface with grouped sections, inline status text, restore-defaults confirmation, and autosave orchestration.
- **PATTERN**: Mirror Tk setup simplicity from `src/vox/gui/stop_window.py:80-114`.
- **IMPORTS**: Keep runtime-heavy imports local if they are only needed for test actions such as cue preview or mic test.
- **GOTCHA**: Do not persist partial invalid text-entry states; use commit-on-finish semantics.
- **VALIDATE**: `uv run pytest tests/unit/test_settings_window.py -q`

### CREATE `src/vox/gui/settings_launcher.py`

- **IMPLEMENT**: Add a narrow launcher abstraction that can open the settings window directly or via a standalone subprocess when invoked from tray/other GUI contexts.
- **PATTERN**: Keep user-facing error propagation aligned with existing CLI boundaries in `src/vox/cli.py:73-106`.
- **IMPORTS**: Prefer explicit executable resolution using `sys.executable` and module entrypoints over shell assumptions.
- **GOTCHA**: Tray callbacks should not block waiting on the settings UI to exit.
- **VALIDATE**: `uv run pytest tests/unit/test_settings_launcher.py -q`

### UPDATE `src/vox/cli.py`

- **IMPLEMENT**: Register `vox settings` with lazy GUI import behavior and user-safe error handling.
- **PATTERN**: Mirror Typer command style from `src/vox/cli.py:125-180`.
- **IMPORTS**: Keep GUI imports inside helper functions or command bodies where possible.
- **GOTCHA**: Do not regress current default `vox` behavior or `--help` safety.
- **VALIDATE**: `uv run pytest tests/unit/test_cli.py -q`

### UPDATE `src/vox/gui/tray.py`

- **IMPLEMENT**: Add a `Settings...` menu item that launches the standalone settings surface without entangling it with tray shutdown or `icon.run()`.
- **PATTERN**: Extend the current menu callback model in `src/vox/gui/tray.py:69-85`.
- **IMPORTS**: Use the launcher helper rather than importing the settings window directly.
- **GOTCHA**: Keep menu callbacks narrow and resilient; failures should be surfaced cleanly.
- **VALIDATE**: `uv run pytest tests/unit/test_settings_launcher.py -q`

### UPDATE `src/vox/gui/stop_window.py`

- **IMPLEMENT**: Add a minimal settings affordance only if it preserves the current small-window intent; otherwise document deferral in a plan patch during execution.
- **PATTERN**: Preserve the existing stop-window coordination model in `src/vox/gui/stop_window.py:44-116`.
- **IMPORTS**: Route through the launcher helper.
- **GOTCHA**: Do not complicate the stop workflow or block shutdown.
- **VALIDATE**: `uv run pytest tests/unit/test_cli.py -q`

### UPDATE Tests And Docs

- **IMPLEMENT**: Add/extend tests for config persistence, autosave commit rules, launcher behavior, and CLI dispatch. Update README, example config, and status surfaces.
- **PATTERN**: Mirror current config and CLI testing style in `tests/unit/test_config.py` and `tests/unit/test_cli.py`.
- **IMPORTS**: Use `tmp_path` and mocks; avoid hardware-dependent assertions.
- **GOTCHA**: Keep GUI tests logic-heavy and event-light so CI remains stable.
- **VALIDATE**: `just quality && just test`

---

## TESTING STRATEGY

### Unit Tests

- Extend `tests/unit/test_config.py` to cover:
  - file-backed config read without env overrides
  - deterministic serialization of known keys
  - atomic write flow using temp file + replace
  - invalid edit rejection
  - env-override detection metadata for the UI
- Add `tests/unit/test_settings_window.py` for:
  - immediate save on valid toggle/dropdown changes
  - debounced save orchestration for `cue_volume`
  - commit-on-finish behavior for hotkey edits
  - restore-defaults action
  - restart-needed / overridden-field messaging
- Add `tests/unit/test_settings_launcher.py` for:
  - direct launch mode
  - tray-safe standalone launch mode
  - failure propagation
- Extend `tests/unit/test_cli.py` for `vox settings`

### Integration Tests

- Keep existing integration suite green
- Add integration coverage only if a stable, non-interactive settings-launch smoke test is practical; otherwise document why unit coverage plus manual GUI validation is the correct boundary

### Edge Cases

- `VOX_CONFIG` points to a custom file
- env vars override values shown in the screen
- invalid hotkey edit is attempted
- slider is dragged rapidly
- config file write fails due to permissions/lock
- settings window is launched while tray/run loop is active
- restore defaults is clicked accidentally
- device list is unavailable or audio query fails

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and feature correctness.

### Level 1: Syntax & Style

- `just lint`
- `just format-check`
- `just types`

### Level 2: Unit Tests

- `uv run pytest tests/unit/test_config.py -q`
- `uv run pytest tests/unit/test_cli.py -q`
- `uv run pytest tests/unit/test_settings_window.py -q`
- `uv run pytest tests/unit/test_settings_launcher.py -q`

### Level 3: Integration Tests

- `uv run pytest tests/integration -q`

### Level 4: Manual Validation

- `uv run vox settings`
- Change `cue_volume` and confirm the config file updates without pressing Save
- Change `injection_mode` and confirm the config file updates immediately
- Edit hotkey to an invalid value and confirm it is not persisted
- Launch `vox`, then open settings from any new runtime affordance and confirm the settings window appears without disrupting stop/tray behavior
- Close and reopen the settings window; confirm saved values round-trip from disk
- Run `uv run vox --help` and confirm CLI help remains healthy

### Level 5: Final Gate

- `just docs-check`
- `just status`
- `just quality && just test`

---

## OUTPUT CONTRACT

- Exact output artifacts/surfaces:
  - `vox settings` CLI command
  - desktop settings window under `src/vox/gui/settings_window.py`
  - autosaved user config file at `~/.vox/vox.toml` or `VOX_CONFIG`
  - optional tray/stop-window `Settings...` launch affordance
  - updated docs in `README.md`, `vox.toml.example`, and `docs/dev/status.md`
- Verification commands:
  - `uv run vox settings`
  - `uv run pytest tests/unit/test_config.py tests/unit/test_settings_window.py tests/unit/test_settings_launcher.py -q`
  - `just quality && just test`

## DEFINITION OF VISIBLE DONE

- A human can directly verify completion by:
  - running `uv run vox settings`
  - seeing a desktop settings window with `Recording`, `Transcription`, `Output`, and `Runtime` sections
  - changing a valid field and observing that the TOML file updates without any `Save` action
  - attempting an invalid text-like edit and observing inline validation without bad config persistence
  - reopening the screen and seeing the persisted values restored from disk

## INPUT/PREREQUISITE PROVENANCE

- Pre-existing dependency:
  - stdlib `tkinter` / `ttk` available in the active Python runtime
  - refresh/setup command: `uv sync`
- Pre-existing dependency:
  - local desktop session capable of opening Tk windows
  - setup: run from a normal interactive OS session, not a headless CI shell
- Generated during this feature:
  - user config updates in `~/.vox/vox.toml` or the path from `VOX_CONFIG` via `vox settings`

---

## ACCEPTANCE CRITERIA

- [x] Vox exposes a `vox settings` user-facing command
- [x] The settings screen contains the required sections and controls
- [x] There are no `Save` or `Cancel` buttons
- [x] Valid completed changes persist automatically to the config file
- [x] Invalid intermediate text-entry states do not get persisted
- [x] `cue_volume` changes debounce writes while still feeling responsive
- [x] Env-overridden fields are clearly surfaced to the user
- [x] Tray/stop-window launch integration does not regress existing runtime behavior
- [x] All validation commands pass with zero errors
- [x] Documentation is updated and status surfaces are synced
- [x] Output artifacts and verification commands are present
- [x] The "Definition of Visible Done" is present and testable

---

## COMPLETION CHECKLIST

- [x] All tasks completed in order
- [x] Each task validation passed immediately
- [x] All validation commands executed successfully
- [x] Full test suite passes
- [x] No linting or type checking errors
- [x] Manual GUI validation confirms autosave works
- [x] Acceptance criteria all met
- [x] Execution report appended to this plan

## Execution Report

2026-03-20 Phase 1: Persistent Config Foundation

- Status: completed
- Phase intent check:
  - phase: `Phase 1: Persistent Config Foundation`
  - sources used: `.ai/RULES.md`, `.ai/REF/project-types/cli-tool.md`, `.ai/COMMANDS/phase-intent-check.md`, `src/vox/config.py`, `tests/unit/test_config.py`
  - locked musts: file-backed helpers without env override flattening, pre-write validation, deterministic TOML, atomic replace, env-override metadata for UI callers
  - locked must-nots: no GUI-specific `get_config()` changes, no env-derived persistence by default, no silent fallback defaults, no new TOML dependency
- Branch setup:
  - added PowerShell-safe branch setup commands to this plan
  - active branch: `feat/004-autosave-settings-screen`
- Files changed:
  - `.ai/PLANS/004-autosave-settings-screen.md`
  - `src/vox/config.py`
  - `tests/unit/test_config.py`
- Commands run:
  - `uv run pytest tests/unit/test_config.py -q` -> pass
  - `just lint` -> pass
  - `just types` -> pass
- Output artifacts:
  - file-backed config helpers in `src/vox/config.py`
  - persistence and override coverage in `tests/unit/test_config.py`
- Partial / blocked items:
  - remaining settings-window work deferred to later phases by plan scope

2026-03-20 Phase 2: Standalone Autosave Settings Window

- Status: completed
- Phase intent check:
  - phase: `Phase 2: Standalone Autosave Settings Window`
  - sources used: `.ai/RULES.md`, `.ai/COMMANDS/phase-intent-check.md`, `src/vox/gui/stop_window.py`, `src/vox/config.py`, `src/vox/commands.py`, `src/vox/audio_cues.py`, `tests/unit/test_settings_window.py`
  - locked musts: standalone Tk/ttk settings surface, no Save/Cancel flow, grouped Recording/Transcription/Output/Runtime sections, autosave rules by control type, inline saved/error/restart feedback, restore/test actions, env-override warnings
  - locked must-nots: no keystroke-by-keystroke invalid persistence, no second validation source of truth, no tray dependency, no out-of-scope settings expansion
- Files changed:
  - `.ai/PLANS/004-autosave-settings-screen.md`
  - `src/vox/gui/settings_window.py`
  - `tests/unit/test_settings_window.py`
- Commands run:
  - `uv run pytest tests/unit/test_settings_window.py -q` -> pass
  - `uv run pytest tests/unit/test_config.py -q` -> pass
  - `just lint` -> pass
  - `just types` -> pass
- Output artifacts:
  - standalone settings controller/view module at `src/vox/gui/settings_window.py`
  - autosave orchestration coverage at `tests/unit/test_settings_window.py`
- Partial / blocked items:
  - CLI and runtime launch wiring remain deferred to Phase 3 by plan scope

2026-03-20 Phase 3: Runtime Launch Integration

- Status: completed
- Phase intent check:
  - phase: `Phase 3: Runtime Launch Integration`
  - sources used: `.ai/RULES.md`, `.ai/COMMANDS/phase-intent-check.md`, `src/vox/cli.py`, `src/vox/gui/tray.py`, `src/vox/gui/stop_window.py`, `src/vox/gui/__init__.py`, `src/vox/gui/settings_launcher.py`, `tests/unit/test_cli.py`
  - locked musts: lazy-import-safe `vox settings` command, standalone launcher path for tray/stop-window contexts, non-blocking tray callback behavior, existing CLI/runtime flows unchanged, user-visible launcher failures
  - locked must-nots: no help/import regressions, no tray lifecycle coupling to settings window, no nested in-process tray/Tk mainloop strategy
- Files changed:
  - `.ai/PLANS/004-autosave-settings-screen.md`
  - `src/vox/cli.py`
  - `src/vox/gui/__init__.py`
  - `src/vox/gui/settings_launcher.py`
  - `src/vox/gui/stop_window.py`
  - `src/vox/gui/tray.py`
  - `tests/unit/test_cli.py`
  - `tests/unit/test_settings_launcher.py`
- Commands run:
  - `uv run pytest tests/unit/test_cli.py -q` -> pass
  - `uv run pytest tests/unit/test_settings_launcher.py -q` -> pass
  - `just lint` -> pass
  - `just types` -> pass
- Output artifacts:
  - `vox settings` CLI command path in `src/vox/cli.py`
  - standalone launch helper in `src/vox/gui/settings_launcher.py`
  - runtime `Settings...` affordances in tray and stop-window surfaces
  - launcher/CLI coverage in `tests/unit/test_settings_launcher.py` and `tests/unit/test_cli.py`
- Partial / blocked items:
  - docs and final visible-done proof remain deferred to Phase 4 by plan scope

2026-03-20 Phase 4: Tests, Docs, and Visible-Done Proof

- Status: completed
- Phase intent check:
  - phase: `Phase 4: Tests, Docs, and Visible-Done Proof`
  - sources used: `.ai/RULES.md`, `.ai/COMMANDS/phase-intent-check.md`, `README.md`, `vox.toml.example`, `docs/dev/status.md`, `.ai/REF/status-surfaces.md`
  - locked musts: document `vox settings`, describe autosave/restart behavior, sync status surfaces, run final repo gates, record visible-done proof
  - locked must-nots: no user-visible feature without docs/status updates, no undocumented warning debt, no skipped validation evidence
- Files changed:
  - `.ai/PLANS/004-autosave-settings-screen.md`
  - `README.md`
  - `vox.toml.example`
  - `docs/dev/status.md`
- Commands run:
  - `uv run pytest tests/unit/test_config.py -q` -> pass
  - `uv run pytest tests/unit/test_cli.py -q` -> pass
  - `uv run pytest tests/unit/test_settings_window.py -q` -> pass
  - `uv run pytest tests/unit/test_settings_launcher.py -q` -> pass
  - `uv run pytest tests/integration -q` -> pass
  - `just lint` -> pass
  - `just format-check` -> pass
  - `just types` -> pass
  - `just docs-check` -> pass
  - `just status` -> pass
  - `just quality && just test` -> pass
- Output artifacts:
  - `vox settings` command and standalone settings window
  - autosaved config at `~/.vox/vox.toml` or `VOX_CONFIG`
  - tray/stop-window runtime launch affordances
  - updated docs in `README.md`, `vox.toml.example`, and `docs/dev/status.md`
- Visible-done evidence:
  - automated proof covers config persistence, autosave orchestration, launcher behavior, and CLI dispatch through the unit suites above
  - documentation now includes direct human verification steps for `vox settings`, autosave behavior, cue preview on slider change, runtime affordance launch, and persistence round-trip
- Manual GUI validation:
  - user confirmed interactive desktop verification completed and accepted for the settings window, autosave behavior, runtime launch affordances, and persistence round-trip
- Partial / blocked items:
  - none

2026-03-20 Post-Review Fixes

- Status: completed
- Scope:
  - fixed the three review findings from the completed 004 implementation
- Files changed:
  - `.ai/PLANS/004-autosave-settings-screen.md`
  - `src/vox/gui/settings_window.py`
  - `tests/unit/test_settings_window.py`
- Commands run:
  - `uv run pytest tests/unit/test_settings_window.py -q` -> pass
  - `just lint` -> pass
  - `just types` -> pass
  - `just quality && just test` -> pass
- Fix evidence:
  - incremental autosave now validates against the controller's full current state, so first-run saves no longer fail when required defaults are only implied in the UI
  - heavy `settings_window` test-action imports now stay behind lazy helper boundaries
  - microphone test failures for config/value/model errors now surface through the status banner instead of escaping the worker path

---

## NOTES

- Recommended launch strategy: add a standalone settings process instead of trying to run a second in-process Tk lifecycle from `pystray` callbacks. This is the lowest-risk approach given the current tray architecture.
- Recommended persistence rule: autosave on every completed valid change, not on every keystroke.
- Recommended scope control: keep config editing to existing supported keys. Do not expand into arbitrary plugin/settings architecture in this feature.
- If implementation reveals that stop-window integration degrades the minimal UX, keep `vox settings` and tray launch as the primary access paths and document the stop-window deferral in a `Plan Patch`.

**Confidence Score**: 8/10 that one-pass implementation succeeds

## Plan Patch

- 2026-03-20 post-review fixes:
  - ensure incremental autosave validates against the controller's full current state so first-run edits do not fail on implied defaults
  - keep settings test-action imports local to preserve the intended lazy GUI import boundary
  - harden `Test Mic` status handling for `ConfigError`, `ValueError`, and `TranscriptionError`
- 2026-03-24 hotkey capture correction:
  - replace freeform hotkey text entry behavior with keypress-driven capture in the settings hotkey field
  - while capture is active, update the field progressively from currently pressed keys (for example: `ALT-`, then `ALT-F12`)
  - persist only on completed capture input and preserve existing validation/error messaging through the config layer

## Execution Report (Addendum)

2026-03-24 Hotkey capture correction

- Status: completed
- Scope:
  - fix settings hotkey input behavior so users do not type key-code text manually
  - ensure progressive display while pressing combinations (modifier(s) first, then trigger)
- Files changed:
  - `.ai/PLANS/004-autosave-settings-screen.md`
  - `src/vox/gui/settings_window.py`
  - `tests/unit/test_settings_window.py`
  - `tests/unit/test_settings_hotkey_capture.py`
- Commands run:
  - `uv run pytest tests/unit/test_settings_window.py tests/unit/test_settings_hotkey_capture.py -q` -> pass
  - `just lint` -> pass
  - `just types` -> pass

2026-03-24 Runtime hotkey rebind on settings close

- Status: completed
- Scope:
  - apply updated hotkey without requiring a full Vox restart
  - restart only the push-to-talk listener loop when the hotkey changes
- Files changed:
  - `.ai/PLANS/004-autosave-settings-screen.md`
  - `src/vox/commands.py`
  - `tests/unit/test_commands.py`
- Commands run:
  - `uv run pytest tests/unit/test_commands.py -q` -> pass
  - `just lint` -> pass
  - `just types` -> pass
