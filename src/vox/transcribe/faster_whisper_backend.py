"""faster-whisper backend: load model and transcribe audio to plain text."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np

# faster-whisper has no py.typed in older releases; type-check only.
from faster_whisper import WhisperModel  # type: ignore[import-untyped]

from vox.transcribe.exceptions import TranscriptionError

_NO_SPEECH_DROP_THRESHOLD = 0.6


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


def _resolve_model(
    *,
    model: WhisperModel | None,
    model_size_or_path: str,
    device: str,
    compute_type: str,
) -> WhisperModel:
    """Return ``model`` or load one from the given size/path.

    Args:
        model: Optional pre-loaded model.
        model_size_or_path: Model size or path when ``model`` is None.
        device: "cpu" or "cuda".
        compute_type: "float32" or "int8".

    Returns:
        A WhisperModel ready for inference.

    Raises:
        TranscriptionError: If model load fails.
    """
    if model is not None:
        return model
    try:
        return load_model(model_size_or_path, device=device, compute_type=compute_type)
    except TranscriptionError:
        raise
    except Exception as e:
        raise TranscriptionError(
            f"Failed to load model {model_size_or_path!r}: {e}. "
            "Check model name or path and compute_type (e.g. int8 for CPU)."
        ) from e


def _segments_for_audio(
    model: WhisperModel,
    audio: Path | str | np.ndarray,
) -> Iterator[Any]:
    """Run model.transcribe and return the segment iterator.

    Args:
        model: Loaded Whisper model.
        audio: Path or float32 array (16 kHz mono).

    Returns:
        Iterator of Whisper segment objects.
    """
    if isinstance(audio, (Path, str)):
        path = str(Path(audio).resolve())
        segments_gen, _ = model.transcribe(path)
    else:
        arr = np.asarray(audio, dtype=np.float32)
        if arr.ndim > 1:
            arr = arr[:, 0]
        segments_gen, _ = model.transcribe(arr)
    return iter(segments_gen)


def _join_segment_texts(segments: Iterator[Any]) -> str:
    """Concatenate non-empty segment texts with spaces.

    Args:
        segments: Whisper segment iterator.

    Returns:
        Stripped joined text (may be empty).
    """
    parts = [
        segment.text.strip() for segment in segments if getattr(segment, "text", None)
    ]
    return " ".join(parts).strip()


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
    try:
        resolved = _resolve_model(
            model=model,
            model_size_or_path=model_size_or_path,
            device=device,
            compute_type=compute_type,
        )
        return _join_segment_texts(_segments_for_audio(resolved, audio))
    except TranscriptionError:
        raise


def transcribe_speech_only(
    audio: Path | str | np.ndarray,
    model_size_or_path: str = "base",
    device: str = "cpu",
    compute_type: str = "float32",
    model: WhisperModel | None = None,
) -> str:
    """Transcribe audio, dropping Whisper segments with high no-speech probability.

    Same contract as ``transcribe``, except any segment with
    ``no_speech_prob > 0.6`` is omitted (regardless of average log-probability).

    Args:
        audio: Path to file or array (samples,) or (samples, ch) float32 16 kHz.
        model_size_or_path: Model size or path (used if model is None).
        device: "cpu" or "cuda".
        compute_type: "float32" or "int8" (int8 for CPU saves memory).
        model: Optional pre-loaded WhisperModel to reuse.

    Returns:
        Concatenated text from kept segments (may be empty after filtering).

    Raises:
        TranscriptionError: If model load or inference fails.
    """
    resolved = _resolve_model(
        model=model,
        model_size_or_path=model_size_or_path,
        device=device,
        compute_type=compute_type,
    )
    try:
        kept = (
            segment
            for segment in _segments_for_audio(resolved, audio)
            if getattr(segment, "no_speech_prob", 0.0) <= _NO_SPEECH_DROP_THRESHOLD
        )
        return _join_segment_texts(kept)
    except TranscriptionError:
        raise
    except Exception as e:
        raise TranscriptionError(f"Speech-only transcription failed: {e}.") from e
