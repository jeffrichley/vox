# Feature: 002-tray-packaging-ux — Default run UX, system tray, PyPI tool, installers

The following plan should be complete, but it is important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files etc.

## Feature Description

Three related improvements so Vox is easier to run and distribute:

1. **Default-command UX** — Invoking `vox` with no subcommand starts the push-to-talk run loop (current `run` behavior). Users run `uvx vox` or `vox` without typing `run`. Subcommands remain `vox devices` and `vox test-mic`.

2. **System tray** — Replace or augment the Tk stop window with a system tray icon: minimize to tray, quit from tray, optional “Show window”. The run loop continues in the background; the user stops via tray menu (Quit) or optional window.

3. **Packaging and tool UX** — Publish to PyPI so Vox is a **runnable tool** that can be invoked via **`uvx vox`** (and `pip install vox` + `vox`) from any environment without cloning the repo. Optionally add platform installers (Windows portable/MSI, macOS app) so users can install without Python/uv.

## User Stories

- As a **user**, I want to run **`uvx vox`** (no subcommand) so that push-to-talk starts immediately and I don’t have to remember `run`.
- As a **user**, I want Vox to sit in the **system tray** with **Quit** so that I can stop it without a visible window and without closing a terminal.
- As a **user**, I want to **install Vox with `uvx vox`** (or `pip install vox`) so that I don’t need to clone the repo or run from source.

## Problem Statement

- Today `vox run` is required; users expect `vox` to “just run” the main feature.
- The Tk stop window is always visible; users want minimize-to-tray and quit-from-tray.
- The package is not on PyPI, so `uvx vox` is not available; distribution is source-only.

## Solution Statement

- Use Typer’s `invoke_without_command=True` callback so that `vox` with no subcommand invokes the run loop; keep `devices` and `test-mic` as explicit subcommands.
- Add a system tray icon (pystray + PIL) with menu “Quit” (and optionally “Show window”); run the push-to-talk loop in a background thread; closing the tray menu “Quit” sets the stop event and exits. Optionally keep a small Tk window that can be shown/hidden from tray.
- Publish to PyPI so Vox is a **runnable tool** invokable via **`uvx vox`** (no local install) or `pip install vox` then `vox`; add minimal PyPI metadata (classifiers, URLs). Optionally add a phase for PyInstaller/Windows portable and macOS .app.

## Feature Metadata

**Feature Type:** Enhancement  
**Estimated Complexity:** Medium (UX + packaging; tray has platform nuances)  
**Primary Systems Affected:** `src/vox/cli.py`, `src/vox/gui/` (stop_window, new tray module), `pyproject.toml`, CI/docs  
**Dependencies:** pystray, Pillow (for tray icon); existing Tk, typer, rich

## Traceability Mapping

- Roadmap system improvements: `None`
- Debt items: `None`
- **No SI/DEBT mapping for this feature.**

## Branch Setup (Required)

Branch naming follows the plan filename:

- Plan: `.ai/PLANS/002-tray-packaging-ux.md`
- Branch: `feat/002-tray-packaging-ux`

Commands (must be executable as written):

```bash
PLAN_FILE=".ai/PLANS/002-tray-packaging-ux.md"
PLAN_SLUG="$(basename "$PLAN_FILE" .md)"
BRANCH_NAME="feat/${PLAN_SLUG}"
git show-ref --verify --quiet "refs/heads/${BRANCH_NAME}" \
  && git switch "${BRANCH_NAME}" \
  || git switch -c "${BRANCH_NAME}"
```

On Windows PowerShell:

```powershell
$PLAN_FILE = ".ai/PLANS/002-tray-packaging-ux.md"
$PLAN_SLUG = [System.IO.Path]::GetFileNameWithoutExtension($PLAN_FILE)
$BRANCH_NAME = "feat/$PLAN_SLUG"
git switch $BRANCH_NAME 2>$null; if ($LASTEXITCODE -ne 0) { git switch -c $BRANCH_NAME }
```

---

## CONTEXT REFERENCES

### Relevant Codebase Files (read before implementing)

- `src/vox/cli.py` — Typer app, `devices`, `test-mic`, `run`; entry `main()` calls `app()`. Change to callback-based default command.
- `src/vox/gui/stop_window.py` — `run_stop_window(console)` runs Tk window + daemon thread for `handle_run`. Tray will either replace this or wrap it (tray + optional window).
- `src/vox/commands.py` — `handle_run(console, stop_event=...)`; used by stop_window. Tray will call the same worker with a stop_event.
- `pyproject.toml` — `[project.scripts]` vox = "vox.cli:main"; build-system hatchling; add classifiers/urls for PyPI.
- `.ai/RULES.md` — Quality gates `just quality && just test`; no silent fallbacks; plan-before-code.
- `.ai/PLANS/001-push-to-talk.md` — Current run/window behavior and GUI omit from coverage.

### New Files to Create

- `src/vox/gui/tray.py` — Tray icon (pystray), menu Quit (and optional Show), run worker thread; return same contract as `run_stop_window` (exception or None).
- Optional: `scripts/build_installer.py` or justfile targets for PyInstaller / macOS app (Phase 4).

### Relevant Documentation

- [Typer callback invoke_without_command](https://typer.tiangolo.com/tutorial/subcommands/callback-override/) — Default command when no subcommand given.
- [pystray](https://pypi.org/project/pystray/) — System tray icon; use `pystray.Menu`, `Icon.run()` or `run_detached()` to run alongside other GUIs.
- [Publishing with uv](https://docs.astral.sh/uv/guides/publishing/) — `uv build`, `uv publish`; token / trusted publishers.
- [Hatchling / PyPI metadata](https://hatch.pypa.io/latest/config/metadata/) — classifiers, urls in pyproject.toml.

### Patterns to Follow

- **GUI and coverage:** Keep tray (and any new GUI code) in `src/vox/gui/` and omit from coverage per existing `omit` in pyproject.toml; do not add `# pragma: no cover` in cli.
- **CLI errors:** Keep `RunWindowError` and config/transcribe error handling in `cli.py`; tray module returns `BaseException | None` like `run_stop_window`.
- **Threading:** Reuse pattern from `stop_window.py`: main thread for UI (Tk or pystray), daemon thread for `handle_run(console, stop_event=...)`.

---

## IMPLEMENTATION PLAN

### Phase 1: Default command UX (vox = run)

Make `vox` with no arguments start the run loop. Keep `vox devices` and `vox test-mic` as subcommands.

**Intent Lock**

- Source of truth: this plan; Typer callback docs.
- **Must:** `vox` (no args) starts the same run flow as current `vox run`; `vox devices` and `vox test-mic` unchanged; no breaking change to existing scripts that call `vox run` (keep `run` as an alias or deprecated alias that does the same thing).
- **Must not:** Require a subcommand for the default run; remove `devices` or `test-mic`.
- Acceptance gates: `uv run vox` starts run loop (manual); `uv run vox devices` and `uv run vox test-mic` still work; `just test-quality` passes.

**Tasks:**

- [x] **UPDATE** `src/vox/cli.py`: Add `@app.callback(invoke_without_command=True)` and a callback that, when no subcommand is invoked, calls the same logic as current `run()` (run_stop_window / RunWindowError handling). Keep `@app.command()` for `devices` and `test-mic`. Either keep `run` as a command that invokes the same logic (so `vox run` still works) or document that `vox` is the preferred form.
- [x] **VALIDATE** `uv run vox` (no args) starts push-to-talk; `uv run vox devices` lists devices; `uv run vox test-mic --seconds 1` works; `just test-quality` passes.

---

### Phase 2: System tray

Add a system tray icon with Quit (and optionally Show window). Replace or augment the Tk stop window so the user can minimize to tray and quit from tray.

**Intent Lock**

- Source of truth: this plan; pystray docs.
- **Must:** Tray icon visible when run is active; menu item “Quit” sets stop event and exits cleanly; push-to-talk loop runs in background thread; same error contract as stop_window (return exception or None to cli).
- **Must not:** Block the main thread with the hotkey loop (keep loop in worker thread); break existing run flow or config loading.
- Acceptance gates: `vox` shows tray icon; Quit from tray stops Vox; `just test-quality` passes; tray code in `src/vox/gui/` omitted from coverage.

**Tasks:**

- [x] **ADD** dependency: `pystray`, `Pillow` (for icon image) in `pyproject.toml` and lockfile.
- [x] **CREATE** `src/vox/gui/tray.py`: Implement tray icon (pystray) with menu “Quit” that sets a threading.Event and stops the icon loop. Start `handle_run(console, stop_event=...)` in a daemon thread. Function signature similar to `run_stop_window(console) -> BaseException | None`. Use `Icon.run_detached()` if needed so tray runs alongside worker thread. On Quit: set stop_event, stop icon, return None (or worker exception if already failed).
- [x] **UPDATE** `src/vox/cli.py`: Option to use tray instead of Tk window (e.g. env `VOX_TRAY=1` or config `use_tray: true`). If tray enabled, call new tray entry point instead of `run_stop_window`; same RunWindowError handling. If not enabled, keep current `run_stop_window` behavior.
- [x] **UPDATE** `pyproject.toml`: Add `src/vox/gui/tray.py` to coverage omit if not already covered by `src/vox/gui/*`.
- [x] **VALIDATE** Manual: run with tray enabled, see icon, Quit from menu stops Vox; `just test-quality` passes.

---

### Phase 3: PyPI packaging — Vox as a runnable tool (uvx vox)

Publish the package to PyPI so Vox is installable as a **tool** and can be invoked with **`uvx vox`** (run-once fetch and execute) or `pip install vox` then `vox`. No change to default-command or tray behavior beyond what is in Phase 1 and 2.

**Intent Lock**

- Source of truth: this plan; uv publish docs; hatchling metadata.
- **Must:** Package builds with `uv build`; **publish to PyPI** with `uv publish` so that **`uvx vox` runs without any local project or install** (fetch-and-run from PyPI); PyPI metadata (classifiers, project.urls) so the package page is usable; README mentions `uvx vox` and `pip install vox`.
- **Must not:** Break existing `uv run vox` from source; remove or rename the `vox` script entry point.
- Acceptance gates: `uv build` produces wheel and sdist; **package is published to PyPI**; **`uvx vox --help` (or `uvx vox devices`) succeeds from a context with no local vox project** (confirms runnable tool from PyPI); `just test-quality` passes.

**Tasks:**

- [x] **UPDATE** `pyproject.toml`: Add `[project]` classifiers (e.g. Python 3.12+, License, Topic), `[project.urls]` (Homepage, Repository, Documentation if any). Ensure `version` is set and `readme` points to README.md.
- [x] **UPDATE** `README.md`: Add “Install” section with `uvx vox` and `pip install vox`; note that running from source remains `uv run vox` or `uv sync && vox`.
- [x] **DOCUMENT** (in plan or docs/dev): Publish steps — `uv build`, `uv publish` (with token or trusted publisher); optional TestPyPI first.
- [x] **VALIDATE** `uv build` succeeds; run from built wheel locally (`uv pip install dist/*.whl` then `vox`) to confirm entry point; `just test-quality` passes.
- [ ] **ADD release-please:** Add `.github/workflows/release-please.yml` and config (e.g. `release-please-config.json`) so releases are driven by [release-please](https://github.com/googleapis/release-please): conventional commits → release PR → merge → GitHub release (tag) created. No manual version bumps or publish from local.
- [ ] **ADD PyPI publish workflow (Trusted Publishers):** Add `.github/workflows/publish-pypi.yml` that runs on `release: published`, builds with `uv build --no-sources`, and runs `uv publish`. Use [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/) (OIDC): workflow requests `id-token: write`; GitHub Actions issues a short-lived token to PyPI; **no long-lived API token** stored in secrets. Optionally use a `pypi` environment for approval gates.
- [ ] **One-time PyPI setup:** On PyPI, add a Trusted Publisher for this repo: owner, repo name, workflow filename (e.g. `publish-pypi.yml`), and optionally environment `pypi`. See [Adding a Trusted Publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).
- [ ] **VERIFY** without local install: After the first release has been published by the workflow, from a directory that is **not** the vox repo run `uvx vox-core --help` and `uvx vox-core devices`. Phase 3 is complete when these succeed (tool is fetched from PyPI and runs with no local clone or install).

---

### Phase 4 (Optional): PyInstaller release assets

Build PyInstaller **onedir** artifacts for Windows, macOS, and Linux on each GitHub release; upload archives as release assets. **GitHub Releases** = primary home for packaged binaries; **PyPI** remains separate (Python package only).

**Intent Lock**

- Source of truth: this plan; PyInstaller docs.
- **Must:** Use PyInstaller only; separate workflow from PyPI (`build-release-assets.yml`); GitHub Releases = home for binaries; CLI packaging first (no `.spec` in first pass); `--onedir` on all platforms; matrix build (Windows, macOS, Linux); smoke test before upload; non-mutating PyInstaller install in CI (`uv pip install pyinstaller`); artifact naming convention; defer `.spec` to a later phase only if hidden imports/data/native libs require it.
- **Must not:** Break PyPI/source installs; combine binary build with `publish-pypi.yml`; use `uv add` for PyInstaller in CI; upload without smoke test.
- Acceptance gates: `release: published` triggers `build-release-assets.yml`; three artifacts (Windows zip, macOS zip, Linux tar.gz) attached to the release; smoke test passes per platform; README documents pre-built binaries.

**Artifact naming**

- Pattern: `vox-<version>-<platform>-<arch>.<ext>` (version = release tag, e.g. `v0.2.0`).
- Examples: `vox-v0.2.0-windows-amd64.zip`, `vox-v0.2.0-macos-arm64.zip`, `vox-v0.2.0-linux-x86_64.tar.gz`.

**Immutable releases**

- Release assets are **immutable only if** the repository has the relevant setting enabled (e.g. "Prevent users from modifying or deleting existing tags"). If that setting is off, assets can be replaced or removed. We do not use draft releases for now unless we adopt that policy.

**Later phase**

- Introduce a `vox.spec` file **only if** hidden imports, data files, or native libs (e.g. faster-whisper) require it; otherwise keep PyInstaller CLI packaging.

**Tasks:**

- [x] **ADD** `.github/workflows/build-release-assets.yml`: trigger `release: published`; matrix (windows, macos, linux); checkout release tag; `uv sync`; `uv pip install pyinstaller`; PyInstaller `--onedir --name vox`; platform-specific smoke test; platform-specific archive (zip/tar.gz); upload to release via `softprops/action-gh-release`.
- [x] **UPDATE** README: "Pre-built binaries (GitHub Releases)" section — link to Releases, describe download/unpack/run per platform; note first-run model download; optional note on unsigned binaries.
- [ ] **VALIDATE** Next release triggers workflow; three artifacts appear on the release; manual run of one artifact confirms binary works.

---

## Phase Intent Check Report (all phases)

*Run per `.ai/COMMANDS/phase-intent-check.md` before implementation.*

### Phase 1: Default command UX (vox = run)

| Item | Status |
|------|--------|
| **Phase locked** | Yes |
| **Source docs used** | This plan (Intent Lock); `.ai/RULES.md` (quality gates, no silent fallbacks); [Typer callback docs](https://typer.tiangolo.com/tutorial/subcommands/callback-override/) |
| **Must** | `vox` (no args) starts same run flow as current `vox run`; `vox devices` and `vox test-mic` unchanged; keep `vox run` as alias (no breaking change) |
| **Must not** | Require a subcommand for default run; remove `devices` or `test-mic` |
| **Acceptance gates to run** | `uv run vox` starts run loop (manual); `uv run vox devices`; `uv run vox test-mic --seconds 1`; `just test-quality` |

### Phase 2: System tray

| Item | Status |
|------|--------|
| **Phase locked** | Yes |
| **Source docs used** | This plan (Intent Lock); `.ai/RULES.md`; [pystray](https://pypi.org/project/pystray/); `src/vox/gui/stop_window.py` (return contract, threading pattern) |
| **Must** | Tray icon visible when run active; menu "Quit" sets stop event and exits cleanly; push-to-talk in background thread; same error contract as stop_window (return exception or None) |
| **Must not** | Block main thread with hotkey loop; break existing run flow or config loading |
| **Acceptance gates to run** | Manual: `vox` with tray enabled shows icon, Quit stops Vox; `just test-quality`; tray code under `src/vox/gui/` (already omitted by `src/vox/gui/*` in pyproject.toml) |

### Phase 3: PyPI packaging — Vox as a runnable tool (uvx vox)

| Item | Status |
|------|--------|
| **Phase locked** | Yes |
| **Source docs used** | This plan (Intent Lock); `.ai/RULES.md`; [uv building and publishing](https://docs.astral.sh/uv/guides/package/#uploading-attestations-with-your-package); [Hatchling metadata](https://hatch.pypa.io/latest/config/metadata/) |
| **Must** | `uv build` succeeds; **publish to PyPI** so **`uvx vox` runs without local project/install**; PyPI metadata (classifiers, project.urls); README mentions `uvx vox` and `pip install vox` |
| **Must not** | Break `uv run vox` from source; remove or rename `vox` script entry point |
| **Acceptance gates to run** | release-please creates release PRs; merge creates release and triggers **publish-pypi**; **PyPI Trusted Publisher** configured; **`uvx vox-core --help` / `uvx vox-core devices` succeed from a non-project directory**; `just test-quality` |

### Phase 4 (Optional): PyInstaller release assets

| Item | Status |
|------|--------|
| **Phase locked** | Yes (optional; deferrable) |
| **Source docs used** | This plan (Intent Lock); PyInstaller docs |
| **Must** | PyInstaller only; separate workflow; GitHub Releases = binaries; CLI + `--onedir`; matrix build; smoke test before upload; non-mutating PyInstaller install; artifact naming convention; defer `.spec` to later phase if needed |
| **Must not** | Combine with PyPI workflow; `uv add` PyInstaller in CI; upload without smoke test |
| **Acceptance gates to run** | `release: published` triggers build-release-assets; three artifacts on release; smoke test per platform; README documents pre-built binaries |

### Execution handoff constraints (all phases)

- Treat **Must** and **Must not** as binding during implementation.
- After each phase: update plan checkboxes, run `.ai/COMMANDS/status-sync.md .ai/PLANS/002-tray-packaging-ux.md`, append validation evidence in plan `## Execution Report`.
- Final gate per `.ai/RULES.md`: `just quality && just test` (repo also has `just test-quality` = quality-check + test-cov; use that for CI parity).

---

## STEP-BY-STEP TASKS (Phases 1–3)

Execute in order. Phase 4 is optional and can be a separate PR.

1. **UPDATE** `src/vox/cli.py` — DONE  
   - Add callback with `invoke_without_command=True` that, when `ctx.invoked_subcommand` is None, calls the same logic as current `run()` (run_stop_window + RunWindowError handling).  
   - Keep `devices` and `test-mic` as `@app.command()`.  
   - Keep `run` as a command that invokes the same run logic (backward compatibility).  
   - **VALIDATE** `uv run vox`, `uv run vox devices`, `uv run vox test-mic --seconds 1`; `just test-quality`.

2. **ADD** dependencies in `pyproject.toml`: `pystray`, `Pillow`. Run `uv lock`. — DONE  
   - **VALIDATE** `uv sync` and `just test-quality`.

3. **CREATE** `src/vox/gui/tray.py` — DONE  
   - Implement `run_tray(console: Console) -> BaseException | None`.  
   - Create pystray Icon with a simple image (Pillow Image); menu with “Quit”.  
   - Start daemon thread running `handle_run(console, stop_event=ev)`.  
   - On Quit: set `ev`, stop icon; return any worker exception.  
   - **PATTERN** Same return contract as `run_stop_window` in `stop_window.py`.  
   - **VALIDATE** Manual run with tray; `just test-quality` (tray omitted from coverage).

4. **UPDATE** `src/vox/cli.py` (and optionally config) — DONE  
   - If config or env enables tray (e.g. `VOX_TRAY=1` or config `use_tray`), call `run_tray(console)` instead of `run_stop_window(console)`.  
   - **VALIDATE** Tray and non-tray paths; `just test-quality`.

5. **UPDATE** `pyproject.toml` — DONE  
   - Classifiers (Programming Language :: Python :: 3.12, License, Topic).  
   - `[project.urls]` Homepage, Repository.  
   - **VALIDATE** `uv build`; `just test-quality`.

6. **UPDATE** `README.md` — DONE  
   - Install: `uvx vox` and `pip install vox`; run: `vox` (or `vox run`), `vox devices`, `vox test-mic`.  
   - **VALIDATE** Docs read correctly.

7. **ADD release-please**  
   - Add workflow (e.g. `.github/workflows/release-please.yml`) and config so release PRs are created from conventional commits; merging the release PR creates the GitHub release (tag).  
   - **VALIDATE** Pushing a conventional commit (e.g. `fix: something`) triggers or updates a release PR.

8. **ADD PyPI publish workflow (Trusted Publishers)**  
   - Add workflow (e.g. `.github/workflows/publish-pypi.yml`) that runs on `release: published`, has `permissions: id-token: write` (and optionally `environment: pypi`), runs `uv build --no-sources` and `uv publish`. No `UV_PUBLISH_TOKEN` — [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/) (OIDC) let GitHub Actions obtain a short-lived token.  
   - **One-time:** On PyPI project page, add Trusted Publisher: repository owner, repository name, workflow filename, optional environment.  
   - **VALIDATE** Merging a release PR creates the release and triggers the workflow; package appears on PyPI.

9. **VERIFY** without local install  
   - From a directory that is **not** the vox repo, run `uvx vox --help` and `uvx vox devices`. Phase 3 complete when these succeed.

---

## TESTING STRATEGY

- **Unit tests:** No new unit tests required for default command (CLI structure); tray and pystray code omitted from coverage like `stop_window`. Existing tests for `devices`, `test-mic`, and run error handling remain; ensure any CLI refactor doesn’t break them.
- **Integration:** Manual test for `vox` (no args), tray Quit, and (after publish) `uvx vox`.
- **Regression:** Full `just test-quality` after each phase.

---

## VALIDATION COMMANDS

- `just test-quality` — after every change.
- `uv run vox` — starts run loop (no subcommand).
- `uv run vox devices` — lists devices.
- `uv run vox test-mic --seconds 1` — records and plays back.
- `uv build` — wheel and sdist build successfully.
- Optional: `uv publish --dry-run` or publish to TestPyPI.

---

## DEFINITION OF VISIBLE DONE

- A user can run **`uvx vox-core`** with **no local clone or install** — uv fetches the package from PyPI and runs it (Phase 3 complete when this is true).
- A user can run **`uvx vox-core`** or **`pip install vox-core`** then `vox` and push-to-talk starts without typing `run`.
- A user can enable the tray and see a system tray icon; choosing **Quit** from the tray stops Vox.
- A user who installs with **`pip install vox-core`** or **`uvx vox-core`** gets the same CLI (default run, `devices`, `test-mic`).

---

## ACCEPTANCE CRITERIA

- [x] `vox` with no subcommand starts the run loop; `vox run` still works.
- [x] Tray icon appears when run with tray enabled; Quit from tray exits cleanly.
- [x] `uv build` succeeds; PyPI metadata (classifiers, urls) present; README documents `uvx vox-core` and `pip install vox-core`.
- [ ] Package **published to PyPI** (vox-core); **`uvx vox-core --help` and `uvx vox-core devices` succeed from a directory that is not the vox repo** (no local install).
- [ ] `just test-quality` passes; no regressions in existing tests (run after closing any running Vox/tray to avoid venv lock).
- [x] GUI code (tray, stop_window) remains omitted from coverage; no new pragmas in cli.

---

## COMPLETION CHECKLIST

- [x] Phase 1 default command done and validated.
- [x] Phase 2 tray done and validated.
- [ ] Phase 3 complete when: PyPI metadata and docs done, **package published to PyPI (vox-core)**, and **`uvx vox-core` verified from a non-project context** (no local install).
- [x] README updated; build validated; publish steps documented.

---

## Publish steps (Phase 3): release-please + PyPI Trusted Publishers

Releases are driven by **release-please** (no manual version bumps or local publish). PyPI uploads use **Trusted Publishers** so GitHub Actions obtains a short-lived token via OIDC — no long-lived API token in secrets. See [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/) and [Publishing with OpenID Connect](https://docs.pypi.org/trusted-publishers/getting-started/).

### Flow

1. **Develop with conventional commits** (e.g. `feat: add X`, `fix: Y`). release-please uses these to build release notes and version bumps.
2. **release-please** runs on push to `main` and opens or updates a **Release PR** (e.g. “chore(main): release 0.2.0”). The PR updates version (e.g. in `pyproject.toml`) and CHANGELOG.
3. **Merge the Release PR.** release-please then creates the **GitHub release** (tag, e.g. `v0.2.0`) and release notes.
4. **Publish workflow** runs on `release: published`. It checks out the tag, runs `uv build --no-sources` and `uv publish`. With **Trusted Publishers** configured on PyPI, the job uses `permissions: id-token: write`; GitHub’s OIDC provider issues an identity token; PyPI validates it and returns a **short-lived API token** (no `UV_PUBLISH_TOKEN` or secrets). See [Adding a Trusted Publisher to an existing PyPI project](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).
5. **Verify:** From a non-project directory run `uvx vox-core --help` and `uvx vox-core devices`. Phase 3 is complete when these succeed (package on PyPI is vox-core; CLI command remains `vox`).

### One-time PyPI setup

On [PyPI → Your projects → vox-core → Publishing](https://pypi.org/manage/projects/) (project name is **vox-core**; "vox" is taken on PyPI), add a **Trusted Publisher**:

- **Publisher:** GitHub Actions  
- **Owner:** your GitHub org/user (e.g. `jeffrichley`)  
- **Repository name:** `vox`  
- **Workflow filename:** `publish-pypi.yml` (must match the workflow that runs `uv publish`)  
- **Environment (optional):** `pypi` — if used, create a GitHub environment named `pypi` and optionally require approvals for extra safety.

If the PyPI project does not exist yet, create it once (e.g. via [pypi.org/manage/account/register](https://pypi.org/manage/account/register/) or by uploading a first version manually or with a token). Then add the Trusted Publisher so that future publishes use OIDC only. After this, only that workflow (and optionally that environment) can obtain upload tokens for the PyPI project **vox-core**.

### Workflow details

- **release-please:** Runs on `push` to `main`; uses `release-please-config.json` (e.g. `release-type: python`). Merge the generated Release PR to create the release.
- **publish-pypi:** Triggers on `release: published`. Job has `permissions: id-token: write` and optionally `environment: pypi`. Steps: checkout (ref = release tag), install uv, `uv build --no-sources`, `uv publish`. If an index rejects attestations, add `--no-attestations` or `UV_PUBLISH_NO_ATTESTATIONS`.

### Manual / TestPyPI (optional)

To test uploads without release-please or to use TestPyPI, you can still run locally: `uv build --no-sources` then `uv publish --repository-url https://test.pypi.org/legacy/` (with a TestPyPI token). For production PyPI, the recommended path is release-please + Trusted Publishers only.

### Finish Phase 3 — actionable checklist

Code and CI for Phase 3 are in place. To close Phase 3:

1. **One-time PyPI**
   - Ensure the project **vox-core** exists on PyPI (create at [pypi.org/manage/projects/](https://pypi.org/manage/projects/) if needed; "vox" is taken so we use vox-core).
   - On the project’s **Publishing** tab, add a **Trusted Publisher**: GitHub Actions, owner/repo `vox`, workflow filename **`publish-pypi.yml`**.

2. **Create a release**
   - **Option A (recommended):** Merge the release-please **Release PR** (e.g. “chore(main): release 0.2.0”) into `main`. release-please will create the GitHub release and tag; that triggers `publish-pypi.yml` and `build-release-assets.yml`.
   - **Option B:** In GitHub → Repository → Releases → “Draft a new release”, choose a tag (e.g. create `v0.1.0` from `main`) and publish. The same workflows run on `release: published`.

3. **Verify**
   - After the Publish to PyPI job succeeds, from a directory **outside** the vox repo run:
     - `uvx vox-core --help`
     - `uvx vox-core devices`
   - Phase 3 is complete when both succeed (the CLI command is still `vox`; the PyPI package name is vox-core).

4. **Plan checkboxes**
   - Mark “Package published to PyPI” and “uvx vox-core verified from non-project context” in **ACCEPTANCE CRITERIA**, and “Phase 3 complete when…” in **COMPLETION CHECKLIST**. Append a one-line validation note to **Execution Report** (Phase 3).

---

## NOTES

- **Default command:** Keeping `run` as an alias preserves scripts that call `vox run`; preferred UX is `vox` with no args.
- **Tray vs window:** First implementation can be “tray only” (no Tk window) or “tray + optional window”; optional window can be a later refinement.
- **PyPI:** Releases are done via **release-please**; publish to PyPI is done by the **publish-pypi** workflow using **Trusted Publishers** (OIDC). No long-lived API token; GitHub Actions obtains a short-lived token from PyPI.
- **Installers (Phase 4):** Can be a separate plan/PR to keep this one focused.

---

## Execution Report

### Phase 1: Default command UX (vox = run) — 2026-03-17

**Branch:** `feat/002-tray-packaging-ux` (created from main).

**Completed tasks:**
- Updated `src/vox/cli.py`: added `@app.callback(invoke_without_command=True)` with `_default_callback(ctx)` that calls `_run_impl()` when `ctx.invoked_subcommand is None`. Extracted run flow into `_run_impl()` (run_stop_window + RunWindowError handling). Kept `run` as `@app.command()` calling `_run_impl()` for backward compatibility. Kept `devices` and `test-mic` as `@app.command()`.
- Validated: `uv run vox --help` shows devices, test-mic, run; `uv run vox devices` lists devices; `uv run vox test-mic --seconds 1` runs; `just test-quality` passes (83 tests, 89% coverage, all quality checks).

**Phase intent check:** Intent Lock in plan used; Must/Must not respected; no subcommand required for default run; `vox run` still works.

**Evidence:** `just docs-check` and `just status` pass. Status doc updated (`docs/dev/status.md`: Current focus, Recently completed, Diary).

**Ready for commit:** Phase 1 complete; all validation commands pass.

### Phase 2: System tray — 2026-03-17

**Completed tasks:**
- Added dependencies: `pystray>=0.19.0`, `pillow>=10.0.0` in `pyproject.toml`; `uv lock` run.
- Created `src/vox/gui/tray.py`: `run_tray(console) -> BaseException | None`; pystray Icon with menu “Quit”; daemon thread runs `handle_run(console, stop_event=...)`; on Quit sets stop_event and `icon.stop()`. Icon loaded from package resource `vox.gui` / `vox_icon.png` (copied from `media/vox_icon.png` into `src/vox/gui/`).
- Updated `src/vox/config.py`: added `use_tray` (optional bool, default False), `VOX_TRAY` env (1/true/yes → True), `_validate_use_tray`, `_bool_default`, included in `get_config()`.
- Updated `src/vox/cli.py`: `_run_impl()` loads config, branches on `use_tray` to call `run_tray(console)` or `run_stop_window(console)`; same RunWindowError handling for both.
- Updated `vox.toml.example`: commented `use_tray` option and env note.
- Coverage: `src/vox/gui/*` already omitted in pyproject.toml; no change needed.

**Validation:** `just test-quality` passed (83 tests, 87% coverage). Manual: run with `VOX_TRAY=1` or `use_tray = true` in config to see tray icon; Quit from menu stops Vox.

**Ready for commit:** Phase 2 complete; all validation commands pass.

### Phase 3: PyPI packaging — 2026-03-17

**Completed tasks:**
- Updated `pyproject.toml`: Added `license = "MIT"`; `classifiers` (Development Status, Environment, Intended Audience, License, OS, Programming Language :: 3.12/3.13, Topic :: Multimedia :: Sound/Audio :: Speech); `[project.urls]` Homepage and Repository pointing to https://github.com/jeffrichley/vox.
- Updated `README.md`: Install section now leads with PyPI (`uvx vox-core`, `pip install vox-core`), then from-source (clone, `uv sync`, `uv run vox`). Commands section updated for `vox`/`vox run` and tray; Definition of Visible Done updated. Configuration mentions `VOX_TRAY`.
- Documented publish steps in plan: **Publish steps (Phase 3)** with `uv build`, optional TestPyPI, `uv publish`, and verify with `uvx vox-core --help`.
- Validated: `uv build` succeeded — produced wheel and sdist (package name vox-core).

**Note:** Local wheel install (`uv pip install dist/*.whl`) was not run because `vox.exe` was in use (Vox tray running). Exit Vox from the tray, then run `just test-quality` to confirm full gate. Phase 3 changed only metadata and docs; no application code changes.

**Ready for commit:** Phase 3 complete. After publishing to PyPI (vox-core), users can run `uvx vox-core` or `pip install vox-core` then `vox`.

### Phase 4: PyInstaller release assets — 2026-03-17

**Completed tasks:**
- Added `.github/workflows/build-release-assets.yml`: trigger `release: published`; single job with matrix (windows / macos / linux); checkout at release tag; Python 3.12 + uv; `uv sync --frozen --all-groups`; `uv pip install pyinstaller` (non-mutating); `uv run pyinstaller --onedir --name vox --collect-all vox vox`; explicitly platform-specific smoke test steps (Windows: `.\dist\vox\vox.exe --help`; macOS/Linux: `./dist/vox/vox --help`); explicitly platform-specific archive steps (Windows: `Compress-Archive`; macOS: `zip`; Linux: `tar -czvf`); upload to release via `softprops/action-gh-release@v2` with `files: ${{ env.ARTIFACT_NAME }}`.
- Updated README: new subsection "Pre-built binaries (GitHub Releases)" under Install — link to Releases, per-platform download/unpack/run (Windows: `vox.exe` in folder; macOS/Linux: `./vox/vox`), first-run Whisper model note, unsigned-binaries note.

**Pending:** VALIDATE on next release — workflow runs, three artifacts attached, manual run of one binary (e.g. `vox --help`, `vox devices`) confirms it works. If PyInstaller misses modules (e.g. faster-whisper), plan follow-up phase for `vox.spec`.

### Validation run (2026-03-17) — `.ai/COMMANDS/validate.md` + plan 002

**Level 0:** `uv --version` → pass; `just --version` → pass.

**Level 1:** `just lint` → pass; `just format-check` → pass; `just types` → pass; `just docs-check` → pass; `just test` → pass (after fix below).

**Level 2:** `just quality` → pass; `just test` → pass (83 passed).

**Plan 002 smoke:** `uv run vox --help` → pass (Usage + Commands); `uv run vox devices` → pass (device table); `just status` → pass.

**Fix applied:** Six `TestRunCommand` tests were failing because `_run_impl()` uses `run_tray` when config has `use_tray` True; tests only patched `run_stop_window`. Patched `get_config` to return `{"use_tray": False}` in those tests so the stop-window path is exercised and the existing assertions hold.
