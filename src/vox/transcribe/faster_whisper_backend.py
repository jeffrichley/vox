"""faster-whisper backend: load model and transcribe audio to plain text."""

from __future__ import annotations

from pathlib import Path

import numpy as np

# faster-whisper has no py.typed in older releases; type-check only.
from faster_whisper import WhisperModel  # type: ignore[import-untyped]

from vox.transcribe.exceptions import TranscriptionError


def load_model(
    model_size_or_path: str = "base",
    device: str = "cpu",
    compute_type: str = "float32",
    download_root: str | None = None,
) -> WhisperModel:
    """Load a WhisperModel by size name or local path.

    Args:
        model_size_or_path: Model size (e.g. tiny, base, small) or path to model dir.
        device: "cpu" or "cuda".
        compute_type: "float32", "int8", etc.
        download_root: Optional directory for downloaded models.

    Returns:
        Loaded WhisperModel.

    Raises:
        TranscriptionError: If model load fails.
    """
    try:
        return WhisperModel(
            model_size_or_path,
            device=device,
            compute_type=compute_type,
            download_root=download_root,
        )
    except Exception as e:
        raise TranscriptionError(
            f"Failed to load model {model_size_or_path!r}: {e}. "
            "Check model name or path and compute_type (e.g. int8 for CPU)."
        ) from e


def transcribe(
    audio: Path | str | np.ndarray,
    model_size_or_path: str = "base",
    device: str = "cpu",
    compute_type: str = "float32",
    model: WhisperModel | None = None,
) -> str:
    """Transcribe audio to plain text.

    Audio must be 16 kHz mono float32 (or a file path that decodes to that).
    If model is provided, model_size_or_path/device/compute_type are ignored.

    Args:
        audio: Path to file or array (samples,) or (samples, ch) float32 16 kHz.
        model_size_or_path: Model size or path (used if model is None).
        device: "cpu" or "cuda".
        compute_type: "float32" or "int8" (int8 for CPU saves memory).
        model: Optional pre-loaded WhisperModel to reuse.

    Returns:
        Concatenated text from all segments (may be empty for silence).

    Raises:
        TranscriptionError: If model load or inference fails (e.g. model not found).
    """
    if model is None:
        try:
            model = load_model(
                model_size_or_path, device=device, compute_type=compute_type
            )
        except TranscriptionError:
            raise
        except Exception as e:
            raise TranscriptionError(
                f"Failed to load model {model_size_or_path!r}: {e}. "
                "Check model name or path and compute_type (e.g. int8 for CPU)."
            ) from e

    if isinstance(audio, (Path, str)):
        path = str(Path(audio).resolve())
        segments_gen, _ = model.transcribe(path)
    else:
        arr = np.asarray(audio, dtype=np.float32)
        if arr.ndim > 1:
            arr = arr[:, 0]
        segments_gen, _ = model.transcribe(arr)

    parts = [
        segment.text.strip()
        for segment in segments_gen
        if getattr(segment, "text", None)
    ]
    return " ".join(parts).strip()
