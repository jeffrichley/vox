"""Continuous dictation package.

Importing this package stays headless-safe: it does not load sounddevice, pynput,
or onnxruntime. Speech detection is loaded via ``load_streaming_vad()``.
"""

from __future__ import annotations
