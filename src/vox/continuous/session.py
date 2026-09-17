"""Continuous dictation session: listen, Pause-Commit, FIFO Injection."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from vox.continuous.vad import FRAME_SAMPLES, SpeechProbabilityModel
from vox.hotkey.modifiers import ModifierTracker

_SAMPLE_RATE = 16_000
_SPEECH_THRESHOLD = 0.5
_SILENCE_THRESHOLD = 0.35
_PAUSE_SECONDS = 1.0
_PREROLL_SECONDS = 0.4
_IDLE_MINUTES = 5.0
_MIC_STALL_SECONDS = 2.0
_MIC_STALL_MESSAGE = "Microphone stopped delivering audio."
_MIN_SPEECH_SECONDS = 0.3
_TRAILING_SPACE = " "
_NO_SPEECH_MESSAGE = "No speech detected."
_MODIFIER_WAIT_SECONDS = 2.0
_MODIFIER_WAIT_WARNING = (
    "Modifiers still held after toggle-off; injecting Continuous text anyway."
)


@dataclass(frozen=True)
class ContinuousState:
    """Published Continuous dictation state for UI and notifications.

    Attributes:
        active: Whether Continuous dictation is currently listening.
        error: Optional failure message; None when there is no error.
    """

    active: bool
    error: str | None = None


@dataclass(frozen=True)
class _PendingCommit:
    """Queued Utterance audio plus detected-speech sample count."""

    audio: np.ndarray
    speech_samples: int
    wait_for_modifiers: bool = False


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
    _speech_samples: int = 0
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
        self._speech_samples = 0
        self._utterance.clear()
        self._preroll.clear()

    def ingest(self, frame: np.ndarray, probability: float) -> _PendingCommit | None:
        """Ingest one frame; return a pending Commit when a Pause completes.

        Args:
            frame: Mono float32 samples of length ``frame_samples``.
            probability: Speech probability for this frame.

        Returns:
            Pending Commit audio and speech sample count, or None if still open.
        """
        if not self._in_speech:
            self._preroll.append(frame.copy())
            if probability >= self.speech_threshold:
                self._in_speech = True
                self._silence_samples = 0
                self._speech_samples = self.frame_samples
                self._utterance = [f.copy() for f in self._preroll]
            return None

        self._utterance.append(frame.copy())
        if probability >= self.speech_threshold:
            self._speech_samples += self.frame_samples
            self._silence_samples = 0
            return None
        if probability < self.silence_threshold:
            self._silence_samples += self.frame_samples
            if self._silence_samples >= self._pause_samples:
                audio = np.concatenate(self._utterance)
                speech_samples = self._speech_samples
                self._in_speech = False
                self._silence_samples = 0
                self._speech_samples = 0
                self._utterance = []
                self._preroll.clear()
                return _PendingCommit(audio=audio, speech_samples=speech_samples)
        return None

    def flush_pending(self) -> _PendingCommit | None:
        """Return pending utterance audio (including partial last frames), if any.

        Returns:
            Pending Commit or None when there is no open Utterance.
        """
        if not self._in_speech or not self._utterance:
            self.reset()
            return None
        pending = _PendingCommit(
            audio=np.concatenate(self._utterance),
            speech_samples=self._speech_samples,
        )
        self.reset()
        return pending


class ContinuousSession:
    """Toggle Continuous dictation; Commit Utterances on Pause via a FIFO worker.

    All collaborators are injected. ``request_toggle`` is non-blocking and safe
    to call from the keyboard hook thread. No stream or speech detector is
    created before the first toggle-on.
    """

    def __init__(  # noqa: PLR0913 — injected Continuous collaborators exceed 5 by design
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
        status: Callable[[str], None] | None = None,
        warn: Callable[[str], None] | None = None,
        state_publisher: Callable[[ContinuousState], None] | None = None,
        start_refusal: Callable[[], str | None] | None = None,
        modifier_tracker: ModifierTracker | None = None,
        pause_seconds: float = _PAUSE_SECONDS,
        idle_minutes: float = _IDLE_MINUTES,
        on_idle_auto_off: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        mic_stall_seconds: float = _MIC_STALL_SECONDS,
        min_speech_seconds: float = _MIN_SPEECH_SECONDS,
        modifier_wait_seconds: float = _MODIFIER_WAIT_SECONDS,
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
            status: Optional dim/info notifier (short-sound discard, empty text).
            warn: Optional yellow warning notifier (modifier-wait timeout).
            state_publisher: Optional publisher of active flag plus error.
            start_refusal: Optional gate; return a message to refuse toggle-on.
            modifier_tracker: Shared held-modifier set for toggle-off wait.
            pause_seconds: Trailing silence that ends an Utterance (must be > 0).
            idle_minutes: Silence minutes before auto-off (must be > 0).
            on_idle_auto_off: Optional callback with configured idle minutes.
            clock: Monotonic clock for mic-stall / modifier wait (tests inject).
            sleep: Sleep used while waiting for modifiers (tests inject a fake).
            mic_stall_seconds: No-audio seconds before mic-failure shutdown.
            min_speech_seconds: Discard Utterances with less detected speech.
            modifier_wait_seconds: Max wait for modifiers after user toggle-off.
        """
        self._stream_starter = stream_starter
        self._speech_detector_factory = speech_detector_factory
        self._transcriber = transcriber
        self._deliverer = deliverer
        self._play_start = play_start
        self._play_end = play_end
        self._reporter = reporter
        self._status = status
        self._warn = warn
        self._state_publisher = state_publisher
        self._start_refusal = start_refusal
        self._modifier_tracker = modifier_tracker
        self._idle_minutes = idle_minutes
        self._idle_limit_samples = int(idle_minutes * 60.0 * _SAMPLE_RATE)
        self._on_idle_auto_off = on_idle_auto_off
        self._clock = clock if clock is not None else time.monotonic
        self._sleep = sleep if sleep is not None else time.sleep
        self._mic_stall_seconds = mic_stall_seconds
        self._min_speech_samples = int(min_speech_seconds * _SAMPLE_RATE)
        self._modifier_wait_seconds = modifier_wait_seconds

        self._lock = threading.Lock()
        self._active = False
        self._started = False
        self._shutting_down = False
        self._idle_samples = 0
        self._idle_off_requested = False
        self._user_toggle_off = False
        self._detector: SpeechProbabilityModel | None = None
        self._pause = _PauseDetector(pause_seconds=pause_seconds)
        self._listen_stop = threading.Event()
        self._listen_thread: threading.Thread | None = None
        self._commit_queue: deque[_PendingCommit | None] = deque()
        self._commit_event = threading.Event()
        self._commit_thread: threading.Thread | None = None
        self._commits_done = threading.Condition()
        self._last_audio_at: float | None = None
        self._mic_failure = False

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
        start_failure: str | None = None
        with self._lock:
            if self._shutting_down or not self._started:
                return
            if self._active:
                self._user_toggle_off = True
                self._listen_stop.set()
                return
            refusal = self._start_refusal() if self._start_refusal is not None else None
            if refusal is not None:
                start_failure = refusal
            else:
                self._mic_failure = False
                self._user_toggle_off = False
                self._listen_stop = threading.Event()
                self._pause.reset()
                self._idle_samples = 0
                self._idle_off_requested = False
                self._last_audio_at = None
                stop_event = self._listen_stop
                self._listen_thread = threading.Thread(
                    target=self._listen_loop,
                    args=(stop_event,),
                    name="vox-continuous-listen",
                    daemon=True,
                )
                self._listen_thread.start()
        if start_failure is not None:
            self._report(start_failure)
            self._safe_cue(self._play_end)
            self._publish(ContinuousState(active=False, error=start_failure))

    def ingest_frame(self, frame: np.ndarray) -> None:
        """Process one 512-sample frame (test seam and stream callback).

        Args:
            frame: Mono float32 audio of length ``FRAME_SAMPLES``.
        """
        with self._lock:
            if not self._active or self._detector is None:
                return
            detector = self._detector
            self._last_audio_at = self._clock()
        flat = np.asarray(frame, dtype=np.float32).reshape(-1)
        if flat.size != FRAME_SAMPLES:
            if flat.size > FRAME_SAMPLES:
                flat = flat[:FRAME_SAMPLES]
            else:
                padded = np.zeros(FRAME_SAMPLES, dtype=np.float32)
                padded[: flat.size] = flat
                flat = padded
        probability = detector.probability(flat)
        self._note_idle_sample(probability)
        pending = self._pause.ingest(flat, probability)
        if pending is not None:
            self._enqueue_commit(pending)

    def _note_idle_sample(self, probability: float) -> None:
        """Advance or reset the idle sample clock; auto-off at most once.

        Args:
            probability: Speech probability for the current frame.
        """
        if probability >= _SPEECH_THRESHOLD:
            self._idle_samples = 0
            return
        self._idle_samples += FRAME_SAMPLES
        if self._idle_samples < self._idle_limit_samples:
            return
        with self._lock:
            if (
                not self._active
                or self._idle_off_requested
                or self._shutting_down
                or self._listen_stop.is_set()
            ):
                return
            self._idle_off_requested = True
            self._listen_stop.set()
        if self._on_idle_auto_off is not None:
            try:
                self._on_idle_auto_off(self._idle_minutes)
            except Exception as exc:
                self._report(str(exc))

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
            self._safe_cue(self._play_end)
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
        self._publish(ContinuousState(active=False, error=None))

    def _listen_loop(self, stop_event: threading.Event) -> None:
        """Create detector, announce listening, run stream until stop.

        Args:
            stop_event: Set by toggle-off or shutdown to end the stream.
        """
        start_error: str | None = None
        stall_thread: threading.Thread | None = None
        try:
            detector = self._speech_detector_factory()
            with self._lock:
                if self._shutting_down or stop_event.is_set():
                    return
                self._detector = detector
                self._active = True
            self._safe_cue(self._play_start)
            self._publish(ContinuousState(active=True, error=None))
            stall_thread = threading.Thread(
                target=self._mic_stall_watch,
                args=(stop_event,),
                name="vox-continuous-mic-stall",
                daemon=True,
            )
            stall_thread.start()
            self._stream_starter(self.ingest_frame, stop_event)
        except Exception as exc:
            start_error = str(exc)
            self._report(start_error)
        finally:
            self._enqueue_flushed_pending()
            with self._lock:
                mic_failure = self._mic_failure
                shutting_down = self._shutting_down
                self._active = False
                self._detector = None
            if stall_thread is not None:
                stall_thread.join(timeout=1.0)
            self._publish_listen_end(
                shutting_down=shutting_down,
                mic_failure=mic_failure,
                start_error=start_error,
            )

    def _enqueue_flushed_pending(self) -> None:
        """Flush Pause detector and enqueue, marking toggle-off modifier wait."""
        pending = self._pause.flush_pending()
        if pending is None or pending.audio.size == 0:
            with self._lock:
                self._user_toggle_off = False
            return
        with self._lock:
            wait_mods = self._user_toggle_off
            self._user_toggle_off = False
        if wait_mods:
            pending = _PendingCommit(
                audio=pending.audio,
                speech_samples=pending.speech_samples,
                wait_for_modifiers=True,
            )
        self._enqueue_commit(pending)

    def _publish_listen_end(
        self,
        *,
        shutting_down: bool,
        mic_failure: bool,
        start_error: str | None,
    ) -> None:
        """Play end cue and publish inactive state unless shutting down.

        Args:
            shutting_down: When True, skip end cue/publish (shutdown owns them).
            mic_failure: Whether the session ended due to mic stall.
            start_error: Optional start failure message.
        """
        if shutting_down:
            return
        self._safe_cue(self._play_end)
        error: str | None = None
        if mic_failure:
            error = _MIC_STALL_MESSAGE
        elif start_error is not None:
            error = start_error
        self._publish(ContinuousState(active=False, error=error))

    def _mic_stall_watch(self, stop_event: threading.Event) -> None:
        """Turn Continuous off when no audio frames arrive for too long.

        Args:
            stop_event: Listening stop event shared with the stream.
        """
        while not stop_event.wait(timeout=0.05):
            with self._lock:
                if (
                    not self._active
                    or self._shutting_down
                    or self._mic_failure
                    or self._last_audio_at is None
                ):
                    continue
                stalled = (
                    self._clock() - self._last_audio_at
                ) >= self._mic_stall_seconds
                if not stalled:
                    continue
                self._mic_failure = True
                self._listen_stop.set()
            self._report(_MIC_STALL_MESSAGE)
            return

    def _enqueue_commit(self, pending: _PendingCommit) -> None:
        """Enqueue utterance audio for the FIFO Commit worker.

        Args:
            pending: Utterance samples and detected-speech sample count.
        """
        with self._commits_done:
            self._commit_queue.append(pending)
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
                self._process_commit(item)

    def _process_commit(self, item: _PendingCommit) -> None:
        """Filter, transcribe, optionally wait for modifiers, then deliver.

        Args:
            item: Queued Utterance to Commit.
        """
        if item.speech_samples < self._min_speech_samples:
            seconds = item.speech_samples / _SAMPLE_RATE
            self._announce(f"Discarded short sound ({seconds:.3f} s of speech).")
            return
        try:
            text = self._transcriber(item.audio)
        except Exception as exc:
            self._report(str(exc))
            return
        if not text.strip():
            self._announce(_NO_SPEECH_MESSAGE)
            return
        delivery = text if text.endswith(_TRAILING_SPACE) else text + _TRAILING_SPACE
        if item.wait_for_modifiers:
            self._wait_for_modifiers_or_warn()
        try:
            self._deliverer(delivery)
        except Exception as exc:
            self._report(str(exc))

    def _wait_for_modifiers_or_warn(self) -> None:
        """Block up to the wait window for modifiers to clear; warn on timeout."""
        if self._modifier_tracker is None:
            return
        deadline = self._clock() + self._modifier_wait_seconds
        while self._clock() < deadline:
            if not self._modifier_tracker.any_held():
                return
            self._sleep(0.05)
        if self._warn is not None:
            try:
                self._warn(_MODIFIER_WAIT_WARNING)
            except Exception as exc:
                self._report(str(exc))

    def _announce(self, message: str) -> None:
        """Emit a dim/info status message without raising.

        Args:
            message: User-facing status detail.
        """
        if self._status is None:
            return
        try:
            self._status(message)
        except Exception as exc:
            self._report(str(exc))

    def _report(self, message: str) -> None:
        """Report a failure without raising.

        Args:
            message: User-facing error detail.
        """
        if self._reporter is None:
            return
        try:
            self._reporter(message)
        except Exception:
            return

    def _safe_cue(self, play: Callable[[], None]) -> None:
        """Play a cue; report exceptions without killing the session.

        Args:
            play: Start or end cue callback.
        """
        try:
            play()
        except Exception as exc:
            self._report(str(exc))

    def _publish(self, state: ContinuousState) -> None:
        """Publish active/error state when a publisher is configured.

        Args:
            state: Latest Continuous dictation state.
        """
        if self._state_publisher is None:
            return
        try:
            self._state_publisher(state)
        except Exception as exc:
            self._report(str(exc))
