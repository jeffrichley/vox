---
last_updated: 2026-03-20
---

# Dev status

## Current focus

- **Settings-screen follow-up watch:** Monitor shipped `vox settings` behavior for any post-ship regressions while keeping canonical docs/status surfaces aligned. Source: `.ai/PLANS/004-autosave-settings-screen.md`

## Recently completed

- **004 Phase 1-4 (autosave settings screen):** added file-backed config persistence helpers, standalone `vox settings`, autosaving Tk settings UI, detached runtime launch integration from tray/stop-window contexts, unit coverage, README/example-config updates, and visible-done proof scaffolding.
- **003 follow-up (configurable cue volume):** recording cue playback volume is now configurable via `cue_volume` / `VOX_CUE_VOLUME`, with a default of `0.5`, plus config/tests/docs updates.
- **003 Phase 1-3 (preloaded recording cues):** packaged start/end cue assets, startup preload/decode cache, hotkey press/release cue playback wiring, unit coverage, and README/status updates completed.
- **Direct typing injection mode:** `injection_mode = "type"` now types transcription into the focused window without modifying the clipboard; config/docs/tests updated.
- **002 Phase 3 (release automation and publish verification):** release-please, PyPI Trusted Publisher publish flow, and non-repo `uvx vox-core` verification are complete.
- **002 Phase 4 (PyInstaller release assets):** `build-release-assets.yml` (release: published, matrix win/mac/linux, smoke test, upload); README “Pre-built binaries (GitHub Releases)”; package name set to vox-core for PyPI.
- **002 Phase 3 (PyPI packaging):** Classifiers, `[project.urls]`, `license` in pyproject.toml; README Install with `uvx vox-core` and `pip install vox-core`; release-please + publish-pypi workflow; PyPI project vox-core + Trusted Publisher; `uv build` produces wheel and sdist.
- **002 Phase 2 (system tray):** Tray icon (pystray + Pillow) with Quit menu; `use_tray` in config and `VOX_TRAY=1` env; icon from `media/vox_icon.png` in package; `just test-quality` passing.
- **002 Phase 1 (default command):** `vox` with no args starts run loop; `vox run` kept as alias. Callback `invoke_without_command=True` in `src/vox/cli.py`; `just test-quality` passing.
- **Phase 4 (Polish and docs):** README updated with install, config, commands (`vox run`, `vox devices`, `vox test-mic`), model setup, OS permissions, and Definition of Visible Done. Added `vox.toml.example`. Confirmed Rich usage for device list and run panel. Quality gate `just test quality` passing. This status doc added.
- **Phase 3:** Global hotkey, capture→transcribe→inject loop, `vox run` with stop window (CLI-only).
- **Phases 1–2:** Foundation, config, capture, faster-whisper transcription, test-mic with play-back and transcribe.

## Diary

- **2026-03-20:** Completed autosave settings-screen feature. Vox now exposes `vox settings`, a standalone Tk settings window with Recording/Transcription/Output/Runtime sections, autosave-on-valid-completion semantics, env override warnings, debounced cue-volume writes with automatic cue preview, and detached launch affordances from the tray and Stop window. Synced README, example config, plan tracking, and validation evidence.
- **2026-03-20:** Added configurable recording-cue volume. Vox now accepts `cue_volume` in config and `VOX_CUE_VOLUME` in the environment, applies that scale at cue playback time, and defaults cues to 50% of the previous level. Updated config/tests/example config/docs.
- **2026-03-20:** Implemented preloaded audible recording cues for push-to-talk. Vox now loads packaged start/end MP3 cues into memory during startup, plays the start cue on valid hotkey press, and plays the end cue after stop is signaled on release. Added direct `av` runtime dependency, cue unit tests, and README/status updates.
- **2026-03-20:** Added explicit `injection_mode = "type"` support so Vox can type directly into the focused window without overwriting the clipboard. Updated README, example config, tests, and plan/status tracking. Also synced status with completed release-please/PyPI/`uvx vox-core` verification.
- **2026-03-17:** Status sync. Current focus: publish release + verify uvx vox-core; Phase 4 workflow/README done; package name vox-core. Recently completed updated for Phase 4 and vox-core.
- **2026-03-17:** 002 Phase 3 executed. PyPI metadata (classifiers, urls, license); README Install and publish steps; `uv build` succeeded; package name vox-core.
- **2026-03-17:** 002 Phase 2 executed. System tray with Quit; config `use_tray` and `VOX_TRAY=1`; `src/vox/gui/tray.py` and icon; `just test-quality` passed.
- **2026-03-17:** 002 Phase 1 executed. Default command UX: `vox` (no args) runs push-to-talk; `vox run` retained. Branch `feat/002-tray-packaging-ux`; `just test-quality` passed.
- **2026-03-17:** Phase 4 completed. README, example config, docs/dev/status.md in place. MVP satisfiable per Definition of Visible Done in README.


