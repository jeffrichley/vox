# Feature: Continuous Dictation

The following plan should be complete, but it is important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Add **Continuous dictation** as a second listening mode next to **Push-to-talk**. The user taps a separate toggle hotkey (`continuous_hotkey`, default `ctrl+alt+space`) to turn it on, speaks freely, and each **Utterance** is **Committed** after a **Pause** (default 1.0 s of silence detected by the Silero VAD bundled in faster-whisper). Committed text is **Injected** into whatever window has focus at Commit time, with a trailing space. Tapping the toggle again turns it off and Commits any pending Utterance. It turns itself off after `continuous_idle_minutes` (default 5) without detected speech.

This plan also adds clipboard restore for `injection_mode = "clipboard_and_paste"` (both listening modes): the previous clipboard text is put back about 150 ms after the paste.

Terms follow `CONTEXT.md`: Push-to-talk, Continuous dictation, Utterance, Pause, Commit, Injection. Do not use "segment", "flush", "send", "hands-free mode" or "always-on" in user-facing text, config keys, or new public names. faster-whisper's `Segment` objects may be named as such only where the library type is meant.

## User Story

As a Vox user dictating longer text
I want to toggle a mode where I speak freely and each pause commits my words into the focused window
So that I do not have to hold a hotkey for every sentence

## Problem Statement

Vox only supports Push-to-talk (`src/vox/hotkey/register.py:135-284`): the user must hold the hotkey for the whole Utterance, and release both ends the recording and triggers transcription. Dictating paragraphs this way is tiring and error-prone. There is also no clipboard protection: `clipboard_and_paste` overwrites the user's clipboard permanently (`src/vox/commands.py:271-281`).

## Solution Statement

- Put Utterance detection behind a deep, pure, hardware-free seam, `UtteranceDetector` (`src/vox/continuous/utterances.py`). It takes fixed 512-sample frames plus a per-frame speech probability and emits `UtteranceEnded`, `UtteranceDiscarded`, or `IdleTimedOut` events. It owns the Pause length, the pre-roll and tail padding, the minimum-speech drop, and the idle timeout. Its clock is the audio sample count, so tests are deterministic with synthetic arrays.
- Compute speech probabilities with a streaming adapter, `StreamingSileroVad` (`src/vox/continuous/vad.py`), around faster-whisper's bundled Silero model. It carries the LSTM state (`h`, `c`) and the 64-sample context across calls. The public `SileroVADModel.__call__` resets that state on every call, so it cannot be used frame by frame (evidence under Verified Library Facts).
- Run Continuous dictation in `ContinuousDictationSession` (`src/vox/continuous/session.py`). One control/listening thread owns the long-lived `sounddevice` InputStream, the VAD, and the detector. One FIFO commit processor thread transcribes, filters, and Injects in spoken order, mirroring the queue/processor pattern in `src/vox/hotkey/register.py:185-194,257-284`. All collaborators are injected through a dependency dataclass.
- Extend the single pynput listener in `register.py` with an optional `ToggleBinding`. Toggle presses are debounced against key auto-repeat and handed off without blocking. Push-to-talk presses are ignored while Continuous dictation is on. When combos overlap, the most specific one wins.
- Wire everything in `handle_run` (`src/vox/commands.py:286-385`), extend the hotkey reload watcher to `continuous_hotkey`, refactor Injection into a dispatch table, and add clipboard restore.
- Show the state in the Stop window label and the tray tooltip. Expose the three new keys in the settings window, env overrides, `vox.toml.example`, and the README.

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: High
**Primary Systems Affected**: `src/vox/config.py`, `src/vox/commands.py`, `src/vox/hotkey/register.py`, `src/vox/capture/stream.py`, `src/vox/transcribe/faster_whisper_backend.py`, `src/vox/inject/clipboard.py`, new `src/vox/continuous/*`, `src/vox/gui/{stop_window,tray,settings_window}.py`, docs
**Dependencies**: No new dependencies. Existing `faster-whisper` (Silero VAD asset + onnxruntime transitive dep), `sounddevice`, `pynput`, `pyperclip`, `numpy`. **Dependency spec change:** raise the floor to `faster-whisper>=1.2.1,<2` (rationale in Phase 4).

## Traceability Mapping

No SI/DEBT mapping for this feature.

(`docs/dev/` contains only `status.md`; there is no roadmap or debt tracker with SI/DEBT ids.)

## Branch Setup

Branch naming must follow the plan filename:
- Plan: `.ai/PLANS/<NNN>-<feature>.md`
- Branch: `feat/<NNN>-<feature>`

The branch `feat/005-continuous-dictation` already exists and is checked out at plan time. The commands below are idempotent.

```bash
PLAN_FILE=".ai/PLANS/005-continuous-dictation.md"
PLAN_SLUG="$(basename "$PLAN_FILE" .md)"
BRANCH_NAME="feat/${PLAN_SLUG}"
git show-ref --verify --quiet "refs/heads/${BRANCH_NAME}" \
  && git switch "${BRANCH_NAME}" \
  || git switch -c "${BRANCH_NAME}"
```

PowerShell equivalent:

```powershell
$planFile = ".ai/PLANS/005-continuous-dictation.md"
$planSlug = [System.IO.Path]::GetFileNameWithoutExtension($planFile)
$branchName = "feat/$planSlug"
git show-ref --verify --quiet "refs/heads/$branchName"
if ($LASTEXITCODE -eq 0) {
    git switch $branchName
} else {
    git switch -c $branchName
}
```

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `CONTEXT.md` - Domain glossary. All new names and user-facing strings use its terms.
- `.ai/RULES.md` - Commit per phase, no new deps without rationale, no new suppression comments, dispatch tables over `if/elif`, fail-fast validation, warnings are defects.
- `src/vox/hotkey/register.py:18-54` - `_MODIFIER_MAP` / `_MODIFIER_TO_LOGICAL` / `_normalize_modifier`. Modifier aliasing to mirror in config-side combo normalization.
- `src/vox/hotkey/register.py:57-114` - `_parse_hotkey`, `_key_matches`. `"ctrl+alt+space"` parses to `({ctrl, alt}, Key.space)` via `getattr(keyboard.Key, "space")` (line 86).
- `src/vox/hotkey/register.py:135-245` - `_PushToTalkSession` state, `_processor_loop` (185-194), `_on_press` (196-222, subset modifier match at 211), `_on_release` (224-245).
- `src/vox/hotkey/register.py:247-329` - `run()` listener/watcher/processor lifecycle and `run_push_to_talk_loop` public signature (already `# noqa: PLR0913`).
- `src/vox/capture/stream.py:13-45` - `InputStreamProtocol`, `SoundDeviceProtocol`, lazy `_sd()` (keeps `vox --help` PortAudio-free).
- `src/vox/capture/stream.py:146-201` - `record_until_stop`: InputStream callback pattern to mirror for the long-lived stream.
- `src/vox/capture/stream.py:93-96` - Error-wrapping style (`RuntimeError` with actionable text).
- `src/vox/transcribe/faster_whisper_backend.py:49-101` - `transcribe()`: array path (91-94) and segment join (96-101). Push-to-talk keeps using it unchanged.
- `src/vox/commands.py:26-79` - `HotkeyModuleProtocol` and lazy `_run_push_to_talk_loop` (positional call contract).
- `src/vox/commands.py:82-119` - `_spawn_hotkey_reload_watcher` (must handle `continuous_hotkey`).
- `src/vox/commands.py:180-230` - `_warn_on_cue_failure`, `_build_cue_callbacks` (reuse for toggle on/off cues).
- `src/vox/commands.py:233-283` - `_build_audio_handler`. The `if injection_mode ...` chain at 263-281 becomes a dispatch table.
- `src/vox/commands.py:286-385` - `handle_run`: config read (301-308), hardcoded `sample_rate = 16000`, `channels = 1` (316-317), cue preload (318), panel (326-333), terminal direct path (336-347), reload loop (349-385).
- `src/vox/inject/clipboard.py:8-34` - `InjectError`, `set_clipboard` wrapping `pyperclip.copy`.
- `src/vox/inject/keystroke.py:11-50` - `paste_into_focused` (`controller.pressed(Key.ctrl)`), `type_into_focused`.
- `src/vox/inject/__init__.py:1-6` - Export surface.
- `src/vox/config.py:58-64` - `ALLOWED_INJECTION_MODES`.
- `src/vox/config.py:165-226` - `_ENV_OVERRIDES`, `_apply_cue_volume_env` (200-212), `_apply_env_overrides`.
- `src/vox/config.py:229-238` - `_CONFIG_KEYS` (serialization order; append new keys at the end so `tests/unit/test_config.py:318-338` stays green).
- `src/vox/config.py:334-438` - Validators and `validate_config`: field-prefixed `ValueError` wrapped into `ConfigError`.
- `src/vox/config.py:563-577` - `_float_default`.
- `src/vox/config.py:690-735` - `get_env_override_fields`, `get_config` output dict.
- `src/vox/audio_cues.py:296-330` - `CuePlayer.play_start/play_end` are non-blocking (`blocking=False` at 325).
- `src/vox/gui/stop_window.py:89-164` - Stop window: label at line 121 (`"Push-to-talk running."`), `root.after` polling pattern at 140-145, worker start at 57-86.
- `src/vox/gui/tray.py:92-156` - Tray: `run_worker` (114-121), `pystray.Icon("vox", image, "Vox — push-to-talk", menu=menu)` at 145.
- `src/vox/gui/settings_window.py:45-54` - `DEFAULT_SETTINGS`; `83-93` `RESTART_REQUIRED_FIELDS`; `274-296` `commit_text`/`commit_choice`; `403-430` `_persist_updates`.
- `src/vox/gui/settings_window.py:436-540` - Window build and Recording section (hotkey capture binds at 516-522).
- `src/vox/gui/settings_window.py:750-836` - Hotkey capture handlers (to extract into a reusable per-field helper); `862-876` `_on_restore_defaults`.
- `src/vox/cli.py:89-122` - `_run_impl` lazy GUI boundary (no change expected; keep headless-safe imports).
- `tests/conftest.py:30-34` - `requires_audio` fixture (not needed by new tests; new tests must be hardware-free).
- `tests/unit/test_hotkey.py:104-138` - Pattern for driving `_PushToTalkSession._on_press/_on_release` with `keyboard.Key`/`KeyCode` and patched `threading.Thread`.
- `tests/unit/test_capture.py:62-116` - Pattern for patching `vox.capture.stream._sd` and invoking the captured InputStream callback.
- `tests/unit/test_commands.py:199-238` - Pattern for capturing `on_audio` from `handle_run` via patched `_run_push_to_talk_loop`.
- `tests/unit/test_commands.py:362-407` - `clipboard_and_paste` paste-failure test (must patch the new clipboard snapshot).
- `tests/unit/test_commands.py:583-658` - Reload-watcher fake with keyword-only signature (must be updated for the new watcher parameter).
- `tests/unit/test_config.py:409-431,554-571` - Env-override metadata and `get_config` defaults tests to mirror.
- `tests/unit/test_settings_window.py:20-91` - `FakeScheduler` and `_build_controller` helpers to mirror for settings tests.
- `pyproject.toml` - drill-sergeant (`enforce_markers`, strict AAA, `max_file_length = 350`), ruff `D`/`ANN` apply to tests too, mypy strict, coverage `fail_under = 85` with `src/vox/gui/*` omitted, xenon `-b B -m A -a A`.
- `.github/workflows/ci.yml` - CI = `just quality-check` + `just test-cov` + `diff-cover --fail-under=80` on changed lines (GUI files are omitted from coverage, so put logic in covered modules).
- `README.md:48-101`, `vox.toml.example`, `docs/dev/status.md` - Docs surfaces for Phase 8.

### New Files to Create

- `src/vox/continuous/__init__.py` - Headless-safe package exports (no sounddevice/pynput/onnxruntime import at import time).
- `src/vox/continuous/utterances.py` - `DetectorSettings`, `UtteranceDetector`, `FrameBuffer`, event dataclasses. Pure.
- `src/vox/continuous/vad.py` - `StreamingSileroVad`, `SpeechProbabilityModel` protocol, `VadUnavailableError`, `load_streaming_vad()`.
- `src/vox/continuous/modifiers.py` - `ModifierTracker` (thread-safe held-modifier set with `wait_released`).
- `src/vox/continuous/keystate.py` - `physical_modifier_state()`: Windows `GetAsyncKeyState` reader (ctypes) used to heal stale modifier state; `None` on other platforms.
- `src/vox/continuous/state.py` - `ContinuousState`, `ToggleBinding`, `continuous_refusal()`, `describe_window_label()`, `describe_tray_title()`, `describe_tray_notification()`.
- `src/vox/continuous/session.py` - `ContinuousSettings`, `ContinuousDependencies`, `ContinuousDictationSession`.
- `tests/unit/test_config_continuous.py`
- `tests/unit/test_clipboard_restore.py`
- `tests/unit/test_utterance_detector.py`
- `tests/unit/test_streaming_vad.py`
- `tests/unit/test_transcribe_speech.py`
- `tests/unit/test_capture_input_stream.py`
- `tests/integration/test_streaming_vad_model.py`
- `tests/unit/conftest.py` - Fixtures/fakes shared by the session tests (fake stream factory, scripted VAD, recorder of delivered text).
- `tests/unit/test_continuous_state.py`
- `tests/unit/test_continuous_session_toggle.py`
- `tests/unit/test_continuous_session_commits.py`
- `tests/unit/test_continuous_session_failures.py`
- `tests/unit/test_hotkey_toggle.py`
- `tests/unit/test_commands_continuous.py`
- `tests/unit/test_settings_continuous_fields.py`

### Existing Files To Update

- `pyproject.toml`, `uv.lock` (faster-whisper floor only)
- `src/vox/config.py`
- `src/vox/inject/clipboard.py`, `src/vox/inject/__init__.py`
- `src/vox/commands.py`
- `src/vox/capture/stream.py`, `src/vox/capture/__init__.py`
- `src/vox/transcribe/faster_whisper_backend.py`, `src/vox/transcribe/__init__.py`
- `src/vox/hotkey/register.py`
- `src/vox/gui/stop_window.py`, `src/vox/gui/tray.py`, `src/vox/gui/settings_window.py`
- `tests/unit/test_commands.py` (two targeted edits only), `tests/unit/test_inject.py`
- `README.md`, `vox.toml.example`, `docs/dev/status.md`

### Verified Library Facts (read from installed source, not memory)

**Provenance caveat:** at plan time the repo has **no `.venv`** (`E:\workspaces\ai\vox\.venv` does not exist). Evidence was read from other installs of the **same versions pinned in `uv.lock`**:
- faster-whisper **1.2.1** (`uv.lock:577-578`) at `E:\workspaces\ai\test_voice\.venv\Lib\site-packages\faster_whisper\`
- pyperclip **1.11.0** (`uv.lock:1595-1596`) at `E:\workspaces\ai\agents\agent_core\.venv\Lib\site-packages\pyperclip\__init__.py`
- faster-whisper **1.1.0** (for API-drift comparison) at `E:\workspaces\ai\audio_hunter\.venv\Lib\site-packages\faster_whisper\vad.py`

pynput 1.8.1, sounddevice, and pystray are not installed anywhere on this machine. Facts about them come from the existing repo usage plus the official docs and are marked **VERIFY-IN-VENV**. After `uv sync`, re-confirm every line reference below under `.venv/Lib/site-packages/...`. They should be identical for the same versions.

**Silero VAD in faster-whisper 1.2.1 (`faster_whisper/vad.py`):**
- `VadOptions` (14-42): `threshold=0.5` (37), `neg_threshold=None` (38), `min_speech_duration_ms=0` (39), `min_silence_duration_ms=2000` (41), `speech_pad_ms=400` (42). When `neg_threshold` is None, `get_speech_timestamps` uses `max(threshold - 0.15, 0.01)` (94-95).
- `get_speech_timestamps(audio, vad_options=None, sampling_rate=16000, **kwargs) -> List[dict]` (45-183) is offline only. It pads the whole array and calls the model once (84-89) with a fixed `window_size_samples = 512` (70). It does not stream.
- `get_vad_model()` is `@functools.lru_cache` and returns `SileroVADModel(<assets>/silero_vad_v6.onnx)` (288-292). The asset ships inside the wheel, so nothing is downloaded.
- `SileroVADModel.__init__(path)` imports `onnxruntime` lazily, raising `RuntimeError` if it is missing (297-302). It stores `self.session = onnxruntime.InferenceSession(...)` with CPU provider and single-threaded options (304-314).
- `SileroVADModel.__call__(audio, num_samples=512, context_size_samples=64)` (316-351) asserts 1-D input with length a multiple of 512 (319-322). **It resets `h` and `c` to zeros on every call (324-325)** and zeroes the context of the first window (331-335). It then runs `self.session.run(None, {"input": batch, "h": h, "c": c})`, carrying `h`/`c` across encoder batches only within that single call (343-346). **State is not kept across calls.**
- ONNX session I/O (probed at runtime via `session.get_inputs()/get_outputs()`): inputs `input [seq_len, 576]`, `h [1,1,128]`, `c [1,1,128]`; outputs `speech_probs [seq_len]`, `hn [1,1,128]`, `cn [1,1,128]`.
- **Streaming equivalence probe** (scratchpad script, same 1.2.1 install, synthetic 4.7 s signal, 146 windows): running `session.run` one 512-sample window at a time, prepending the previous window's last 64 samples and carrying `h`/`c`, produced **max abs diff 0.0** against the single batched `model(audio)` call. Calling the public `model(frame)` per 512-sample frame differed by **up to 0.523**, so it is unusable. Per-window CPU cost was **~0.16 ms** (≈5 ms CPU per second of audio).
- **API drift:** faster-whisper 1.1.0 uses a different design: `state = np.zeros((2, batch, 128))`, separate `encoder_session`/`decoder_session`, and a `"state"` input (`audio_hunter` vad.py:290,304,309-310). The current spec `faster-whisper>=1.0.0,<2` therefore allows versions this adapter cannot drive. Raise the floor to `>=1.2.1` and add a runtime input-name contract check.

**Whisper transcription (`faster_whisper/transcribe.py`, 1.2.1):**
- `Segment` dataclass (47-67) has `avg_logprob: float` (55), `compression_ratio: float` (56), `no_speech_prob: float` (57).
- `WhisperModel.transcribe(audio, language=None, ..., log_prob_threshold=-1.0 (768), no_speech_threshold=0.6 (769), ..., vad_filter=False (782), ...)` returns `(Iterable[Segment], TranscriptionInfo)` (747-791). The iterable is a lazy generator.
- The built-in skip drops a 30 s window only if `no_speech_prob > no_speech_threshold` **and** `avg_logprob <= log_prob_threshold` (1215-1235). Hallucinations with high `no_speech_prob` but moderate `avg_logprob` therefore still come through. Each yielded `Segment` carries the window's `no_speech_prob` (1364).
- Junk filter decision: drop any yielded segment whose `no_speech_prob > 0.6`, regardless of `avg_logprob`. `0.6` mirrors the library's own default `no_speech_threshold` (769); the strict `>` mirrors the comparison at line 1217.

**pyperclip 1.11.0 (Windows):**
- `paste_windows()` returns `""` when the clipboard holds no `CF_UNICODETEXT` (448-456), which includes images and files. Empty and non-text clipboards are indistinguishable.
- `copy_windows(text)` always calls `EmptyClipboard` (431) and only sets data `if text:` (433). Restoring `""` would wipe the clipboard.
- Decision: restore only non-empty text snapshots. Document that non-text clipboard contents cannot be preserved.

**sounddevice (docs, VERIFY-IN-VENV):** `InputStream(samplerate, blocksize, device, channels, dtype, callback, finished_callback, ...)`; callback `callback(indata, frames, time, status)`. A stream becomes inactive if the callback raises or `stop()`/`abort()` is called. The repo already uses `InputStream(device=, channels=, samplerate=, dtype="float32", callback=)` (`src/vox/capture/stream.py:186-192`).

**pynput (docs + repo usage, VERIFY-IN-VENV):** `keyboard.Listener(on_press, on_release, suppress=False)` calls back on the listener thread with `(key)` (repo: `register.py:276-281`). The Windows implementation is a low-level hook: callbacks must return quickly, so never do stream/VAD/model work in them. `Controller.pressed(Key.ctrl)` is already used (`inject/keystroke.py:19`).

**pystray (VERIFY-IN-VENV):** confirm `pystray.Icon.title` is a settable property that updates the tooltip (`.venv/Lib/site-packages/pystray/_base.py`). The Windows tooltip buffer is 128 wide chars, so truncate the title to ≤120 chars.

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [faster-whisper v1.2.1 `vad.py`](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/vad.py)
  - Section: `SileroVADModel.__call__`, `get_vad_model`
  - Why: the streaming adapter replicates its context/state handling per window
- [faster-whisper v1.2.1 `transcribe.py`](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py)
  - Section: `Segment`, `WhisperModel.transcribe`, `generate_segments` no-speech skip
  - Why: junk filter fields and thresholds
- [python-sounddevice Streams API](https://python-sounddevice.readthedocs.io/en/latest/api/streams.html#sounddevice.InputStream)
  - Section: `InputStream`, callback signature, `blocksize`
  - Why: long-lived callback stream for Continuous dictation
- [pynput keyboard monitoring](https://pynput.readthedocs.io/en/latest/keyboard.html#monitoring-the-keyboard)
  - Section: Listener callbacks and threading
  - Why: toggle handling must be non-blocking
- [Silero VAD](https://github.com/snakers4/silero-vad)
  - Section: streaming usage (state carried across 512-sample chunks at 16 kHz)
  - Why: confirms the per-window streaming model the adapter implements

### Patterns to Follow

**Naming Conventions:**
- snake_case modules and functions, PascalCase classes, `_private` helpers; module constants in `UPPER_SNAKE` (`_HOTKEY_RELOAD_POLL_SECONDS` in `commands.py:44`).
- Flat TOML config keys; env overrides `VOX_<KEY_UPPER>`.
- Glossary terms: `Utterance*`, `Pause`, `Commit`, `Injection`, `ContinuousDictation*`.

**Error Handling:**
- Validation raises `ValueError("<field>: <reason>")`, and `validate_config` wraps it into `ConfigError` (`config.py:414-438`).
- Runtime failures print Rich markup and keep running: `[red]Transcription error:[/red]`, `[yellow]Paste failed:[/yellow]`, `[dim]No speech detected.[/dim]`, `[green]Injected.[/green]` (`commands.py:255-281`).
- Wrap third-party exceptions into domain errors with actionable text (`capture/stream.py:93-96`, `faster_whisper_backend.py:42-46`).
- No silent failures. Every drop, refusal, or failure prints a line and, where a GUI surface exists, updates it.

**Lazy import boundary:**
- Hardware and GUI modules are imported lazily through `import_module` + `Protocol` casts (`capture/stream.py:37-45`, `audio_cues.py:146-161`, `commands.py:69`). New code that needs `faster_whisper.vad` must do the same. That also avoids adding `# type: ignore[import-untyped]`.

**Dispatch over if/elif (RULES):**
- Injection by mode uses `dict[str, Callable]`. Continuous refusal by mode uses a dict. Hotkey press routing uses the best-matching binding, not a growing `if` chain.

**Threading:**
- Listener callbacks only update state and enqueue work (`register.py:196-245`).
- FIFO `Queue` with a `None` sentinel, drained in `finally` (`register.py:185-194,282-284`).

**Testing:**
- Every test has a class-level or function-level `@pytest.mark.unit` or `@pytest.mark.integration`, a docstring, type annotations, and strict AAA comments `# Arrange - ...`, `# Act - ...`, `# Assert - ...` (each description ≥10 chars).
- Test files ≤350 lines. **Do not** add `# drill-sergeant: file-length ignore` to new files; split them instead.
- Use `tmp_path`, `mock.patch.dict(os.environ, ...)`, and fakes; no hardware and no Whisper model in unit tests.

---

## IMPLEMENTATION PLAN

Use markdown checkboxes. Update them live as tasks complete, and append evidence under `## Execution Report` after each phase.

- [ ] Phase 1: Config keys and validation
- [ ] Phase 2: Clipboard restore and Injection dispatch
- [ ] Phase 3: Utterance detector core
- [ ] Phase 4: Streaming VAD, speech-only transcription, long-lived input stream
- [ ] Phase 5: Continuous dictation session runtime
- [ ] Phase 6: Toggle hotkey and `handle_run` wiring
- [ ] Phase 7: GUI surfaces (Stop window, tray, settings)
- [ ] Phase 8: Docs and status (docs-only commit)

### Scope Lock (applies to all phases)

**In scope:** only items 1-11 of the agreed design, as restated in the Feature Description.

**Non-goals (never implement in this plan):** AI cleanup or formatting of text; smart leading-space or lowercasing; foreground-window tracking or refocus; double-tap activation; floating status bar; cancel gesture; force-commit key; hotkey suppression; phrase blocklist; splitting Utterances on window switch; per-Commit cue; max Utterance length; new configurable VAD or no-speech thresholds; tray notifications or popups; changing Push-to-talk output text.

---

### Phase 1: Config keys and validation

Add `continuous_hotkey`, `continuous_pause_seconds`, and `continuous_idle_minutes` with defaults, env overrides, serialization, override metadata, and fail-fast validation, including a collision check against `hotkey`.

#### Intent Lock

- Source of truth:
  - `src/vox/config.py:165-238` (env overrides, key order), `334-438` (validators), `690-735` (`get_env_override_fields`, `get_config`)
  - `src/vox/hotkey/register.py:18-26,57-94` (modifier aliases and parse semantics to mirror, without importing pynput)
  - `.ai/RULES.md` Non-Negotiables (no silent fallback for invalid fields)
- Must:
  - Defaults as module constants in `config.py`: `DEFAULT_CONTINUOUS_HOTKEY = "ctrl+alt+space"`, `DEFAULT_CONTINUOUS_PAUSE_SECONDS = 1.0`, `DEFAULT_CONTINUOUS_IDLE_MINUTES = 5.0`
  - Env overrides: `VOX_CONTINUOUS_HOTKEY` (string, stripped), `VOX_CONTINUOUS_PAUSE_SECONDS`, `VOX_CONTINUOUS_IDLE_MINUTES` (float parse; keep the raw string on parse failure so validation errors name the field)
  - Replace the cue-volume-only float env helper with a table-driven helper shared by `cue_volume` and both new numeric keys. `get_env_override_fields` iterates the same table.
  - Validation: `continuous_hotkey` optional non-empty string. Both numeric keys optional, real numbers (reject `bool`), finite, `> 0`. **Collision:** the normalized combo of the effective `continuous_hotkey` (raw value or default) must differ from the normalized `hotkey`. The message names both keys and the combo, and tells the user to change `continuous_hotkey`.
  - Normalization is pure: split on `+`, strip, lowercase, alias `control→ctrl`, `meta|win→cmd`, compare `(frozenset(modifiers), trigger)`
  - Append the new keys to the end of `_CONFIG_KEYS`
  - `get_config()` returns the three keys with defaults
- Must Not:
  - Import pynput or `vox.hotkey` from `config.py` (headless `vox --help` safety, `cli.py:103-106`)
  - Silently coerce an invalid numeric value to the default
  - Add bounds beyond `> 0` (not agreed)
- Provenance map:
  - Key names and defaults → agreed design items 1, 2, 7
  - Collision rule → agreed design item 11
  - Error style → `config.py:334-348,394-411`
- Acceptance gates:
  - `uv run pytest tests/unit/test_config_continuous.py tests/unit/test_config.py -q`
  - `just lint-check && just types`

**Acceptance Criteria:**
- `get_config()` includes the three keys with defaults when unset
- Env overrides apply and appear in `get_env_override_fields()`
- `hotkey = "alt+ctrl+space"` with no `continuous_hotkey` raises `ConfigError` mentioning `continuous_hotkey`
- Pause `0`, negative, `true`, `"abc"`, and `inf` are rejected with field-specific messages
- Existing config tests stay green unchanged

**Non-Goals:** migrating existing user config files; upper bounds; making `hotkey` optional.

**Tasks:**
- [ ] Add default constants, env table entries, float env helper refactor
- [ ] Add `_normalize_hotkey_combo`, `_validate_continuous_hotkey`, `_validate_positive_number`
- [ ] Extend `_CONFIG_KEYS`, `get_env_override_fields`, `get_config`, docstrings (darglint full)
- [ ] Create `tests/unit/test_config_continuous.py`
- [ ] Commit: `feat(config): add continuous dictation settings`

### Phase 2: Clipboard restore and Injection dispatch

Refactor Injection in `commands.py` into a dispatch table and add clipboard restore for `clipboard_and_paste`. This applies to Push-to-talk now, and Continuous dictation reuses it in Phase 6.

#### Intent Lock

- Source of truth:
  - `src/vox/commands.py:233-283`
  - `src/vox/inject/clipboard.py:14-34`
  - pyperclip facts under Verified Library Facts
  - `.ai/RULES.md` Dispatch Pattern
- Must:
  - Add `get_clipboard() -> str` to `inject/clipboard.py` (wraps `pyperclip.paste`, raises `InjectError` like `set_clipboard`) and export it from `vox.inject`
  - In `commands.py`: `_INJECTORS: dict[str, Callable[[Console, str], None]]` with `_inject_clipboard`, `_inject_clipboard_and_paste`, `_inject_type`, plus `_inject_text(console, text, injection_mode)`. `_build_audio_handler` resolves the injector **once at build time**, so an unknown mode raises `ConfigError` at startup rather than on first use.
  - Keep existing console messages byte-identical: `Typing error`, `Clipboard error`, `Paste failed`, `Injected.`
  - `_inject_clipboard_and_paste`: snapshot `get_clipboard()` **before** `set_clipboard(text)`, then paste. If the paste succeeds and the snapshot is non-empty, call `_pause_before_clipboard_restore()` (sleeps `_CLIPBOARD_RESTORE_DELAY_SECONDS = 0.15`). Restore only if `get_clipboard() == text`, so text the user copied meanwhile is not clobbered.
  - Any `InjectError` during snapshot or restore prints `[yellow]Clipboard restore skipped:[/yellow] <e>` and Injection still counts as done
  - Do not restore when the paste failed. The transcription stays on the clipboard so the user can paste manually.
  - Run the restore synchronously on the calling (processor) thread so the next Commit cannot interleave
- Must Not:
  - Change `clipboard` or `type` mode behavior
  - Use `threading.Timer` (breaks ordering across consecutive Commits)
  - Restore an empty snapshot (would `EmptyClipboard`, pyperclip 431-433)
  - Patch `time.sleep` globally in tests; patch `vox.commands._pause_before_clipboard_restore`
- Provenance map:
  - 150 ms delay and both modes → agreed design item 5
  - Text-only limitation → pyperclip 448-456
- Acceptance gates:
  - `uv run pytest tests/unit/test_clipboard_restore.py tests/unit/test_inject.py tests/unit/test_commands.py -q`
  - `just lint-check && just types && just complexity`

**Acceptance Criteria:**
- `clipboard_and_paste` sequence: snapshot → set → paste → pause → verify → restore
- Restore skipped when snapshot empty, paste failed, or clipboard changed by someone else
- Snapshot/restore errors surface as yellow warnings, never exceptions
- All pre-existing `on_audio` tests pass (the one clipboard_and_paste test updated only to patch the snapshot)

**Non-Goals:** preserving non-text clipboard formats; configurable delay; new dependencies (e.g. pywin32).

**Tasks:**
- [ ] Add `get_clipboard` + export + tests in `tests/unit/test_inject.py`
- [ ] Refactor Injection into `_INJECTORS` dispatch in `commands.py`
- [ ] Implement restore helper and `_pause_before_clipboard_restore`
- [ ] Update `tests/unit/test_commands.py:362-407` to also patch `vox.commands.get_clipboard` and `vox.commands._pause_before_clipboard_restore`
- [ ] Create `tests/unit/test_clipboard_restore.py`
- [ ] Commit: `feat(inject): restore previous clipboard text after paste`

### Phase 3: Utterance detector core

Build the pure seam that turns frames and speech probabilities into Utterance boundaries.

#### Intent Lock

- Source of truth:
  - Silero defaults `vad.py:37-42,70,94-95` (threshold 0.5, neg 0.35, pad 400 ms, 512-sample window)
  - Agreed design items 2, 6, 7
- Must:
  - Constants: `SAMPLE_RATE = 16_000`, `FRAME_SAMPLES = 512`
  - `DetectorSettings(pause_seconds, idle_minutes, min_speech_seconds=0.3, pad_seconds=0.4, speech_threshold=0.5, silence_threshold=0.35)` is frozen, and `__post_init__` raises `ValueError` for non-positive durations or thresholds outside `0 < silence_threshold <= speech_threshold <= 1`
  - `UtteranceDetector.feed(frame, speech_prob) -> list[DetectorEvent]`: `frame` must be 1-D float32 of length `FRAME_SAMPLES`, else `ValueError`
  - Hysteresis per frame: `prob >= speech_threshold` → speaking; `prob < silence_threshold` → not speaking; otherwise keep the previous state
  - While idle, keep a pre-roll `deque(maxlen=pad_frames)`. The first speaking frame starts an Utterance containing pre-roll plus that frame.
  - Inside an Utterance: append every frame; count `speech_frames`; count `trailing_silence_frames` (reset on speaking)
  - Pause reached when `trailing_silence_frames >= ceil(pause_seconds * SAMPLE_RATE / FRAME_SAMPLES)`. End the Utterance with audio = frames up to the last speaking frame plus `min(pad_frames, trailing silence)` frames.
  - If `speech_frames * FRAME_SAMPLES / SAMPLE_RATE < min_speech_seconds`, emit `UtteranceDiscarded(speech_seconds)`; otherwise emit `UtteranceEnded(audio, speech_seconds)`
  - Idle: `samples_since_speech` resets on any speaking frame. When not in an Utterance and it reaches `idle_minutes * 60 * SAMPLE_RATE`, emit `IdleTimedOut(idle_seconds)` **once**.
  - `flush(tail: np.ndarray | None = None) -> list[DetectorEvent]` ends a pending Utterance on toggle-off. It appends the `< FRAME_SAMPLES` tail, applies the min-speech rule, and resets.
  - `FrameBuffer.push(block) -> list[np.ndarray]` re-chunks arbitrary 1-D blocks into 512-sample frames; `remainder()` returns the leftover
- Must Not:
  - Use wall-clock time (the audio sample count is the clock)
  - Import numpy-incompatible heavy deps, VAD, sounddevice, or threads
  - Add a max Utterance length
- Provenance map:
  - Pre-roll/tail pad 0.4 s → `VadOptions.speech_pad_ms=400` (`vad.py:42`)
  - Hysteresis → `vad.py:94-95,103-152`
  - Min speech 0.3 s, pause default, idle default → agreed design
- Acceptance gates:
  - `uv run pytest tests/unit/test_utterance_detector.py -q`
  - `uv run pytest --cov=src/vox/continuous --cov-report=term-missing tests/unit/test_utterance_detector.py -q` (utterances.py ≥95% line coverage)
  - `just types && just complexity`

**Acceptance Criteria:**
- 20 speaking frames followed by 32 silent frames (pause 1.0 s) yields exactly one `UtteranceEnded` whose audio length equals (pre-roll + 20 + pad) frames × 512
- 9 speaking frames (0.288 s) → `UtteranceDiscarded`; 10 frames (0.32 s) → `UtteranceEnded`
- Probabilities in `[0.35, 0.5)` keep the previous state (no premature Pause)
- Two Utterances separated by a Pause produce two events in order
- `flush()` ends a pending Utterance; `flush()` when idle returns `[]`
- `IdleTimedOut` is emitted once after the configured idle samples without speech

**Non-Goals:** VAD inference, threading, transcription.

**Tasks:**
- [ ] Create `src/vox/continuous/__init__.py` (exports detector types only for now)
- [ ] Create `src/vox/continuous/utterances.py`
- [ ] Create `tests/unit/test_utterance_detector.py`
- [ ] Commit: `feat(continuous): add utterance detector`

### Phase 4: Streaming VAD, speech-only transcription, long-lived input stream

#### Intent Lock

- Source of truth:
  - Verified Library Facts (vad.py 288-351, ONNX I/O, probe, 1.1.0 drift; transcribe.py 47-67, 747-791, 1215-1235, 1364)
  - `src/vox/capture/stream.py:37-45,146-201`
  - `src/vox/transcribe/faster_whisper_backend.py:49-101`
- Must:
  - **Dependency spec:** `pyproject.toml` `faster-whisper>=1.2.1,<2`, then `uv lock`. Rationale: the adapter relies on `SileroVADModel.session` and ONNX inputs `input/h/c`, which exist in 1.2.1 and differ in 1.1.0. The lock already resolves 1.2.1, so the only effect is excluding incompatible installs. No new package.
  - `StreamingSileroVad(session)`: on construction, verify `{i.name for i in session.get_inputs()} == {"input", "h", "c"}` or raise `VadUnavailableError` naming the required faster-whisper version. Initialize `h = c = zeros((1,1,128), float32)` and `context = zeros((1,64), float32)`.
  - `probability(frame) -> float`: validate 1-D float32 length 512; `x = concat([context, frame[None, :]], axis=1)`; `out, h, c = session.run(None, {"input": x, "h": h, "c": c})`; `context = frame[-64:]`; return `float(out.reshape(-1)[0])`
  - `load_streaming_vad() -> StreamingSileroVad` via `import_module("faster_whisper.vad").get_vad_model().session`, cast to a local Protocol. Wrap any exception into `VadUnavailableError` with actionable text. Build a new adapter per toggle-on; the model itself stays cached by `lru_cache`.
  - `transcribe_speech(audio, model, no_speech_prob_limit=NO_SPEECH_PROB_LIMIT) -> str` in `faster_whisper_backend.py`: `NO_SPEECH_PROB_LIMIT = 0.6`; iterate segments **inside** try; skip `segment.no_speech_prob > limit`; join stripped texts like `transcribe` (96-101); wrap any inference exception into `TranscriptionError`. Export from `vox.transcribe`.
  - `start_input_stream(on_block, *, device_id, sample_rate, channels, blocksize) -> InputStreamProtocol` in `capture/stream.py`: create `InputStream(..., dtype="float32", blocksize=blocksize, callback=cb)` where `cb` calls `on_block(indata[:, 0].copy())`, then `start()`; wrap open/start exceptions in `RuntimeError("Could not start microphone input stream: <e>. Check the device and microphone permissions.")`; close the stream if `start()` fails. Export from `vox.capture`.
  - Integration test with the real bundled model: streaming probabilities `np.allclose` to batch `get_vad_model()(audio)` (atol 1e-5) on seeded noise plus a synthetic harmonic burst
- Must Not:
  - Call `SileroVADModel.__call__` per frame (state reset, diff up to 0.52)
  - Use `get_speech_timestamps` for streaming
  - Change `transcribe()` (Push-to-talk output unchanged)
  - Import `onnxruntime` directly or add it as a direct dependency
  - Add `# type: ignore` (use `import_module` + Protocol)
- Provenance map:
  - Window/context sizes → `vad.py:316-337`
  - I/O names → runtime probe + `vad.py:343-346`
  - No-speech limit → `transcribe.py:769,1217`
- Acceptance gates:
  - `uv lock --check`
  - `uv run python -c "import faster_whisper.vad as v; s = v.get_vad_model().session; assert {i.name for i in s.get_inputs()} == {'input', 'h', 'c'}; print('vad contract ok')"`
  - `uv run pytest tests/unit/test_streaming_vad.py tests/unit/test_transcribe_speech.py tests/unit/test_capture_input_stream.py tests/integration/test_streaming_vad_model.py -q`
  - `just types && just vulture && just darglint`

**Acceptance Criteria:**
- Fake-session unit tests prove state and context are carried (the second call receives the first call's `hn`/`cn` and the last 64 samples)
- Wrong input names → `VadUnavailableError`
- Integration test proves streaming == batch on the real model
- `transcribe_speech` drops `no_speech_prob > 0.6` segments, keeps ≤ 0.6, wraps generator exceptions
- `start_input_stream` passes `blocksize=512`, forwards mono copies, closes on start failure

**Non-Goals:** GPU VAD; configurable thresholds; resampling (capture is 16 kHz mono).

**Tasks:**
- [ ] Bump the faster-whisper floor, run `uv lock`, commit separately: `build(deps): require faster-whisper>=1.2.1 for streaming VAD`
- [ ] Create `src/vox/continuous/vad.py` + `tests/unit/test_streaming_vad.py` + `tests/integration/test_streaming_vad_model.py`
- [ ] Add `transcribe_speech` + export + `tests/unit/test_transcribe_speech.py`
- [ ] Add `start_input_stream` + export + `tests/unit/test_capture_input_stream.py`
- [ ] Commit: `feat(continuous): add streaming Silero VAD, speech-only transcription, and input stream`
- [ ] Add `--collect-data faster_whisper` to both PyInstaller build lines in `.github/workflows/build-release-assets.yml` (Windows/macOS and Linux) so `faster_whisper/assets/silero_vad_v6.onnx` ships in release binaries. Validate: `grep -c "collect-data faster_whisper" .github/workflows/build-release-assets.yml` prints `2`. Commit separately: `ci: bundle faster-whisper VAD assets in release binaries`

### Phase 5: Continuous dictation session runtime

#### Intent Lock

- Source of truth:
  - `src/vox/hotkey/register.py:185-194,247-284` (FIFO processor, sentinel, drain in finally)
  - `src/vox/commands.py:180-230` (cue callbacks), `255-262` (messages)
  - Agreed design items 1-11
- Must:
  - `ModifierTracker` (`modifiers.py`): `press(m)`, `release(m)`, `held() -> frozenset`, `wait_released(timeout_seconds) -> bool` using a `threading.Condition`. Constructor takes an optional `physical_state: Callable[[], frozenset[str]] | None`. When given, `held()` and `wait_released()` **reconcile**: any tracked modifier that the physical state reports as up is dropped (heals key-ups swallowed by Windows secure-desktop actions like Ctrl+Alt+Del / Win+L). `wait_released` polls `physical_state` at a short interval rather than relying only on release events.
  - `keystate.py`: `physical_modifier_state() -> Callable[[], frozenset[str]] | None`. On `sys.platform == "win32"` return a function using `ctypes.windll.user32.GetAsyncKeyState` (high bit `0x8000`) for `VK_CONTROL 0x11`, `VK_SHIFT 0x10`, `VK_MENU 0x12`, `VK_LWIN 0x5B`/`VK_RWIN 0x5C` → logical `ctrl`/`shift`/`alt`/`cmd`. Elsewhere return `None` (tracker trusts events). stdlib `ctypes` only, no new dependency.
  - `state.py`:
    - `ContinuousState(active: bool, error: str | None = None)`
    - `ToggleBinding(hotkey_str, on_toggle, is_active, modifiers)`
    - `continuous_refusal(injection_mode) -> str | None` via a dict (`clipboard` → message; `clipboard_and_paste`/`type` → `None`; unknown → `ValueError`)
    - `describe_window_label(state)` → `"Push-to-talk running."` / `"Continuous dictation on."` / `"Continuous dictation off: <error>"`
    - `describe_tray_title(state)` → `"Vox — push-to-talk"` / `"Vox — continuous dictation on"` / `"Vox — continuous dictation off: <error>"`, truncated to ≤120 chars
    - `describe_tray_notification(state) -> str | None` → the error text when `state.error` is set, else `None`
  - `ContinuousSettings(injection_mode, detector: DetectorSettings, stall_seconds=2.0, modifier_release_timeout_seconds=2.0, poll_seconds=0.1)`
  - `ContinuousDependencies` (frozen dataclass): `start_stream(on_block) -> InputStreamProtocol`, `create_vad() -> SpeechProbabilityModel`, `transcribe(audio) -> str`, `deliver(text) -> None`, `play_start_cue()`, `play_end_cue()`, `report(message)`, `publish_state(ContinuousState)`, `modifiers: ModifierTracker`, `clock() -> float` (default `time.monotonic`)
  - `ContinuousDictationSession(settings, deps)`, public API only:
    - `start()`
    - `request_toggle()`: thread-safe and **non-blocking**; enqueues a control command
    - `is_active() -> bool`
    - `shutdown()`
  - Control/listening thread:
    - **When off**, block on the control queue. On toggle: if `continuous_refusal(mode)` is set, report `[red]Continuous dictation unavailable:[/red] <msg>`, publish `ContinuousState(False, msg)`, play the **end cue** (audible "did not start"). Otherwise create the VAD and start the stream, both with `on_block` putting mono copies on an audio queue. On failure (`VadUnavailableError`, `RuntimeError`), report red, publish the error, play the end cue. On success, set active, play the start cue, publish `ContinuousState(True)`.
    - **When on**, each iteration: non-blocking check of the control queue (toggle or shutdown → turn off). `audio_q.get(timeout=poll_seconds)` → `FrameBuffer.push` → per frame `vad.probability` → `detector.feed` → handle events. If no block has arrived for `stall_seconds` (via `deps.clock`), treat it as a microphone failure.
    - **Turn off (reason)**: stop and close the stream (errors → yellow report); drain the audio queue into the detector; `detector.flush(frame_buffer.remainder())`; handle events; clear active; play the end cue; publish `ContinuousState(False, error)`. The error is set only for failures.
    - **Event handling:** `UtteranceEnded` → `commit_q.put(event)`; `UtteranceDiscarded` → `[dim]Ignored short sound (<n.nn> s of speech).[/dim]`; `IdleTimedOut` → turn off with a dim `Continuous dictation turned off after <n> idle minutes.`
    - **Microphone failure:** turn off, report `[red]Continuous dictation stopped: microphone input failed (<detail>).[/red]`, publish the error
  - Commit items carry `after_toggle_off: bool` (True only for Utterances produced by the turn-off flush when the reason is a user toggle).
  - Commit processor thread (FIFO, one consumer): `item = commit_q.get()`; `None` → exit. `deps.transcribe(item.audio)`; on `TranscriptionError` report red and continue. Empty text → `[dim]No speech detected.[/dim]` and continue. **Only if `item.after_toggle_off`**: `modifiers.wait_released(timeout)`; on timeout report `[yellow]Modifier keys still held; injecting anyway.[/yellow]`. Pause Commits never wait. Then `deps.deliver(text + " ")`.
  - Turning off never discards pending or in-flight Utterances. The processor keeps draining while off, and a new toggle-on enqueues after them, so order is preserved.
  - `shutdown()`: enqueue shutdown (turns off if active), join the control thread, `commit_q.put(None)`, join the processor (drains)
  - Construct a new `UtteranceDetector` and `FrameBuffer` on every toggle-on
- Must Not:
  - Do any blocking work in `request_toggle()` (it runs on the pynput hook thread)
  - Run VAD or detector work in the PortAudio callback (callback only enqueues)
  - Transcribe on the listening thread (would block listening)
  - Skip the start/end cue rules above or add a per-Commit cue
  - Import sounddevice, pynput, onnxruntime, or faster_whisper at module import time
- Provenance map:
  - Refusal message/visibility → agreed design item 5 + "no silent failures" (`README.md:12`)
  - Auto-off → item 7; mic failure → item 11; order and no-discard → item 11
  - Modifier wait → design gotcha (held modifiers during toggle-off Commit)
  - Stall watchdog → a stopped or removed device stops callbacks; a 2 s queue stall is host-API independent
- Acceptance gates:
  - `uv run pytest tests/unit/test_continuous_state.py tests/unit/test_continuous_session_toggle.py tests/unit/test_continuous_session_commits.py tests/unit/test_continuous_session_failures.py -q`
  - `uv run pytest tests/unit -q -n auto` (no flakiness under xdist)
  - `uv run pytest --cov=src/vox/continuous --cov-report=term-missing tests/unit -q` (session.py, state.py, modifiers.py ≥90%)
  - `just types && just complexity && just vulture`

**Acceptance Criteria:**
- Toggle on: start cue once, `is_active()` True, published active state
- Toggle on in `clipboard` mode: no stream opened, no start cue, end cue played, red message, published error
- Two Utterances → delivered as `"first "` then `"second "` in order even when the first transcription is slower (fake transcribe with an event gate)
- Toggle off mid-Utterance → pending Utterance delivered after the end cue, nothing lost
- Idle timeout → end cue, inactive, dim message
- Stream start failure → red message, inactive, end cue, published error; stall → red message, end cue, inactive
- Toggle-off Commit waits for modifier release; timeout path warns and delivers; Pause Commits deliver without waiting even when the tracker reports held modifiers
- Tracker with a fake `physical_state` reporting all-up drops stale modifiers from `held()` and `wait_released()` returns True immediately
- `shutdown()` drains the commit queue before returning

**Non-Goals:** keyboard listener integration; GUI; config reading.

**Tasks:**
- [ ] Create `modifiers.py`, `keystate.py`, `state.py`, `session.py`; extend `continuous/__init__.py` exports (still headless-safe)
- [ ] Create `tests/unit/conftest.py` fakes/fixtures
- [ ] Create the four session/state test files (each ≤350 lines)
- [ ] Commit: `feat(continuous): add continuous dictation session runtime`

### Phase 6: Toggle hotkey and `handle_run` wiring

#### Intent Lock

- Source of truth:
  - `src/vox/hotkey/register.py:135-329`
  - `src/vox/commands.py:26-119,286-385`
  - `tests/unit/test_commands.py:583-658`
- Must:
  - `register.py`: `_PushToTalkSession` and `run_push_to_talk_loop` accept `toggle_binding: ToggleBinding | None = None` (last parameter; keep the existing `# noqa: PLR0913`, add no new suppressions). Modifier tracking goes through a `ModifierTracker` built with `physical_state=physical_modifier_state()`: the binding's tracker if given, else a private one. It replaces the `current_modifiers` set. Binding matching uses the reconciled `held()`, so a stale Ctrl+Alt after Ctrl+Alt+Del cannot turn a plain Space press into a toggle on Windows.
  - Press routing: parse both combos once. On a non-modifier press, collect the bindings whose trigger matches and whose modifiers are ⊆ held. **Pick the one with the most modifiers** (overlap rule). Route via a dict of handlers.
  - Toggle handler: debounce auto-repeat with a `toggle_trigger_down` flag (set on handled press, cleared on toggle-trigger release); call `binding.on_toggle()` (non-blocking `session.request_toggle`)
  - Push-to-talk handler: if `toggle_binding` and `toggle_binding.is_active()` → return without starting a recording or cue. Otherwise use the existing start logic.
  - `commands.py`:
    - `HotkeyModuleProtocol` gains the 9th positional arg; `_run_push_to_talk_loop(..., toggle_binding=None)` forwards it
    - `HotkeyBindings` NamedTuple `(hotkey, continuous_hotkey)` and `_read_hotkey_bindings()` (one `get_config()` call; `.get("continuous_hotkey", DEFAULT_CONTINUOUS_HOTKEY)`)
    - `_spawn_hotkey_reload_watcher(*, stop_event, bindings, loop_stop_event, reload_requested)` restarts on either key change
    - Reload loop prints `Rebound hotkey:` (existing text) and/or `Rebound continuous hotkey:`
  - `handle_run(console, stop_event=None, on_continuous_state=None)`:
    - Read the three new keys from cfg with the config.py defaults
    - `_build_continuous_session(...)` wires `start_stream = partial(start_input_stream, device_id=..., sample_rate=16000, channels=1, blocksize=FRAME_SAMPLES)`, `create_vad = load_streaming_vad`, `transcribe = partial(transcribe_speech, model=model)`, `deliver = injector resolved from Phase 2 dispatch`, cues from `_build_cue_callbacks`, `report = console.print`, `publish_state = on_continuous_state or no-op`
    - `session.start()` before the listener loop
    - One session for the whole `handle_run`, surviving hotkey reloads, `shutdown()` in `finally` for both the terminal path and the reload path
    - The panel adds one line: `Continuous dictation: tap <continuous_hotkey> to toggle; pauses commit text.`
  - Update the fake watcher in `tests/unit/test_commands.py:583-658` to the new keyword signature (minimal edit; keep the assertions)
- Must Not:
  - Start a second pynput Listener
  - Block the listener thread
  - Change Push-to-talk behavior when Continuous dictation is off
  - Increase the number of `get_config()` calls in the reload path (the existing test uses a 2-item `side_effect`)
  - Suppress the toggle keypress (agreed: passes through)
- Provenance map:
  - PTT ignore → item 8
  - Toggle semantics/default → item 1
  - Live rebind → existing 004 addendum behavior (`commands.py:349-385`)
- Acceptance gates:
  - `uv run pytest tests/unit/test_hotkey.py tests/unit/test_hotkey_toggle.py tests/unit/test_commands.py tests/unit/test_commands_continuous.py -q`
  - `uv run python -c "import vox.cli, sys; assert 'pynput' not in sys.modules and 'sounddevice' not in sys.modules; print('headless import ok')"`
  - `uv run vox --help`
  - `just quality-check && just test-cov`

**Acceptance Criteria:**
- `ctrl`+`alt`+`space` press calls `on_toggle` once; repeated presses without release are ignored; a release re-arms
- PTT press while `is_active()` → no `on_start`, no thread
- Overlap: PTT `ctrl+space` + toggle `ctrl+alt+space`; pressing ctrl+alt+space toggles only. Reverse overlap: PTT `ctrl+alt+space` + toggle `ctrl+space` → PTT only.
- Watcher restarts on `continuous_hotkey` change and prints `Rebound continuous hotkey`
- `handle_run` calls `session.shutdown()` on normal stop and on exceptions
- Coverage ≥85% overall; diff-cover on changed non-GUI lines ≥80%

**Non-Goals:** GUI state display; settings fields.

**Tasks:**
- [ ] Extend `register.py` with the toggle binding, tracker, and best-match routing
- [ ] Wire the session, watcher, and panel in `commands.py`
- [ ] Create `tests/unit/test_hotkey_toggle.py`, `tests/unit/test_commands_continuous.py`; update the watcher fake in `tests/unit/test_commands.py`
- [ ] Commit: `feat(continuous): toggle continuous dictation from its own hotkey`

### Phase 7: GUI surfaces (Stop window, tray, settings)

#### Intent Lock

- Source of truth:
  - `src/vox/gui/stop_window.py:57-158`
  - `src/vox/gui/tray.py:92-156`
  - `src/vox/gui/settings_window.py:45-93,274-430,436-540,750-876`
  - Agreed design items 10, 11
- Must:
  - Stop window: `handle_run(console, stop_event=..., on_continuous_state=holder.set)` where `holder` is a lock-protected latest-state box. A `root.after(200, ...)` poll (mirror `_check_worker_error`, 140-145) updates a `StringVar` label via `describe_window_label`. Add `wraplength` and enlarge the geometry so the error text fits.
  - Tray: `on_continuous_state` sets `icon.title = describe_tray_title(state)` (VERIFY-IN-VENV the setter). When `describe_tray_notification(state)` (in `state.py`) returns text — i.e. the state carries an error (clipboard-mode refusal, VAD/stream start failure, mic failure) — also call `icon.notify(text, "Vox")` (Windows toast; VERIFY-IN-VENV `pystray` win32 `notify`/`HAS_NOTIFICATION`). Guard both with try/except that prints a yellow console warning; never kill the worker.
  - Settings: add `continuous_hotkey`, `continuous_pause_seconds`, `continuous_idle_minutes` to `DEFAULT_SETTINGS` and `RESTART_REQUIRED_FIELDS`. Add `SettingsController.commit_number(field_name, text) -> bool` (parse float; on `ValueError` set status `"<field>: must be a number"` and return False; else `_persist_updates`). Extract the hotkey capture handlers (750-836) into a reusable per-field helper so both hotkey entries share capture behavior. In the Recording section add "Continuous hotkey" (capture entry), "Pause before commit (s)" and "Idle auto-off (min)" entries committing on `<Return>`/`<FocusOut>`, each with `_add_override_note`. Refresh the new vars in `_on_restore_defaults`; commit a pending continuous-hotkey capture in `_on_window_close`.
  - Keep `SETTINGS_SECTIONS` unchanged (`tests/unit/test_settings_window.py:97-105`)
- Must Not:
  - Touch Tk widgets from non-Tk threads
  - Add a floating status bar or new window; notifications only for error states (no toast on normal on/off)
  - Duplicate validation (config layer remains the single source)
  - Put label/tooltip text logic in GUI modules (it lives in covered `state.py`)
- Provenance map:
  - Label/tooltip → item 10
  - Restart-required + settings exposure → item 11
  - Capture UX → 004 Plan Patch 2026-03-24
- Acceptance gates:
  - `uv run pytest tests/unit/test_settings_window.py tests/unit/test_settings_hotkey_capture.py tests/unit/test_settings_continuous_fields.py -q`
  - `just quality-check`
  - Manual: `uv run vox settings` shows the new fields; `uv run vox` label changes on toggle

**Acceptance Criteria:**
- Controller persists valid numbers, rejects `"abc"` and `0` with field-specific status, and rejects a continuous hotkey equal to `hotkey` via `ConfigError`
- Restore defaults writes the new defaults
- The Stop window label and tray tooltip reflect on, off, and error
- In tray mode, an error state (clipboard refusal, start failure, mic failure) raises one Windows notification; normal on/off raises none

**Non-Goals:** redesigning the settings layout; live-apply of pause/idle to a running session.

**Tasks:**
- [ ] Stop window state label + polling
- [ ] Tray tooltip updates
- [ ] Settings controller `commit_number`, defaults, restart set; view fields + capture helper extraction
- [ ] Create `tests/unit/test_settings_continuous_fields.py`
- [ ] Commits (UX kept separate per RULES): `feat(gui): show continuous dictation state in stop window and tray`, then `feat(settings): expose continuous dictation settings`

### Phase 8: Docs and status (docs-only commit)

#### Intent Lock

- Source of truth:
  - `README.md:48-101`
  - `vox.toml.example`
  - `docs/dev/status.md`
  - `.ai/REF/status-surfaces.md`
  - `CONTEXT.md`
- Must:
  - README: env override list adds the three `VOX_CONTINUOUS_*` vars. New `## Continuous dictation` section: toggle, Pause Commit, focused-window destination (wait for the text before switching windows), trailing space, PTT ignored while on, auto-off, junk guard, `clipboard` mode refusal, keypress not suppressed, mic failure behavior (end cue + tray notification), quitting is best-effort (utterances still transcribing at quit may be lost). Clipboard restore note under Commands/`injection_mode` (text only; non-text clipboard not preserved; skipped if paste failed). Settings Screen restart guidance lists the new keys. Definition of Visible Done gains the Continuous dictation steps.
  - `vox.toml.example`: three commented keys with defaults and env names; note the collision rule
  - `docs/dev/status.md`: bump `last_updated`, Current focus, Recently completed, Diary entry
  - Use glossary terms only
- Must Not:
  - Edit `CHANGELOG.md` (release-please owns it)
  - Mix code changes into this commit
- Provenance map: all copy derives from the implemented behavior in Phases 1-7
- Acceptance gates:
  - `just docs-check`
  - `just status`
  - `just quality && just test`

**Acceptance Criteria:** docs match shipped behavior; the final gate passes; the docs-only commit contains only doc files and this plan.

**Non-Goals:** full user manual; screenshots.

**Tasks:**
- [ ] Update README, `vox.toml.example`, `docs/dev/status.md`
- [ ] Append the Execution Report to this plan
- [ ] Commit: `docs: document continuous dictation and clipboard restore`

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### SETUP environment (prerequisite)

- **IMPLEMENT**: `uv sync --all-groups`. Then re-confirm the Verified Library Facts line references under `.venv/Lib/site-packages/` (faster_whisper/vad.py, faster_whisper/transcribe.py, pyperclip/__init__.py, pynput/keyboard/_base.py, sounddevice.py, pystray/_base.py). If any differ, add a `## Plan Patch` before coding.
- **PATTERN**: `README.md:29-35`
- **GOTCHA**: the repo had no `.venv` at plan time.
- **VALIDATE**: `uv run python -c "import faster_whisper, pyperclip; print(faster_whisper.__version__, pyperclip.__version__)"` (expect `1.2.1 1.11.0`)

### UPDATE `src/vox/config.py` (Phase 1)

- **IMPLEMENT**: Defaults constants; `("VOX_CONTINUOUS_HOTKEY", "continuous_hotkey", True)` in `_ENV_OVERRIDES`; `_FLOAT_ENV_OVERRIDES: tuple[tuple[str, str], ...] = (("VOX_CUE_VOLUME", "cue_volume"), ("VOX_CONTINUOUS_PAUSE_SECONDS", "continuous_pause_seconds"), ("VOX_CONTINUOUS_IDLE_MINUTES", "continuous_idle_minutes"))` consumed by `_apply_float_envs(raw)` (replaces `_apply_cue_volume_env` body) and by `get_env_override_fields`. `_normalize_hotkey_combo(value) -> tuple[frozenset[str], str]` with `_HOTKEY_ALIASES = {"control": "ctrl", "meta": "cmd", "win": "cmd"}` and modifier set `{"ctrl", "shift", "alt", "cmd"}`. `_validate_continuous_hotkey(raw)`: optional non-empty str; effective = raw value or default; if combos equal → `ValueError("continuous_hotkey: must differ from hotkey (both resolve to 'ctrl+alt+space'); set continuous_hotkey to another combination")`. `_validate_positive_number(raw, key)` rejects bool, non-real, non-finite, `<= 0`. Call both from `validate_config` after `_validate_hotkey`. Append keys to `_CONFIG_KEYS`; add them to `get_config` with `_str_default`/`_float_default`.
- **PATTERN**: `src/vox/config.py:165-226` (env), `334-348` (hotkey validator), `394-411` (numeric validator), `710-735` (get_config)
- **IMPORTS**: `math` (stdlib) for `isfinite`
- **GOTCHA**: `isinstance(True, int)` is True, so reject bool first. `find-dupes` (10-line similarity) flags copy-pasted env helpers; keep one table-driven helper. Keep `load_config` docstring env list in sync (darglint does not check prose, but reviewers do).
- **VALIDATE**: `uv run pytest tests/unit/test_config.py -q && just types`

### CREATE `tests/unit/test_config_continuous.py` (Phase 1)

- **IMPLEMENT**: Classes `TestContinuousDefaults` (get_config defaults via `mock.patch.object(vox_config, "load_config", ...)`), `TestContinuousEnvOverrides` (three env vars applied + `get_env_override_fields` includes them), `TestContinuousValidation` (valid values pass; `0`, `-1`, `True`, `"abc"`, `float("inf")` rejected per key; collision with same and reordered combo `alt+ctrl+space`; alias `control+alt+space` collides; distinct combos pass), `TestContinuousSerialization` (new keys serialized after `use_tray`).
- **PATTERN**: `tests/unit/test_config.py:409-431`, `554-571`
- **IMPORTS**: `os`, `unittest.mock`, `pytest`, `from vox import config as vox_config`
- **GOTCHA**: ≤350 lines; `@pytest.mark.unit` on classes; strict AAA comments.
- **VALIDATE**: `uv run pytest tests/unit/test_config_continuous.py -q`

### COMMIT Phase 1

- **VALIDATE**: `just quality-check && just test-cov`, then `git add src/vox/config.py tests/unit/test_config_continuous.py .ai/PLANS/005-continuous-dictation.md && git commit -m "feat(config): add continuous dictation settings"` (match the repo trailer convention: `git log -3 --format='%B'` shows no Co-Authored-By trailers)

### UPDATE `src/vox/inject/clipboard.py` and `src/vox/inject/__init__.py` (Phase 2)

- **IMPLEMENT**: `get_clipboard() -> str` calling `pyperclip.paste()`. A non-str result becomes `""`. `pyperclip.PyperclipException` → `InjectError("Failed to read clipboard: <e>. ...")`. Export in `__all__`.
- **PATTERN**: `src/vox/inject/clipboard.py:14-34`
- **IMPORTS**: none new
- **GOTCHA**: pyperclip returns `""` for non-text clipboard on Windows (pyperclip 448-456).
- **VALIDATE**: `uv run pytest tests/unit/test_inject.py -q`

### UPDATE `tests/unit/test_inject.py` (Phase 2)

- **IMPLEMENT**: `TestGetClipboard`: returns the `pyperclip.paste` value; wraps `PyperclipException` in `InjectError`.
- **PATTERN**: `tests/unit/test_inject.py:13-46`
- **VALIDATE**: `uv run pytest tests/unit/test_inject.py -q`

### REFACTOR `src/vox/commands.py` Injection dispatch + ADD restore (Phase 2)

- **IMPLEMENT**: Move the branch bodies from 263-281 into `_inject_type(console, text)`, `_inject_clipboard(console, text)`, `_inject_clipboard_and_paste(console, text)`. Register them in `_INJECTORS`. `_resolve_injector(injection_mode) -> Callable[[Console, str], None]` raises `ConfigError(f"injection_mode: unsupported value {mode!r}")`. `_build_audio_handler` resolves once, then `on_audio` does transcribe → empty check → `injector(console, text)`. Restore helpers: `_snapshot_clipboard(console) -> str | None`, `_pause_before_clipboard_restore()` (sleeps `_CLIPBOARD_RESTORE_DELAY_SECONDS`), `_restore_clipboard(console, previous, injected)`.
- **PATTERN**: `src/vox/commands.py:233-283`; warning style `commands.py:280`
- **IMPORTS**: `get_clipboard` from `vox.inject`
- **GOTCHA**: existing tests patch `vox.commands.set_clipboard` / `paste_into_focused` / `type_into_focused`, so the injector functions must look these names up in `vox.commands` (module globals), not capture them in defaults. xenon B max per function: keep each helper small.
- **VALIDATE**: `uv run pytest tests/unit/test_commands.py -q && just complexity`

### UPDATE `tests/unit/test_commands.py` (Phase 2, minimal)

- **IMPLEMENT**: In `test_on_audio_calls_paste_and_prints_yellow_when_paste_fails` (362-407), add `mock.patch("vox.commands.get_clipboard", return_value="previous")` and `mock.patch("vox.commands._pause_before_clipboard_restore")` to the Act `with` block. No other edits.
- **GOTCHA**: without the patch, CI Linux (xvfb, no xclip) would hit the real clipboard.
- **VALIDATE**: `uv run pytest tests/unit/test_commands.py -q`

### CREATE `tests/unit/test_clipboard_restore.py` (Phase 2)

- **IMPLEMENT**: Build `on_audio` via `handle_run` capture (same as `test_commands.py:199-238`) with `injection_mode="clipboard_and_paste"`. Cases:
  1. Restores the snapshot after paste (record call order: get → set(text) → paste → pause → get → set(previous))
  2. Skips the restore when the snapshot is `""`
  3. Skips the restore when the clipboard changed (second `get_clipboard` returns `"user copied"`)
  4. Skips the restore when the paste fails (still prints `Injected`)
  5. Snapshot `InjectError` → yellow `Clipboard restore skipped`, still pastes
  6. Unknown mode → `ConfigError` at `handle_run` build time
  7. `clipboard` and `type` modes never call `get_clipboard`
- **PATTERN**: `tests/unit/test_commands.py:199-238,362-407`
- **GOTCHA**: patch `vox.commands._pause_before_clipboard_restore`; ≤350 lines (use a module helper `_capture_on_audio(mode, console)` with a docstring).
- **VALIDATE**: `uv run pytest tests/unit/test_clipboard_restore.py -q`

### COMMIT Phase 2

- **VALIDATE**: `just quality-check && just test-cov`, then commit the changed src/tests/plan files: `feat(inject): restore previous clipboard text after paste`

### CREATE `src/vox/continuous/__init__.py` and `src/vox/continuous/utterances.py` (Phase 3)

- **IMPLEMENT**: As specified in the Phase 3 Intent Lock. Events: `@dataclass(frozen=True) UtteranceEnded(audio: np.ndarray, speech_seconds: float)`, `UtteranceDiscarded(speech_seconds: float)`, `IdleTimedOut(idle_seconds: float)`; `type DetectorEvent = UtteranceEnded | UtteranceDiscarded | IdleTimedOut`. Internals split into small methods (`_classify`, `_feed_idle`, `_feed_in_utterance`, `_end_utterance`, `_check_idle`) to stay within xenon B.
- **PATTERN**: dataclass style `src/vox/audio_cues.py:32-37`; type alias style `src/vox/config.py:240`
- **IMPORTS**: `math`, `collections.deque`, `dataclasses`, `numpy`
- **GOTCHA**: returned `audio` must be a fresh `np.concatenate` (no aliasing of buffers reused later); dtype float32; 1-D.
- **VALIDATE**: `uv run python -c "import vox.continuous.utterances as u; print(u.FRAME_SAMPLES)"`

### CREATE `tests/unit/test_utterance_detector.py` (Phase 3)

- **IMPLEMENT**: Helper `_frames(n, value)` returns n×512 float32 frames with a distinct fill value (so audio slicing is checkable). Tests for every Phase 3 acceptance criterion, plus: `DetectorSettings` rejects bad values; `feed` rejects wrong length/2-D; `FrameBuffer` re-chunks 300+300+500 samples into 2 frames with remainder 88; `flush(tail)` includes the tail; pre-roll is capped at pad frames; idle emitted once.
- **PATTERN**: AAA style `tests/unit/test_hotkey.py:172-208`
- **VALIDATE**: `uv run pytest tests/unit/test_utterance_detector.py -q`

### COMMIT Phase 3

- **VALIDATE**: `just quality-check && just test-cov`, commit `feat(continuous): add utterance detector`

### UPDATE `pyproject.toml` + `uv.lock` (Phase 4)

- **IMPLEMENT**: `"faster-whisper>=1.2.1,<2"`; run `uv lock`.
- **GOTCHA**: must not change any resolved version (lock already at 1.2.1); inspect `git diff uv.lock` (expect only the specifier line near `uv.lock:2106`).
- **VALIDATE**: `uv lock --check && git diff --stat uv.lock`, commit `build(deps): require faster-whisper>=1.2.1 for streaming VAD`

### CREATE `src/vox/continuous/vad.py` (Phase 4)

- **IMPLEMENT**: Protocols `_OnnxInputProtocol(name: str)`, `OnnxSessionProtocol(get_inputs() -> list[_OnnxInputProtocol]; run(output_names: None, input_feed: dict[str, np.ndarray]) -> list[np.ndarray])`, `_VadModelProtocol(session: OnnxSessionProtocol)`, `_VadModuleProtocol(get_vad_model: Callable[[], _VadModelProtocol])`, `SpeechProbabilityModel(probability(frame) -> float)`. `VadUnavailableError(RuntimeError)`. `StreamingSileroVad` and `load_streaming_vad()` per the Phase 4 Intent Lock. Constants `_CONTEXT_SAMPLES = 64`, `_STATE_SHAPE = (1, 1, 128)`, `_REQUIRED_INPUTS = frozenset({"input", "h", "c"})`.
- **PATTERN**: lazy module + Protocol cast `src/vox/audio_cues.py:133-161`; error wrap `src/vox/capture/stream.py:93-96`
- **IMPORTS**: `importlib.import_module`, `typing.Protocol, cast`, `numpy`, `FRAME_SAMPLES` from `vox.continuous.utterances`
- **GOTCHA**: `session.run` returns `[speech_probs, hn, cn]`; `speech_probs` shape `(1,)` for one window. Keep `h`/`c` as returned arrays (float32). Context is the **previous frame's** last 64 samples, zeros for the first frame (`vad.py:331-335`).
- **VALIDATE**: `uv run python -c "from vox.continuous.vad import load_streaming_vad; import numpy as np; v = load_streaming_vad(); print(v.probability(np.zeros(512, dtype=np.float32)))"`

### CREATE `tests/unit/test_streaming_vad.py` (Phase 4)

- **IMPLEMENT**: `FakeSession` records every `input_feed` and returns scripted `(probs, h+1, c+1)`. Tests: first call context zeros and h/c zeros; second call context equals the first frame's last 64 samples and receives the previous `hn`/`cn`; returns a Python float; wrong-length frame → `ValueError`; missing input names → `VadUnavailableError`; `load_streaming_vad` wraps an import failure (patch `vox.continuous.vad.import_module` to raise) into `VadUnavailableError`.
- **PATTERN**: `tests/unit/test_capture.py:62-116` (patching lazy loader)
- **VALIDATE**: `uv run pytest tests/unit/test_streaming_vad.py -q`

### CREATE `tests/integration/test_streaming_vad_model.py` (Phase 4)

- **IMPLEMENT**: `@pytest.mark.integration`. Seeded `np.random.default_rng(0)` noise (0.01 amplitude, 1 s) + 1.5 s harmonic burst (140/280/420 Hz with 4 Hz AM) + 1 s noise, trimmed to a multiple of 512. `batch = get_vad_model()(audio)`; `streaming = [load_streaming_vad().probability(f) for f in frames]`; `np.testing.assert_allclose(streaming, batch, atol=1e-5)`.
- **PATTERN**: `tests/integration/test_capture_transcribe.py`
- **GOTCHA**: no audio hardware needed; do not use `requires_audio`. The model asset is bundled in the wheel.
- **VALIDATE**: `uv run pytest tests/integration/test_streaming_vad_model.py -q`

### UPDATE `src/vox/transcribe/faster_whisper_backend.py` + `__init__.py` (Phase 4)

- **IMPLEMENT**: `NO_SPEECH_PROB_LIMIT = 0.6`; `transcribe_speech(audio: np.ndarray, model: WhisperModel, no_speech_prob_limit: float = NO_SPEECH_PROB_LIMIT) -> str`; 2-D → first column like 91-94; wrap `model.transcribe(...)` and full iteration in try → `TranscriptionError(f"Transcription failed: {e}")`.
- **PATTERN**: `src/vox/transcribe/faster_whisper_backend.py:49-101`
- **GOTCHA**: the generator is lazy, so exceptions surface during iteration and must be inside the try. Use `getattr(segment, "no_speech_prob", 0.0)` only if tests use simple objects; otherwise read attributes directly (prefer direct and use `SimpleNamespace` in tests).
- **VALIDATE**: `uv run pytest tests/unit/test_transcribe_speech.py tests/unit/test_transcribe.py -q`

### CREATE `tests/unit/test_transcribe_speech.py` (Phase 4)

- **IMPLEMENT**: Mock model whose `transcribe` returns `(iter([SimpleNamespace(text=" Hello", no_speech_prob=0.1), SimpleNamespace(text=" Thank you.", no_speech_prob=0.9)]), None)` → `"Hello"`; boundary `0.6` kept; all dropped → `""`; generator raising mid-iteration → `TranscriptionError`; 2-D input passes 1-D to the model.
- **PATTERN**: `tests/unit/test_transcribe.py:126-143`
- **VALIDATE**: `uv run pytest tests/unit/test_transcribe_speech.py -q`

### UPDATE `src/vox/capture/stream.py` + `__init__.py` (Phase 4)

- **IMPLEMENT**: `start_input_stream` per the Phase 4 Intent Lock (keyword-only after `on_block`).
- **PATTERN**: `src/vox/capture/stream.py:146-201`
- **GOTCHA**: never do more than copy + enqueue in the callback; `indata` is reused by PortAudio, so `.copy()` is mandatory.
- **VALIDATE**: `uv run pytest tests/unit/test_capture_input_stream.py tests/unit/test_capture.py -q`

### CREATE `tests/unit/test_capture_input_stream.py` (Phase 4)

- **IMPLEMENT**: Patch `vox.capture.stream._sd`. Assert InputStream kwargs (`blocksize=512`, `dtype="float32"`, `samplerate=16000`, `channels=1`, `device=None`); the callback forwards a 1-D copy of column 0 (mutating the original after the call does not change the forwarded array); `start()` failure → `RuntimeError` + `close()` called; constructor failure → `RuntimeError`.
- **PATTERN**: `tests/unit/test_capture.py:62-116`
- **VALIDATE**: `uv run pytest tests/unit/test_capture_input_stream.py -q`

### COMMIT Phase 4

- **VALIDATE**: `just quality-check && just test-cov`, commit `feat(continuous): add streaming Silero VAD, speech-only transcription, and input stream`

### CREATE `src/vox/continuous/modifiers.py`, `keystate.py`, `state.py`, `session.py` (Phase 5)

- **IMPLEMENT**: Per the Phase 5 Intent Lock. Session internals as small methods: `_control_loop`, `_wait_while_off`, `_turn_on`, `_listen_step`, `_process_block`, `_handle_events` (dict dispatch on event type: `{UtteranceEnded: self._enqueue_commit, UtteranceDiscarded: self._report_discarded, IdleTimedOut: self._auto_off}`), `_turn_off(error: str | None)`, `_processor_loop`, `_commit(item)`. Commands: `_Command` enum (`TOGGLE`, `SHUTDOWN`). Threads are daemon, named `vox-continuous-control` and `vox-continuous-commit`.
- **PATTERN**: `src/vox/hotkey/register.py:185-194,257-284`; message style `src/vox/commands.py:255-281`
- **IMPORTS**: `threading`, `queue`, `time`, `enum`, `dataclasses`, `collections.abc.Callable`, `numpy`, `vox.continuous.utterances`, `vox.continuous.vad` (types + `VadUnavailableError` only), `vox.continuous.modifiers`, `vox.continuous.state`, `vox.transcribe.exceptions.TranscriptionError`
- **GOTCHA**:
  - Import `TranscriptionError` from `vox.transcribe.exceptions`, **not** `vox.transcribe` (that package imports faster_whisper eagerly, `transcribe/__init__.py:3-4`)
  - `InputStreamProtocol` import from `vox.capture.stream` is safe (sounddevice is lazy)
  - Wrap `deps.play_*_cue`, `deps.publish_state`, `deps.deliver` in try/except that reports yellow (a GUI or cue exception must not kill the threads)
  - Reset stall timing (`last_block_at = clock()`) at turn-on
  - Make `shutdown()` idempotent
  - `keystate.py`: branch on `sys.platform == "win32"` so mypy on Linux CI treats the ctypes path as platform-specific (no `type: ignore`). Unit-test the VK→logical mapping by injecting a fake `get_async_key_state` callable; the real `windll` lookup stays a one-line seam.
- **VALIDATE**: `uv run python -c "import sys, vox.continuous.session; bad = {'sounddevice', 'pynput', 'onnxruntime', 'faster_whisper'} & set(sys.modules); assert not bad, bad; print('headless ok')"`

### CREATE `tests/unit/conftest.py` (Phase 5)

- **IMPLEMENT**: Fixtures:
  - `fake_stream_factory`: records `on_block`, exposes `push(samples)`, `start_error`, `stopped`/`closed` flags
  - `scripted_vad`: returns probabilities from a list, then 0.0
  - `delivery_log`: list plus `threading.Event` per delivery count
  - `make_session(**overrides)` builder with small durations: pause 0.064 s, idle 0.01 min, stall 0.2 s, poll 0.01 s, modifier timeout 0.05 s
- **GOTCHA**: every fixture and helper needs a docstring and annotations (ruff D/ANN apply to tests). Tests must wait on events with timeouts (≤2 s), never `sleep` for ordering.
- **VALIDATE**: `uv run pytest tests/unit --collect-only -q`

### CREATE `tests/unit/test_continuous_state.py`, `test_continuous_session_toggle.py`, `test_continuous_session_commits.py`, `test_continuous_session_failures.py` (Phase 5)

- **IMPLEMENT**:
  - state: `ModifierTracker` press/release/wait timeout, physical-state reconciliation drops stale modifiers, `keystate` VK mapping with a fake key-state function, `continuous_refusal` table, label/tooltip/notification texts and truncation, unknown mode `ValueError`
  - toggle: on (cue, active, state), off (end cue, inactive), clipboard refusal (end cue), idempotent shutdown, toggle while off-and-refused stays off
  - commits: ordering with a slow first transcription, trailing space, `UtteranceDiscarded` message, empty transcription message, `TranscriptionError` continues, toggle-off delivers the pending Utterance, toggle-off Commit waits for modifier release, modifier timeout warns, Pause Commit does not wait on held modifiers
  - failures: VAD load failure, stream start failure, stall → mic failure message + end cue, idle auto-off, cue exception does not kill the session
- **PATTERN**: AAA and marker style `tests/unit/test_hotkey.py:58-138`
- **GOTCHA**: each file ≤350 lines. Always `session.shutdown()` in a `try/finally` so threads never leak between tests.
- **VALIDATE**: `uv run pytest tests/unit/test_continuous_state.py tests/unit/test_continuous_session_toggle.py tests/unit/test_continuous_session_commits.py tests/unit/test_continuous_session_failures.py -q -n auto`

### COMMIT Phase 5

- **VALIDATE**: `just quality-check && just test-cov`, commit `feat(continuous): add continuous dictation session runtime`

### UPDATE `src/vox/hotkey/register.py` (Phase 6)

- **IMPLEMENT**: Per the Phase 6 Intent Lock. `_Binding` internal dataclass `(kind: Literal["ptt", "toggle"], modifiers: frozenset[keyboard.Key], trigger: keyboard.Key | str)`. `_best_binding(key) -> _Binding | None` picks the satisfied match with the largest modifier set. `_PRESS_HANDLERS` maps kind → bound method. The release path clears `toggle_trigger_down` when the key matches the toggle trigger and keeps the existing PTT release logic. The tracker records `_normalize_modifier` results.
- **PATTERN**: `src/vox/hotkey/register.py:196-245`
- **IMPORTS**: `from vox.continuous.modifiers import ModifierTracker`, `from vox.continuous.state import ToggleBinding`
- **GOTCHA**:
  - Windows low-level hook: callbacks must return fast; `on_toggle` must only enqueue
  - Held keys auto-repeat press events, so debounce
  - Parse `toggle_binding.hotkey_str` in `__init__` so an invalid string fails fast with `ValueError` (the existing `_parse_hotkey` message)
- **VALIDATE**: `uv run pytest tests/unit/test_hotkey.py tests/unit/test_hotkey_toggle.py -q`

### CREATE `tests/unit/test_hotkey_toggle.py` (Phase 6)

- **IMPLEMENT**: Drive `_PushToTalkSession._on_press/_on_release` with `keyboard.Key.ctrl_l`, `keyboard.Key.alt_l`, `keyboard.Key.space`, patching `vox.hotkey.register.threading.Thread`. Cases: toggle fires once; auto-repeat ignored; re-arm after release; PTT ignored while `is_active` returns True; PTT works when False; both overlap directions; tracker reflects held modifiers; invalid toggle hotkey raises `ValueError`.
- **PATTERN**: `tests/unit/test_hotkey.py:104-165`
- **VALIDATE**: `uv run pytest tests/unit/test_hotkey_toggle.py -q`

### UPDATE `src/vox/commands.py` wiring (Phase 6)

- **IMPLEMENT**: Per the Phase 6 Intent Lock: `HotkeyModuleProtocol` 9th arg; `_run_push_to_talk_loop(..., toggle_binding=None)`; `HotkeyBindings`, `_read_hotkey_bindings`, watcher signature `bindings`; `_build_continuous_session`; `handle_run(..., on_continuous_state=None)` with `try/finally: session.shutdown()` around both loop paths; panel line; reload messages.
- **PATTERN**: `src/vox/commands.py:47-119,286-385`
- **IMPORTS**: `functools.partial`; `from vox.capture import start_input_stream`; `from vox.config import DEFAULT_CONTINUOUS_HOTKEY, DEFAULT_CONTINUOUS_IDLE_MINUTES, DEFAULT_CONTINUOUS_PAUSE_SECONDS`; `from vox.continuous.*` (session, settings, dependencies, state, detector settings, `FRAME_SAMPLES`, `ModifierTracker`); `load_streaming_vad`; `transcribe_speech`
- **GOTCHA**:
  - Keep `vox.hotkey` lazily imported (`commands.py:69`)
  - `handle_run` has one `get_config()` before the loop; the reload path does one per reload (existing test relies on this)
  - xenon: split `handle_run` into helpers if its complexity exceeds B
  - Existing `mock_cfg` dicts lack the new keys, so use `.get(key, DEFAULT_...)`
  - Existing tests patch `vox.commands.load_model`/`preload_default_cues`; the session must not open a stream or load VAD until a toggle, so no extra patches are needed
- **VALIDATE**: `uv run pytest tests/unit/test_commands.py -q`

### UPDATE `tests/unit/test_commands.py` watcher fake (Phase 6, minimal)

- **IMPLEMENT**: In `test_handle_run_rebinds_hotkey_without_restart` (583-658), change the fake signature `hotkey_str: str` → `bindings: object` and `_ = hotkey_str` → `_ = bindings`. No other edits.
- **VALIDATE**: `uv run pytest tests/unit/test_commands.py -q`

### CREATE `tests/unit/test_commands_continuous.py` (Phase 6)

- **IMPLEMENT**:
  - `handle_run` passes a `ToggleBinding` whose `hotkey_str` equals cfg `continuous_hotkey` (default when absent)
  - `on_toggle` delegates to `session.request_toggle` (patch `vox.commands.ContinuousDictationSession` with a mock)
  - `shutdown` called on normal return and when the loop raises
  - The watcher detects a `continuous_hotkey` change (real `_spawn_hotkey_reload_watcher` with patched `get_config` and a short poll via `mock.patch("vox.commands._HOTKEY_RELOAD_POLL_SECONDS", 0.01)`)
  - Reload loop prints `Rebound continuous hotkey`
  - `_build_continuous_session` wires deliver → injector with the trailing space added by the session (assert through a fake session capturing deps)
  - Panel mentions the continuous hotkey
- **PATTERN**: `tests/unit/test_commands.py:131-197,583-658`
- **VALIDATE**: `uv run pytest tests/unit/test_commands_continuous.py -q`

### COMMIT Phase 6

- **VALIDATE**: `uv run vox --help && just quality-check && just test-cov && uv run diff-cover coverage.xml --compare-branch=main --fail-under=80`, commit `feat(continuous): toggle continuous dictation from its own hotkey`

### UPDATE `src/vox/gui/stop_window.py` (Phase 7)

- **IMPLEMENT**: `_LatestState` (lock + `ContinuousState`), `_start_worker(..., on_continuous_state)` passes it to `handle_run`, label bound to `tk.StringVar(value=describe_window_label(ContinuousState(active=False)))`, `_refresh_state_label` scheduled every 200 ms, `ttk.Label(..., wraplength=240)`, geometry `"280x120"` / minsize `(260, 100)`.
- **PATTERN**: `src/vox/gui/stop_window.py:57-86,140-158`
- **GOTCHA**: Tk calls only on the Tk thread (the poll reads the holder).
- **VALIDATE**: `uv run ruff check src/vox/gui && uv run mypy -p vox`

### UPDATE `src/vox/gui/tray.py` (Phase 7)

- **IMPLEMENT**: Create `icon` before starting the worker (reorder 137-145 accordingly); `on_continuous_state(state)` sets `icon.title = describe_tray_title(state)` and, when `describe_tray_notification(state)` returns text, calls `icon.notify(text, "Vox")`, each inside try/except (yellow console warning); pass to `handle_run`.
- **PATTERN**: `src/vox/gui/tray.py:114-151`
- **GOTCHA**: VERIFY-IN-VENV that the `Icon.title` setter updates the live tooltip on win32.
- **VALIDATE**: `uv run ruff check src/vox/gui && uv run mypy -p vox`

### UPDATE `src/vox/gui/settings_window.py` (Phase 7)

- **IMPLEMENT**: Per the Phase 7 Intent Lock. Extract `_HotkeyCaptureField(root_var: tk.StringVar, field_name: str, controller: SettingsController, sync_status: Callable[[], None])` holding `modifier_order`, `active_modifiers`, `active_trigger`, `captured_value` and the handlers now at 750-836, reusing module helpers (`_event_keysym_to_hotkey_token`, `_build_hotkey_value`, etc., tested in `tests/unit/test_settings_hotkey_capture.py`). Add `commit_number` to the controller. Increase geometry to fit the new rows (e.g. `620x660`, minsize `580x620`).
- **PATTERN**: `src/vox/gui/settings_window.py:274-296,506-540,750-836,862-876`
- **GOTCHA**:
  - `find-dupes` fails if the two hotkey fields copy-paste handlers, so the helper is required
  - Keep module-level helper names unchanged (existing tests import them)
  - `SETTINGS_SECTIONS` unchanged
- **VALIDATE**: `uv run pytest tests/unit/test_settings_window.py tests/unit/test_settings_hotkey_capture.py -q && just find-dupes`

### CREATE `tests/unit/test_settings_continuous_fields.py` (Phase 7)

- **IMPLEMENT**: Controller-only tests (mirror `_build_controller`): defaults include the three keys; `commit_number` valid → saved + restart message; `"abc"` → status `must be a number`, not saved; `"0"` → `ConfigError` status from a real `update_persisted_config` with `base` and `tmp_path` via `VOX_CONFIG`; continuous hotkey equal to hotkey → error status, file unchanged; restore defaults writes the new keys.
- **PATTERN**: `tests/unit/test_settings_window.py:58-146`
- **VALIDATE**: `uv run pytest tests/unit/test_settings_continuous_fields.py -q`

### COMMIT Phase 7

- **VALIDATE**: `just quality-check && just test-cov`, then two commits: GUI state files → `feat(gui): show continuous dictation state in stop window and tray`; settings files → `feat(settings): expose continuous dictation settings`

### UPDATE `README.md`, `vox.toml.example`, `docs/dev/status.md` (Phase 8)

- **IMPLEMENT**: Per the Phase 8 Intent Lock. Add the manual checks from `DEFINITION OF VISIBLE DONE` to README's Definition of Visible Done list.
- **PATTERN**: `README.md:48-101`, `vox.toml.example:23-36`, `docs/dev/status.md:1-25`
- **GOTCHA**: glossary terms only; no code changes in this commit.
- **VALIDATE**: `just docs-check && just status && just quality && just test`, commit `docs: document continuous dictation and clipboard restore`

---

## TESTING STRATEGY

### Unit Tests

- Pure seams carry most of the logic and coverage: `utterances.py`, `vad.py` (fake ONNX session), `state.py`, `modifiers.py`, config validation, Injection dispatch/restore, `transcribe_speech` (fake model), `start_input_stream` (patched `_sd`).
- Session tests use real threads with fakes and event-based waits. No audio hardware, no Whisper model, no pynput listener.
- Hotkey tests drive `_PushToTalkSession` callbacks directly with pynput key objects (no OS hook).
- Settings tests exercise `SettingsController` only (the Tk view is omitted from coverage).

### Integration Tests

- `tests/integration/test_streaming_vad_model.py`: the real bundled Silero model gives streaming == batch probabilities. Hardware-free, runs in CI on all three OSes.
- Existing `tests/integration/*` stay green (audio-gated by `requires_audio`).

### Edge Cases

- Probability hovering between thresholds (hysteresis keeps state)
- Utterance exactly at 0.3 s boundary (9 vs 10 frames)
- Toggle-off with a partial (<512 samples) tail
- Toggle-off while the previous Utterance is still transcribing (order preserved)
- Rapid on/off/on toggles (commands processed sequentially; new detector per on)
- Key auto-repeat on the toggle combo
- Overlapping PTT/toggle combos in both directions
- `continuous_hotkey` equal to `hotkey` via reordered/aliased modifiers
- Existing user whose `hotkey` is `ctrl+alt+space` (ConfigError with actionable message)
- Clipboard snapshot empty, clipboard changed during the 150 ms window, paste failure, clipboard read failure
- Whisper returns only high-`no_speech_prob` segments → nothing Injected, dim message
- Stream start raises; stream stalls (device removed); stream stop/close raises during turn-off
- VAD asset/onnxruntime unavailable; faster-whisper internals changed (input-name contract)
- Cue playback or GUI publish callback raises (session keeps running)
- Modifier keys still held at Commit (wait), stale modifier state (timeout warning)
- App shutdown while Continuous dictation is on (turn off + drain; see Open Questions)

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

- `just lint-check`
- `just format-check`
- `just types`
- `just complexity`
- `just vulture`
- `just darglint`
- `just find-dupes`

### Level 2: Unit Tests

- `uv run pytest tests/unit/test_config_continuous.py tests/unit/test_config.py -q`
- `uv run pytest tests/unit/test_inject.py tests/unit/test_clipboard_restore.py tests/unit/test_commands.py -q`
- `uv run pytest tests/unit/test_utterance_detector.py tests/unit/test_streaming_vad.py tests/unit/test_transcribe_speech.py tests/unit/test_capture_input_stream.py -q`
- `uv run pytest tests/unit/test_continuous_state.py tests/unit/test_continuous_session_toggle.py tests/unit/test_continuous_session_commits.py tests/unit/test_continuous_session_failures.py -q -n auto`
- `uv run pytest tests/unit/test_hotkey.py tests/unit/test_hotkey_toggle.py tests/unit/test_commands_continuous.py -q`
- `uv run pytest tests/unit/test_settings_window.py tests/unit/test_settings_hotkey_capture.py tests/unit/test_settings_continuous_fields.py -q`

### Level 3: Integration Tests

- `uv run pytest tests/integration -q`

### Level 4: Manual Validation (Windows 11)

See `DEFINITION OF VISIBLE DONE`.

### Level 5: Final Gate

- `uv run python -c "import vox.cli, sys; assert 'pynput' not in sys.modules and 'sounddevice' not in sys.modules; print('headless import ok')"`
- `uv run vox --help`
- `just docs-check`
- `just status`
- `just quality && just test`
- `just test-cov` (≥85%)
- `uv run diff-cover coverage.xml --compare-branch=main --fail-under=80`

---

## REQUIRED TESTS AND GATES

| Phase | Required gate before commit |
|---|---|
| 1 | `uv run pytest tests/unit/test_config_continuous.py tests/unit/test_config.py -q` + `just quality-check && just test-cov` |
| 2 | `uv run pytest tests/unit/test_clipboard_restore.py tests/unit/test_inject.py tests/unit/test_commands.py -q` + `just quality-check && just test-cov` |
| 3 | `uv run pytest tests/unit/test_utterance_detector.py -q` + `just quality-check && just test-cov` |
| 4 | `uv lock --check` + VAD contract one-liner + Phase 4 unit/integration tests + `just quality-check && just test-cov` |
| 5 | Session/state tests with `-n auto` + `just quality-check && just test-cov` |
| 6 | Hotkey/commands tests + headless import check + `uv run vox --help` + `just quality-check && just test-cov` + diff-cover |
| 7 | Settings tests + `just find-dupes` + `just quality-check && just test-cov` + manual GUI check |
| 8 | `just docs-check && just status && just quality && just test` |

Warnings are defects (RULES). Any residual warning must be recorded in the Execution Report with its signature, reason, owner, and target date.

---

## OUTPUT CONTRACT

- Exact output artifacts/surfaces:
  - Global toggle hotkey `continuous_hotkey` (default `ctrl+alt+space`) in `uv run vox` (Stop window) and `VOX_TRAY=1 uv run vox` (tray)
  - Injected text + trailing space in the focused window on each Pause Commit (`injection_mode` `type` or `clipboard_and_paste`)
  - Console lines: `Continuous dictation unavailable:`, `Continuous dictation stopped: microphone input failed`, `Continuous dictation turned off after`, `Ignored short sound`, `Clipboard restore skipped:`, `Rebound continuous hotkey:`
  - Stop window label: `Push-to-talk running.` / `Continuous dictation on.` / `Continuous dictation off: <error>`
  - Tray tooltip: `Vox — push-to-talk` / `Vox — continuous dictation on` / `Vox — continuous dictation off: <error>`
  - Config keys in `~/.vox/vox.toml` (or `VOX_CONFIG`): `continuous_hotkey`, `continuous_pause_seconds`, `continuous_idle_minutes`; env `VOX_CONTINUOUS_HOTKEY`, `VOX_CONTINUOUS_PAUSE_SECONDS`, `VOX_CONTINUOUS_IDLE_MINUTES`
  - `vox settings` Recording section fields for the three keys
  - Clipboard restored ~150 ms after paste in `clipboard_and_paste`
  - Docs: `README.md`, `vox.toml.example`, `docs/dev/status.md`
- Verification commands:
  - `uv run vox`
  - `uv run vox settings`
  - `uv run python -c "from vox.config import get_config; c = get_config(); print(c['continuous_hotkey'], c['continuous_pause_seconds'], c['continuous_idle_minutes'])"`
  - `uv run python -c "import pyperclip; print(repr(pyperclip.paste()))"`
  - `uv run pytest tests/integration/test_streaming_vad_model.py -q`
  - `just quality && just test`

## DEFINITION OF VISIBLE DONE

A human on Windows 11 can verify completion directly:

1. **Setup:** `uv sync`. In `~/.vox/vox.toml` set `hotkey = "ctrl+shift+v"` and `injection_mode = "type"`, and leave the `continuous_*` keys unset.
2. **Launch:** `uv run vox`. The Stop window shows `Push-to-talk running.` and the console panel mentions `ctrl+alt+space`.
3. **Toggle on:** Open Notepad and click into it. Press `ctrl+alt+space`. The start cue plays and the Stop window label reads `Continuous dictation on.`
4. **Pause Commit:** Say "Hello world." and stop talking. About 1 s later `Hello world. ` appears in Notepad. Say "This is a second sentence." It appears after the first, in order, each followed by a space.
5. **Push-to-talk ignored:** While on, press and hold `ctrl+shift+v` and speak. No cue plays and nothing extra is recorded (only continuous Commits appear).
6. **Window switch:** Open a second Notepad window and focus it. Say a sentence and wait for it to appear there. Switch back to the first window, speak again, and confirm the text lands in the first window.
7. **Junk guard:** Tap the desk or cough once. Nothing is Injected, and the console shows a dim `Ignored short sound` or `No speech detected.` line.
8. **Toggle off commits pending:** Say a sentence and immediately press `ctrl+alt+space`, releasing the keys normally. The end cue plays, the label returns to `Push-to-talk running.`, the sentence still appears, and no Notepad shortcut fires (no Ctrl/Alt combos).
9. **Auto-off:** Set `continuous_idle_minutes = 0.5` and restart `uv run vox`. Toggle on and stay silent for 30 s. The end cue plays, the label returns to `Push-to-talk running.`, and the console shows `Continuous dictation turned off after`.
10. **Clipboard mode refusal:** Set `injection_mode = "clipboard"` and restart. Press `ctrl+alt+space`. No start cue plays, the console shows red `Continuous dictation unavailable:`, and the label shows `Continuous dictation off: ...`.
11. **Clipboard restore:** Set `injection_mode = "clipboard_and_paste"` and restart. Copy the word `ORIGINAL` in Notepad. Dictate with Push-to-talk into Notepad (text appears), then press Ctrl+V in Notepad: `ORIGINAL` is pasted. Repeat with Continuous dictation on and confirm the same.
12. **Mic failure:** Toggle on, then unplug the USB microphone (or disable it in Settings → System → Sound). Within about 2 s the end cue plays, the console shows red `Continuous dictation stopped: microphone input failed`, and the label shows the error.
13. **Tray:** `$env:VOX_TRAY="1"; uv run vox`. Hover the tray icon: `Vox — push-to-talk`. Toggle on and hover again: `Vox — continuous dictation on`.
14. **Settings + validation:** `uv run vox settings`. The Recording section shows Continuous hotkey, Pause before commit (s), and Idle auto-off (min). Set the continuous hotkey to `CTRL-SHIFT-V` (same as `hotkey`): the status shows an error and `~/.vox/vox.toml` is unchanged. Set pause to `1.5`: the file updates.
15. **Live rebind:** With `uv run vox` running, change Continuous hotkey to `ctrl+alt+d` in settings and close settings. The console prints `Rebound continuous hotkey:` and `ctrl+alt+d` now toggles.
16. **Env override:** `$env:VOX_CONTINUOUS_PAUSE_SECONDS="2.5"; uv run vox`. Commits now need a ~2.5 s Pause. The settings window shows the override note.

## INPUT/PREREQUISITE PROVENANCE

- Pre-existing dependency:
  - Python env with locked deps. Setup: `uv sync --all-groups` (repo `.venv` absent at plan time)
  - Silero VAD asset `faster_whisper/assets/silero_vad_v6.onnx`, shipped in the faster-whisper 1.2.1 wheel. Verify: `uv run python -c "import faster_whisper.vad as v; v.get_vad_model(); print('ok')"`
  - Whisper model (e.g. `base`), downloaded on first run by `load_model`. Pre-fetch: `uv run vox test-mic --seconds 1`
  - Microphone plus Windows microphone permission for manual steps
- Generated during this feature:
  - `uv.lock` specifier update via `uv lock`
  - User config edits via `uv run vox settings`

---

## ACCEPTANCE CRITERIA

- [ ] `continuous_hotkey` toggles Continuous dictation on/off with start/end cues; off at launch
- [ ] A Pause ≥ `continuous_pause_seconds` (Silero VAD, no new dependency) Commits the Utterance into the focused window with a trailing space
- [ ] Toggling off Commits any pending Utterance; in-flight Utterances are never discarded; Commits land in spoken order
- [ ] Utterances with <0.3 s speech and Whisper segments with `no_speech_prob > 0.6` are dropped with a visible dim line
- [ ] Auto-off after `continuous_idle_minutes` without detected speech, with end cue
- [ ] Push-to-talk hotkey ignored while Continuous dictation is on; Push-to-talk output otherwise unchanged
- [ ] `clipboard` mode refuses Continuous dictation with a visible error; `clipboard_and_paste` restores previous clipboard text ~150 ms after paste in both modes
- [ ] Mic failure mid-session turns Continuous dictation off with a visible error
- [ ] Stop window label and tray tooltip reflect state
- [ ] New keys: config validation (incl. collision), env overrides, settings fields (restart-required), `vox.toml.example`, README
- [ ] No new dependencies; no new suppression comments; dispatch tables used for mode branching
- [ ] All validation commands pass with zero errors and zero warnings; coverage ≥85%; diff-cover ≥80%
- [ ] Output artifacts and verification commands are present
- [ ] Definition of Visible Done steps 1-16 pass on Windows 11

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order, checkboxes updated live
- [ ] Each task validation passed immediately
- [ ] One commit per phase (Phase 4: dep-floor commit + feature commit; Phase 7: GUI state commit + settings commit; Phase 8 docs-only)
- [ ] Full test suite passes (unit + integration)
- [ ] No linting, typing, complexity, dead-code, docstring, or duplication errors
- [ ] Manual Windows validation confirms the Definition of Visible Done
- [ ] Execution Report appended

---

## NOTES

### Design decisions

- **Streaming VAD approach:** carry Silero `h`/`c` and the 64-sample context per 512-sample frame via `SileroVADModel.session.run`. The rejected alternatives:
  - The public `__call__` per frame resets state (max error 0.52 in the probe).
  - Re-running a rolling window through `__call__` costs O(window) per hop, and its first windows are cold.
  - `get_speech_timestamps` is offline-only.

  The chosen approach reproduced batch output exactly (diff 0.0) at ~0.16 ms/window. It depends on faster-whisper internals, which is mitigated by the `>=1.2.1` floor, the input-name contract check, and the integration test.
- **Detector clock = audio sample count:** deterministic, needs no injected wall clock for Pause or idle. Wall-clock time (`deps.clock`) is used only for the stall watchdog, where no audio arrives by definition.
- **Two session threads:** control/listening (stream, VAD, detector) and commit processor (transcribe, filter, Inject). Transcription never blocks listening, and one consumer guarantees spoken order.
- **Toggle handoff:** listener → `request_toggle()` enqueue only (Windows low-level hook latency).
- **Modifier wait before Injection:** the toggle-off Commit can happen while Ctrl+Alt are still held. Injection waits up to 2 s for release, then warns and proceeds. Bounded, because Windows secure-desktop actions (Ctrl+Alt+Del, Win+L) can swallow key-up events and leave stale state.
- **Most-specific combo wins** when PTT and toggle combos overlap, because `register.py:211` uses subset matching.
- **Clipboard restore is synchronous** on the processor thread, restores only non-empty text, and only if the clipboard still holds the injected text.
- **Junk filter is continuous-only:** `transcribe()` is unchanged, so Push-to-talk output is unchanged (agreed item 4).
- **Settings fields go in the Recording section** to keep `SETTINGS_SECTIONS` stable.

### Risks

- faster-whisper internal API drift (`session`, I/O names) in future 1.x releases. Guarded by the floor, contract check, and integration test.
- Stale modifier state (missed key-ups) is healed on Windows via `GetAsyncKeyState` reconciliation; on macOS/Linux a stale state can still add up to 2 s to a toggle-off Commit or mis-route a toggle press. Only the toggle-off Commit waits, so Pause Commits are unaffected.
- Device-removal behavior differs by PortAudio host API; the 2 s stall watchdog is the catch-all.
- Clipboard restore races slow paste consumers (Electron/RDP) at 150 ms: the old clipboard could be pasted instead of the transcription.
- Threaded tests can flake. Use event waits with timeouts and always `shutdown()` in `finally`.
- Existing users with `hotkey = "ctrl+alt+space"` get a startup `ConfigError` after upgrade (fail-fast by agreed design).
- Release binaries: `--collect-data faster_whisper` is added in Phase 4, but it is only exercised by a real release build (the release smoke test runs `--help` only). Verify continuous dictation in the first release binary.
- `settings_window.py` is already 1141 lines; the capture-helper extraction must not regress existing capture UX.

### Open Questions

Resolved with the user on 2026-09-16 (see Plan Patch):

1. **App quit while on or in-flight:** quitting is best-effort. Commits that finish within the existing Stop/Quit join timeouts (`stop_window.py:161`, `tray.py:153`) are delivered; the rest are dropped. "Never discards" applies to toggling off only. Document in README (Phase 8).
2. **"Visible error" surface:** end cue + Stop-window label / tray tooltip + a Windows tray notification for error states (Phases 5 and 7).
3. **Release binaries:** add `--collect-data faster_whisper` (Phase 4 task).
4. **Upgrade collision:** a startup `ConfigError` is acceptable; the message names the fix.
5. **Unverifiable library details:** still open. Confirm in `.venv` during Phases 6-7: pystray `Icon.title` live update and `notify` on win32; pynput 1.8.1 Controller-typed space (`VK_PACKET`) vs `Key.space`; PortAudio/WASAPI behavior on mic unplug.
6. **Empty clipboard snapshot:** accepted. Restore is skipped when the snapshot is empty or non-text, leaving the transcription on the clipboard.

**Confidence Score**: 7/10 that one-pass implementation succeeds

## Plan Patch

### 2026-09-16 — user answers + review fixes (before execution)

- **Quit semantics:** best-effort drain within existing join timeouts; no new shutdown wait (Open Question 1).
- **Error visibility:** clipboard-mode refusal and VAD/stream start failures now play the end cue (previously silent). Tray mode raises a Windows notification for error states via `describe_tray_notification` + `icon.notify` (Phases 5, 7).
- **Stale modifiers:** `ModifierTracker` reconciles against physical key state on Windows (`keystate.py`, `GetAsyncKeyState` via stdlib ctypes). Prevents Space presses toggling continuous dictation after Ctrl+Alt+Del swallows key-ups (Phases 5, 6).
- **Modifier wait scope:** only the Commit produced by a user toggle-off waits for modifier release; Pause Commits never wait (Phase 5).
- **Release binaries:** `--collect-data faster_whisper` added to the PyInstaller build as a separate `ci:` commit (Phase 4).
- **Non-text clipboard:** skip restore (Open Question 6), unchanged from draft.

## Execution Report

(append one entry per completed phase: status, phase intent check, files changed, commands run with pass/fail, output artifacts verified, partial/blocked items)
