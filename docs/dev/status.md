---
last_updated: 2026-03-17
---

# Dev status

## Current focus

- **002-tray-packaging-ux:** Publish first release (merge release-please PR or create release) then verify `uvx vox-core --help` / `uvx vox-core devices` from non-repo dir; validate Phase 4 binaries on release per `.ai/PLANS/002-tray-packaging-ux.md`.

## Recently completed

- **002 Phase 4 (PyInstaller release assets):** `build-release-assets.yml` (release: published, matrix win/mac/linux, smoke test, upload); README “Pre-built binaries (GitHub Releases)”; package name set to vox-core for PyPI.
- **002 Phase 3 (PyPI packaging):** Classifiers, `[project.urls]`, `license` in pyproject.toml; README Install with `uvx vox-core` and `pip install vox-core`; release-please + publish-pypi workflow; PyPI project vox-core + Trusted Publisher; `uv build` produces wheel and sdist.
- **002 Phase 2 (system tray):** Tray icon (pystray + Pillow) with Quit menu; `use_tray` in config and `VOX_TRAY=1` env; icon from `media/vox_icon.png` in package; `just test-quality` passing.
- **002 Phase 1 (default command):** `vox` with no args starts run loop; `vox run` kept as alias. Callback `invoke_without_command=True` in `src/vox/cli.py`; `just test-quality` passing.
- **Phase 4 (Polish and docs):** README updated with install, config, commands (`vox run`, `vox devices`, `vox test-mic`), model setup, OS permissions, and Definition of Visible Done. Added `vox.toml.example`. Confirmed Rich usage for device list and run panel. Quality gate `just test quality` passing. This status doc added.
- **Phase 3:** Global hotkey, capture→transcribe→inject loop, `vox run` with stop window (CLI-only).
- **Phases 1–2:** Foundation, config, capture, faster-whisper transcription, test-mic with play-back and transcribe.

## Diary

- **2026-03-17:** Status sync. Current focus: publish release + verify uvx vox-core; Phase 4 workflow/README done; package name vox-core. Recently completed updated for Phase 4 and vox-core.
- **2026-03-17:** 002 Phase 3 executed. PyPI metadata (classifiers, urls, license); README Install and publish steps; `uv build` succeeded; package name vox-core.
- **2026-03-17:** 002 Phase 2 executed. System tray with Quit; config `use_tray` and `VOX_TRAY=1`; `src/vox/gui/tray.py` and icon; `just test-quality` passed.
- **2026-03-17:** 002 Phase 1 executed. Default command UX: `vox` (no args) runs push-to-talk; `vox run` retained. Branch `feat/002-tray-packaging-ux`; `just test-quality` passed.
- **2026-03-17:** Phase 4 completed. README, example config, docs/dev/status.md in place. MVP satisfiable per Definition of Visible Done in README.


