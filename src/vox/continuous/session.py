"""Continuous dictation session: listen, Pause-Commit, FIFO Injection."""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from vox.continuous.vad import FRAME_SAMPLES, SpeechProbabilityModel

_SAMPLE_RATE = 16_000
_SPEECH_THRESHOLD = 0.5
_SILENCE_THRESHOLD = 0.35
_PAUSE_SECONDS = 1.0
_PREROLL_SECONDS = 0.4
_TRAILING_SPACE = " "


@dataclass
class _PauseDetector:
    """Hysteresis Pause detector driven by a sample-count clock."""

    sample_rate: int = _SAMPLE_RATE
    frame_samples: int = FRAME_SAMPLES
    speech_threshold: float = _SPEECH_THRESHOLD
    silence_threshold: float = _SILENCE_THRESHOLD
    pause_seconds: float = _PAUSE_SECONDS
    preroll_seconds: float = _PREROLL_SECONDS
    _in_speech: bool = False
    _silence_samples: int = 0
    _utterance: list[np.ndarray] = field(default_factory=list)
    _preroll: deque[np.ndarray] = field(default_factory=deque)

    def __post_init__(self) -> None:
        preroll_frames = max(
            1, int(self.preroll_seconds * self.sample_rate / self.frame_samples)
        )
        self._preroll = deque(maxlen=preroll_frames)
        self._pause_samples = int(self.pause_seconds * self.sample_rate)

    def reset(self) -> None:
        """Clear utterance and speech state; keep preroll capacity."""
        self._in_speech = False
        self._silence_samples = 0
        self._utterance.clear()
        self._preroll.clear()

    def ingest(self, frame: np.ndarray, probability: float) -> np.ndarray | None:
        """Ingest one frame; return utterance audio when a Pause completes.

        Args:
            frame: Mono float32 samples of length ``frame_samples``.
            probability: Speech probability for this frame.

        Returns:
            Concatenated utterance audio, or None if still open / idle.
        """
        if not self._in_speech:
            self._preroll.append(frame.copy())
            if probability >= self.speech_threshold:
                self._in_speech = True
                self._silence_samples = 0
                self._utterance = [f.copy() for f in self._preroll]
            return None

        self._utterance.append(frame.copy())
        if probability >= self.speech_threshold:
            self._silence_samples = 0
            return None
        if probability < self.silence_threshold:
            self._silence_samples += self.frame_samples
            if self._silence_samples >= self._pause_samples:
                audio = np.concatenate(self._utterance)
                self._in_speech = False
                self._silence_samples = 0
                self._utterance = []
                self._preroll.clear()
                return audio
        return None

    def flush_pending(self) -> np.ndarray | None:
        """Return pending utterance audio (including partial last frames), if any.

        Returns:
            Pending audio or None when there is no open Utterance.
        """
        if not self._in_speech or not self._utterance:
            self.reset()
            return None
        audio = np.concatenate(self._utterance)
        self.reset()
        return audio


class ContinuousSession:
    """Toggle Continuous dictation; Commit Utterances on Pause via a FIFO worker.

    All collaborators are injected. ``request_toggle`` is non-blocking and safe
    to call from the keyboard hook thread. No stream or speech detector is
    created before the first toggle-on.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        stream_starter: Callable[
            [Callable[[np.ndarray], None], threading.Event],
            None,
        ],
        speech_detector_factory: Callable[[], SpeechProbabilityModel],
        transcriber: Callable[[np.ndarray], str],
        deliverer: Callable[[str], None],
        play_start: Callable[[], None],
        play_end: Callable[[], None],
        reporter: Callable[[str], None] | None = None,
        state_publisher: Callable[[bool], None] | None = None,
        pause_seconds: float = _PAUSE_SECONDS,
    ) -> None:
        """Create an idle session; call ``start`` before toggling.

        Args:
            stream_starter: Runs the long-lived mic stream until stop_event.
            speech_detector_factory: Builds a fresh detector per toggle-on.
            transcriber: Maps utterance audio to text.
            deliverer: Receives committed text (caller adds trailing space here).
            play_start: Start cue (toggle-on).
            play_end: End cue (toggle-off).
            reporter: Optional error/status reporter.
            state_publisher: Optional active-state publisher.
            pause_seconds: Trailing silence that ends an Utterance (must be > 0).
        """
        self._stream_starter = stream_starter
        self._speech_detector_factory = speech_detector_factory
        self._transcriber = transcriber
        self._deliverer = deliverer
        self._play_start = play_start
        self._play_end = play_end
        self._reporter = reporter
        self._state_publisher = state_publisher

        self._lock = threading.Lock()
        self._active = False
        self._started = False
        self._shutting_down = False
        self._detector: SpeechProbabilityModel | None = None
        self._pause = _PauseDetector(pause_seconds=pause_seconds)
        self._listen_stop = threading.Event()
        self._listen_thread: threading.Thread | None = None
        self._commit_queue: deque[np.ndarray | None] = deque()
        self._commit_event = threading.Event()
        self._commit_thread: threading.Thread | None = None
        self._commits_done = threading.Condition()

    def start(self) -> None:
        """Start the FIFO Commit worker; listening begins on first toggle-on."""
        with self._lock:
            if self._started:
                return
            self._started = True
            self._shutting_down = False
            self._commit_thread = threading.Thread(
                target=self._commit_loop,
                name="vox-continuous-commit",
                daemon=True,
            )
            self._commit_thread.start()

    def is_active(self) -> bool:
        """Return True while Continuous dictation is listening.

        Returns:
            Whether the session is currently listening.
        """
        with self._lock:
            return self._active

    def request_toggle(self) -> None:
        """Toggle listening on or off without blocking the caller."""
        with self._lock:
            if self._shutting_down or not self._started:
                return
            if self._active:
                self._listen_stop.set()
                return
            self._active = True
            self._listen_stop = threading.Event()
            self._pause.reset()
            stop_event = self._listen_stop
            self._listen_thread = threading.Thread(
                target=self._listen_loop,
                args=(stop_event,),
                name="vox-continuous-listen",
                daemon=True,
            )
            self._listen_thread.start()
        self._publish(True)

    def ingest_frame(self, frame: np.ndarray) -> None:
        """Process one 512-sample frame (test seam and stream callback).

        Args:
            frame: Mono float32 audio of length ``FRAME_SAMPLES``.
        """
        with self._lock:
            if not self._active or self._detector is None:
                return
            detector = self._detector
        flat = np.asarray(frame, dtype=np.float32).reshape(-1)
        if flat.size != FRAME_SAMPLES:
            if flat.size > FRAME_SAMPLES:
                flat = flat[:FRAME_SAMPLES]
            else:
                padded = np.zeros(FRAME_SAMPLES, dtype=np.float32)
                padded[: flat.size] = flat
                flat = padded
        probability = detector.probability(flat)
        audio = self._pause.ingest(flat, probability)
        if audio is not None:
            self._enqueue_commit(audio)

    def shutdown(self) -> None:
        """Stop listening, drain Commits, and tear down workers. Idempotent."""
        with self._lock:
            if self._shutting_down:
                return
            self._shutting_down = True
            was_active = self._active
            self._listen_stop.set()
            listen_thread = self._listen_thread
        if was_active and listen_thread is not None:
            listen_thread.join(timeout=5.0)
            # listen_loop skips end cue when shutting down; play it here.
            self._play_end()
        with self._lock:
            self._active = False
            self._enqueue_sentinel()
            commit_thread = self._commit_thread
        if commit_thread is not None:
            commit_thread.join(timeout=30.0)
        with self._lock:
            self._commit_thread = None
            self._listen_thread = None
            self._started = False
            self._detector = None
        self._publish(False)

    def _listen_loop(self, stop_event: threading.Event) -> None:
        """Create detector, play start cue, run stream until stop.

        Args:
            stop_event: Set by toggle-off or shutdown to end the stream.
        """
        try:
            detector = self._speech_detector_factory()
            with self._lock:
                self._detector = detector
            self._play_start()
            self._stream_starter(self.ingest_frame, stop_event)
        except Exception as exc:
            if self._reporter is not None:
                self._reporter(str(exc))
        finally:
            pending = self._pause.flush_pending()
            if pending is not None and pending.size > 0:
                self._enqueue_commit(pending)
            with self._lock:
                play_end = self._active and not self._shutting_down
                self._active = False
                self._detector = None
            if play_end:
                self._play_end()
                self._publish(False)

    def _enqueue_commit(self, audio: np.ndarray) -> None:
        """Enqueue utterance audio for the FIFO Commit worker.

        Args:
            audio: Concatenated Utterance samples to transcribe and Inject.
        """
        with self._commits_done:
            self._commit_queue.append(audio)
            self._commit_event.set()

    def _enqueue_sentinel(self) -> None:
        """Signal the Commit worker to exit after draining."""
        with self._commits_done:
            self._commit_queue.append(None)
            self._commit_event.set()

    def _commit_loop(self) -> None:
        """Transcribe and deliver Commits in FIFO order."""
        while True:
            self._commit_event.wait(timeout=0.1)
            while True:
                with self._commits_done:
                    if not self._commit_queue:
                        self._commit_event.clear()
                        break
                    item = self._commit_queue.popleft()
                if item is None:
                    return
                try:
                    text = self._transcriber(item)
                except Exception as exc:
                    if self._reporter is not None:
                        self._reporter(str(exc))
                    continue
                if not text.strip():
                    continue
                self._deliverer(
                    text if text.endswith(_TRAILING_SPACE) else text + _TRAILING_SPACE
                )

    def _publish(self, active: bool) -> None:
        """Publish active state when a publisher is configured.

        Args:
            active: Whether Continuous dictation is listening.
        """
        if self._state_publisher is not None:
            self._state_publisher(active)
