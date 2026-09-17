"""Transcription backends (e.g. faster-whisper)."""

from vox.transcribe.exceptions import TranscriptionError
from vox.transcribe.faster_whisper_backend import (
    load_model,
    transcribe,
    transcribe_speech_only,
)

__all__ = [
    "TranscriptionError",
    "load_model",
    "transcribe",
    "transcribe_speech_only",
]
