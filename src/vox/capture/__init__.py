"""Audio capture surface re-exported from the active stream module.

Importing this package is safe in headless environments because `sounddevice`
is still lazy-loaded inside `vox.capture.stream._sd()`, not at import time.
"""

from vox.capture.stream import (
    list_devices,
    play_back,
    record_seconds,
    record_until_stop,
)

__all__ = [
    "list_devices",
    "play_back",
    "record_seconds",
    "record_until_stop",
]
