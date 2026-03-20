# Vox

Vox is the voice input layer for the system. It captures speech via push-to-talk, transcribes it locally with **faster-whisper**, and injects the text into the clipboard (and optionally into the focused window). No cloud calls; no silent failures.

## Install

**From PyPI** (no clone required; package name is `vox-core` because `vox` is taken on PyPI):

```bash
uvx vox-core
```

Or install the tool, then run it (the CLI command is still `vox`):

```bash
pip install vox-core
vox
```

**From source** (development or latest):

```bash
git clone https://github.com/jeffrichley/vox.git && cd vox
uv sync
uv run vox
```

Or install in editable mode: `pip install -e .` (use a venv), then `vox`.

### Pre-built binaries (GitHub Releases)

Packaged binaries for Windows, macOS, and Linux are built on each [GitHub Release](https://github.com/jeffrichley/vox/releases). Download the archive for your platform (e.g. `vox-<version>-windows-amd64.zip`, `vox-<version>-macos-arm64.zip`, `vox-<version>-linux-x86_64.tar.gz`), unpack it, then run the binary:

- **Windows:** Unzip the archive, then run `vox.exe` from inside the `vox` folder (e.g. `.\vox\vox.exe --help`).
- **macOS / Linux:** Unzip or untar the archive, then run `./vox/vox` from the extracted directory (e.g. `./vox/vox --help`).

On first run, the Whisper model is downloaded automatically (see [Transcription model](#transcription-model-faster-whisper)). Binaries are built with PyInstaller and are not signed; you may see a security or Gatekeeper prompt on Windows or macOS.

## Configuration

- **Config file:** `~/.vox/vox.toml`. Create the directory if needed: `mkdir -p ~/.vox`.
- **Override path:** set `VOX_CONFIG` to the full path of your config file.
- **Env overrides:** `VOX_HOTKEY`, `VOX_DEVICE_ID`, `VOX_MODEL_SIZE`, `VOX_COMPUTE_TYPE`, `VOX_COMPUTE_DEVICE`, `VOX_INJECTION_MODE`, `VOX_CUE_VOLUME`, `VOX_TRAY` override the same keys from the file.
- **Settings screen:** run `vox settings` to edit the supported config keys in a desktop window instead of editing TOML manually. Valid completed changes autosave immediately; there is no Save or Cancel flow.

Copy the example config and edit:

```bash
cp vox.toml.example ~/.vox/vox.toml
# Edit hotkey and optionally device_id, cue_volume, model_size, etc.
```

## Commands

- **`vox`** or **`vox run`** — Start push-to-talk. By default a small window with a **Stop** button appears; with `use_tray = true` in config (or `VOX_TRAY=1`), a system tray icon is shown instead—click the icon and choose **Quit** to stop. Audible start/end recording cues are preloaded during startup so the first hotkey cycle does not stall on cue decode. Press and hold your configured hotkey to hear the start cue and begin recording, then release to hear the end cue while transcription/injection continues according to `injection_mode`: clipboard only, clipboard then paste, or direct typing into the focused window.
- **`vox settings`** — Open the standalone settings window. It exposes `Recording`, `Transcription`, `Output`, and `Runtime` sections, autosaves each valid completed change, warns when env vars currently override file-backed values, and shows restart guidance for changes that do not affect an already-running session until restart.
- **Cue volume:** Set `cue_volume` in config (or `VOX_CUE_VOLUME`) to any value from `0.0` to `1.0`. Default is `0.5`. In the settings screen, changing the cue-volume slider autosaves after a short debounce and then plays a cue preview automatically at the new level.
- **`vox devices`** — List audio input devices (ID, name, host API). Use this to choose `device_id` in config.
- **`vox test-mic [--device ID] [--seconds N]`** — Record for N seconds, play back the recording, then transcribe and print text. Default 2 seconds. Use to verify mic and model before using `vox`.

## Settings Screen

- **Autosave rules:** dropdowns and toggles save immediately after a valid selection; text-like fields such as `hotkey` save on Enter or focus loss; `cue_volume` saves after a short debounce so dragging the slider does not write on every movement.
- **Runtime access:** `vox settings` opens the window directly; if Vox is already running, the Stop window and tray both expose a `Settings` / `Settings...` action that launches the same screen as a separate process.
- **Override warnings:** when a `VOX_*` environment variable currently supersedes a file-backed value, the settings window shows that warning so the on-disk value is not mistaken for the effective runtime value.
- **Restart/apply guidance:** changing `hotkey`, device selection, transcription settings, injection mode, or tray usage updates the config immediately, but an already-running Vox session applies those changes after restart.

## Transcription model (faster-whisper)

- **First run:** The model is downloaded automatically from Hugging Face (size from config, default `base`). No system FFmpeg required (PyAV is used).
- **CPU:** Use `compute_type = "int8"` in config for lower memory and faster inference.
- **GPU:** Set `compute_device = "cuda"` and `compute_type = "float16"` (or `int8`) in config. Requires CUDA 12 and cuDNN 9.
- **Model size:** Set `model_size` in config (e.g. `tiny`, `base`, `small`, `medium`, `large-v3`) for speed vs accuracy.

## OS permissions

- **Microphone:** Required for capture. On Windows, allow app access to the microphone. On macOS, grant Microphone access when prompted.
- **Accessibility / input injection:** Needed if you use `injection_mode = "clipboard_and_paste"` or `injection_mode = "type"` (paste or type into the focused window). On Windows, run the app with normal privileges; on macOS, grant Accessibility permission to Terminal (or the app running `vox run`) so it can simulate input.

## Definition of Visible Done

A human can verify the shipped feature set by:

1. **Install:** From repo run `uv sync` (or `pip install -e .`).
2. **Open settings:** Run `uv run vox settings`.
3. **Autosave:** Change `injection_mode` and confirm `~/.vox/vox.toml` (or `VOX_CONFIG`) updates without any Save button.
4. **Cue preview:** Drag `cue_volume`, pause briefly, and confirm the file updates once plus the cue preview plays automatically at the new level.
5. **Validation:** Edit `hotkey` to an invalid value and confirm the window shows an error and the invalid value is not persisted.
6. **Round-trip:** Close and reopen `vox settings` and confirm the saved values reload from disk.
7. **Runtime access:** Run `uv run vox`, then launch settings from the Stop window or tray affordance and confirm the settings window opens without shutting down the active session.
8. **Voice workflow:** Press and hold the configured hotkey, speak, release, and confirm transcription/injection still works as configured.
9. **Errors:** If mic, model, or launch prerequisites are missing, Vox surfaces a clear error message instead of failing silently.

## Development

- **Quality gate:** `just quality && just test` (tests, format, lint, types, docstrings, security checks).
- **Tests:** `just test` (pytest). Unit tests under `tests/unit/`, integration under `tests/integration/`.
