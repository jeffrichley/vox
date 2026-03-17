# vox

Vox is the voice input layer for the system. It captures spoken intent, transcribes it locally, and injects it into the active workflow or agent pipeline.

## Install

```bash
uv sync
```

## Commands

- **`vox devices`** — List audio input devices (ID, name, host API).
- **`vox test-mic [--device ID] [--seconds N]`** — Record for N seconds, play back, then transcribe and print text. Uses config for model (or defaults: base, float32).

## Configuration

Config file: **`~/.vox/vox.toml`**. Override with `VOX_CONFIG` env. Env overrides: `VOX_HOTKEY`, `VOX_DEVICE_ID`, `VOX_MODEL_SIZE`, `VOX_COMPUTE_TYPE`, `VOX_COMPUTE_DEVICE`, `VOX_INJECTION_MODE`.

## Transcription model (faster-whisper)

- **First run:** The model is downloaded automatically from Hugging Face (size from config, default `base`). No system FFmpeg required (PyAV is used).
- **CPU:** Use `compute_type = "int8"` in config for lower memory and faster inference on CPU.
- **GPU:** Set `compute_device = "cuda"` and `compute_type = "float16"` (or `int8`) in config. Requires CUDA 12 and cuDNN 9. You can set `model_size` (e.g. `small`, `medium`, `large-v3`) for better accuracy.
