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
- **Env overrides:** `VOX_HOTKEY`, `VOX_DEVICE_ID`, `VOX_MODEL_SIZE`, `VOX_COMPUTE_TYPE`, `VOX_COMPUTE_DEVICE`, `VOX_INJECTION_MODE`, `VOX_TRAY` override the same keys from the file.

Copy the example config and edit:

```bash
cp vox.toml.example ~/.vox/vox.toml
# Edit hotkey and optionally device_id, model_size, etc.
```

## Commands

- **`vox`** or **`vox run`** — Start push-to-talk. By default a small window with a **Stop** button appears; with `use_tray = true` in config (or `VOX_TRAY=1`), a system tray icon is shown instead—click the icon and choose **Quit** to stop. Press and hold your configured hotkey, speak, release; the audio is transcribed and placed on the clipboard (and optionally pasted into the focused window).
- **`vox devices`** — List audio input devices (ID, name, host API). Use this to choose `device_id` in config.
- **`vox test-mic [--device ID] [--seconds N]`** — Record for N seconds, play back the recording, then transcribe and print text. Default 2 seconds. Use to verify mic and model before using `vox`.

## Transcription model (faster-whisper)

- **First run:** The model is downloaded automatically from Hugging Face (size from config, default `base`). No system FFmpeg required (PyAV is used).
- **CPU:** Use `compute_type = "int8"` in config for lower memory and faster inference.
- **GPU:** Set `compute_device = "cuda"` and `compute_type = "float16"` (or `int8`) in config. Requires CUDA 12 and cuDNN 9.
- **Model size:** Set `model_size` in config (e.g. `tiny`, `base`, `small`, `medium`, `large-v3`) for speed vs accuracy.

## OS permissions

- **Microphone:** Required for capture. On Windows, allow app access to the microphone. On macOS, grant Microphone access when prompted.
- **Accessibility / input injection:** Only needed if you use `injection_mode = "clipboard_and_paste"` (paste into focused window). On Windows, run the app with normal privileges; on macOS, grant Accessibility permission to Terminal (or the app running `vox run`) so it can simulate paste.

## Definition of Visible Done

A human can verify the MVP by:

1. **Install:** From repo run `uv sync` (or `pip install -e .`).
2. **Configure:** Copy `vox.toml.example` to `~/.vox/vox.toml`; set `hotkey` (e.g. `ctrl+shift+v`) and optionally `device_id`, `model_size`, `compute_type`, `injection_mode`.
3. **Run:** Execute `uv run vox` or `vox` (or `vox run`). A small “Vox” window with a Stop button appears, or a tray icon if `use_tray` is enabled.
4. **Trigger:** Focus any text field (or leave focus anywhere). Press and hold the configured hotkey, speak a short phrase, release the key.
5. **Verify:** Paste from clipboard (Ctrl+V / Cmd+V) and see the transcribed phrase. If `injection_mode = "clipboard_and_paste"`, the text also appears in the focused field.
6. **Stop:** Click Stop in the Vox window (or close the window) to exit.
7. **Errors:** If mic or model is missing, a clear error message appears (no silent failure).

## Development

- **Quality gate:** `just test quality` (tests, format, lint, types, docstrings, security checks).
- **Tests:** `just test` (pytest). Unit tests under `tests/unit/`, integration under `tests/integration/`.
