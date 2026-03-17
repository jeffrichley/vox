# Vox

Vox is the voice input layer for the system. It captures speech via push-to-talk, transcribes it locally with **faster-whisper**, and injects the text into the clipboard (and optionally into the focused window). No cloud calls; no silent failures.

## Install

From the repo:

```bash
uv sync
```

Or install in editable mode: `pip install -e .` (use a venv).

## Configuration

- **Config file:** `~/.vox/vox.toml`. Create the directory if needed: `mkdir -p ~/.vox`.
- **Override path:** set `VOX_CONFIG` to the full path of your config file.
- **Env overrides:** `VOX_HOTKEY`, `VOX_DEVICE_ID`, `VOX_MODEL_SIZE`, `VOX_COMPUTE_TYPE`, `VOX_COMPUTE_DEVICE`, `VOX_INJECTION_MODE` override the same keys from the file.

Copy the example config and edit:

```bash
cp vox.toml.example ~/.vox/vox.toml
# Edit hotkey and optionally device_id, model_size, etc.
```

## Commands

- **`vox run`** — Start push-to-talk. A small window with a **Stop** button appears. Press and hold your configured hotkey, speak, release; the audio is transcribed and placed on the clipboard (and optionally pasted into the focused window). Click Stop or close the window to exit.
- **`vox devices`** — List audio input devices (ID, name, host API). Use this to choose `device_id` in config.
- **`vox test-mic [--device ID] [--seconds N]`** — Record for N seconds, play back the recording, then transcribe and print text. Default 2 seconds. Use to verify mic and model before using `vox run`.

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
3. **Run:** Execute `uv run vox run` (or `vox run` if installed). A small “Vox” window with a Stop button appears.
4. **Trigger:** Focus any text field (or leave focus anywhere). Press and hold the configured hotkey, speak a short phrase, release the key.
5. **Verify:** Paste from clipboard (Ctrl+V / Cmd+V) and see the transcribed phrase. If `injection_mode = "clipboard_and_paste"`, the text also appears in the focused field.
6. **Stop:** Click Stop in the Vox window (or close the window) to exit.
7. **Errors:** If mic or model is missing, a clear error message appears (no silent failure).

## Development

- **Quality gate:** `just test quality` (tests, format, lint, types, docstrings, security checks).
- **Tests:** `just test` (pytest). Unit tests under `tests/unit/`, integration under `tests/integration/`.
