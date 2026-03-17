# Product Requirements Document: Vox — Push-to-Talk Voice Input Layer

**Spec ID:** 001-push-to-talk  
**Version:** 0.1.0  
**Status:** Draft  
**Source:** [Branch · Push-to-talk transcription in Python](docs/ideas/2026-03-17_13-49-14__Branch-Push-to-talk-transcription-in-Python__chat.json)

---

## 1. Executive Summary

**Vox** is the voice input layer for the system. It is not “just Whisper”—it is the layer through which spoken intent enters the entire workflow and agent pipeline. The product captures speech via push-to-talk, transcribes it locally using **faster-whisper** (CTranslate2-based Whisper: faster and lower-memory than stock Whisper), and injects the resulting text into the active target (focused application or downstream pipeline) so that voice becomes actionable input with minimal friction.

The core value proposition is **speed and immediacy**: the user presses a key, speaks, and the text appears where they need it—no switching context, no copy-paste, no cloud dependency. This makes Vox a small, sharp tool designed for daily workflow: an always-available assistant interface that fits into an ecosystem of agents (e.g., Pepper, OpenClaw, GROVE, HQ) by acting as the single place where “voice enters the system.”

The **MVP goal** is a working push-to-talk experience: global hotkey (or equivalent) triggers recording; speech is transcribed locally; the resulting text is injected into the system (e.g., clipboard and/or simulated keystrokes into the focused window). The product should be nameable and growable—not a throwaway script but something kept and extended (e.g., tray icon, config system, agent wiring) in later phases.

---

## 2. Mission

**Mission statement:**  
Vox is the voice input layer. Voice enters the system through Vox; agents don’t listen—Vox listens for them.

**Core principles:**

1. **Voice → action** — Every interaction should reduce to: speak → text appears where it’s needed. No unnecessary steps.
2. **Speed and immediacy** — “Press the key, whisper, it appears.” Latency and friction must be minimized so the tool feels instant and reliable.
3. **System integration** — Vox is a system-level utility. It must integrate with the OS (focus, clipboard, input injection) and with the broader agent/workflow ecosystem, not act as an isolated app.
4. **Local-first and keep-and-grow** — Transcription runs on-device; the design supports future expansion (voice commands, agent wiring, config, tray) without rewriting the core.
5. **Small, sharp tool** — One clear job done well: capture intent via voice and turn it into text in the right place. Avoid scope creep in MVP; defer advanced features to later phases.

---

## 3. Target Users

**Primary persona: operator of an agent/workflow system**

- Uses or plans to use systems like GROVE (context), HQ (control center), Pepper (COO), OpenClaw, or similar.
- Wants voice as a first-class input channel into that ecosystem.
- Technical comfort: can install Python tools, configure hotkeys, and troubleshoot mic/permissions.
- May work in environments where hands are busy (coding, writing, controlling other tools) and voice is the most efficient input.

**Key user needs and pain points**

- **Need:** Speak and have text appear in the active window or pipeline without switching apps or pasting.
- **Need:** No dependency on cloud transcription for privacy, latency, or offline use.
- **Need:** A single, consistent “voice input” layer that can later feed multiple consumers (agents, notes, chat).
- **Pain:** Generic “speech-to-text” tools feel like separate apps, not part of the system.
- **Pain:** Throwaway scripts are hard to configure, extend, and run reliably (e.g., as a background service with tray and config).

---

## 4. MVP Scope

### In scope (MVP)

**Core functionality**

- ✅ Push-to-talk interaction: user holds (or toggles) a key; recording is active only while key is held or toggled on.
- ✅ Local speech capture from default (or configured) microphone.
- ✅ Local transcription using **faster-whisper** ([SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)): CTranslate2-based Whisper reimplementation, up to 4× faster than openai/whisper with lower memory use; no system FFmpeg required (PyAV).
- ✅ Text injection into the system: at minimum, place transcribed text on the system clipboard; optionally support “paste” or “type into focused window” for immediacy.
- ✅ Invocation by a global hotkey (or equivalent) so the tool is always-available regardless of focused application.
- ✅ CLI entry point and/or minimal programmatic API so the behavior can be scripted or wrapped (e.g., by a future tray/service).

**Technical**

- ✅ Python 3.12+, with dependencies managed via `uv` and project layout under `src/vox` per repository conventions.
- ✅ Configuration via file and/or environment (e.g., hotkey, device, model path/size) without hardcoding.
- ✅ Clear, actionable errors (e.g., mic not available, model not found, permission denied) with no silent fallbacks for required contract fields.

**Integration**

- ✅ Output suitable for consumption by other tools: clipboard and/or typed injection; structured output (e.g., plain text) so future agents can consume it.

### Out of scope (deferred)

**Core functionality**

- ❌ Continuous listening / wake-word activation (deferred to a later phase).
- ❌ Full natural-language “voice commands” (e.g., “send to Pepper”) — MVP is transcription + injection only.
- ❌ Built-in agent wiring (Pepper, OpenClaw, GROVE) — MVP provides the input layer; integration is a later phase.

**Technical / UX**

- ❌ Tray icon and “background service” UX — MVP can be a runnable process (e.g., blocking or minimal daemon); tray and lifecycle management deferred.
- ❌ Rich GUI for settings — CLI/config file and env are sufficient for MVP.
- ❌ Cloud transcription or hybrid cloud/local — MVP is local-only.
- ❌ Multi-language or dialect selection beyond what the chosen model supports by default (can be documented; no extra UX in MVP).

**Deployment**

- ❌ Packaged installer (e.g., MSI, .app) — MVP is “run from repo” or “install via uv/pip” for technical users.
- ❌ Cross-platform parity in one release — MVP can target one primary OS (e.g., Windows or macOS) with notes for others; full parity later.

---

## 5. User Stories

1. **As a** user working in an editor or chat, **I want to** press a key, speak a sentence, and have the text appear in the active field, **so that** I can keep my hands on the keyboard or busy elsewhere and still input text quickly.

2. **As a** privacy-conscious user, **I want** all transcription to run on my machine, **so that** nothing I say is sent to the cloud and I can work offline.

3. **As a** power user, **I want** a global hotkey that works in any application, **so that** I don’t have to focus a separate “transcription app” and then copy-paste.

4. **As a** builder of agent workflows, **I want** Vox to produce plain text (and optionally structured output) in a well-defined way, **so that** I can later pipe that output into Pepper, GROVE, or other agents without changing Vox’s core behavior.

5. **As a** technical user, **I want** to configure the hotkey, microphone, and model via config file or environment, **so that** I can adapt Vox to my setup without editing code.

6. **As an** operator, **I want** clear errors when the mic is unavailable or permissions are missing, **so that** I can fix the environment instead of guessing why nothing happens.

7. **As a** maintainer, **I want** Vox implemented as a small, focused Python package under `src/vox` with tests and quality gates, **so that** we can extend it later (tray, voice commands, agent wiring) without rewriting the core.

8. **As a** user, **I want** the tool to feel fast and predictable (“press the key, whisper, it appears”), **so that** it becomes a daily habit rather than a rarely used experiment.

---

## 6. Core Architecture & Patterns

### High-level approach

- **Pipeline:** Capture (mic) → Transcribe (local model) → Inject (clipboard and/or keystroke).
- **Invocation:** Global hotkey (or equivalent) starts recording; release or second press stops recording and runs the pipeline.
- **Layering:** Vox is the input layer; it does not implement agents. Downstream systems (Pepper, GROVE, etc.) consume text that Vox produces.

### Directory structure (conceptual)

```text
src/vox/
├── __init__.py
├── cli.py              # CLI entry (e.g., vox run, vox record)
├── capture/            # Audio capture (device selection, stream, stop on key release)
├── transcribe/         # Local model invocation (faster-whisper)
├── inject/             # Clipboard and/or keyboard injection
├── config.py           # Load config from file/env
└── hotkey/             # Global hotkey registration (platform-specific)
tests/
├── unit/
├── integration/
└── e2e/                # Optional: end-to-end “record → transcribe → inject”
```

- `scripts/` may contain operational helpers (e.g., “run Vox with default config”).
- `docs/dev/` holds status, roadmap, and debt per repository conventions.

### Design principles

- **Explicit contracts:** Capture, transcribe, and inject are separate concerns with clear interfaces (e.g., protocols or abstract classes) so they can be tested and swapped (e.g., different injectors: clipboard vs. keystroke).
- **Strategy/registry over long if/elif:** For injection strategies or future transcription backends, use a small registry or strategy pattern rather than long conditionals; MVP uses a single backend (faster-whisper).
- **Fail-fast and validate:** No silent fallbacks for required config or device selection; surface field-specific errors.
- **Untrusted inputs:** Treat all captured audio and any external config as untrusted; validate and bound inputs before passing to model or system APIs.

### Technology-specific patterns

- Prefer `uv run python` (or `python3`) in docs and scripts.
- Use `tmp_path` in tests; no hardcoded global temp paths.
- Dependencies added only with plan rationale; no blanket lint/type suppressions without documentation.

---

## 7. Tools / Features

### 7.1 Push-to-talk (core loop)

- **Purpose:** Provide the primary user interaction: start/stop recording with a single key.
- **Operations:**
  - Register global hotkey (configurable).
  - On key down (or toggle on): start capturing audio from the selected device.
  - On key up (or toggle off): stop capture, run transcribe, then inject.
- **Key features:** Configurable key combination; optional “toggle” vs “hold” mode; visual or audible feedback (e.g., minimal console or log) so the user knows when recording is active (optional in MVP but desirable).

### 7.2 Audio capture

- **Purpose:** Record raw audio from the microphone for the duration of the push-to-talk session.
- **Operations:** Open stream on configured device; record until stop; return audio buffer (e.g., PCM) in a format the transcriber expects.
- **Key features:** Default device or configurable device ID; sample rate and format aligned with the transcription model; handling of no device / permission denied with clear errors.

### 7.3 Transcription

- **Purpose:** Convert captured audio to text using **faster-whisper** (CTranslate2-based Whisper).
- **Operations:** Accept audio buffer (format compatible with faster-whisper, e.g. WAV or PCM at 16 kHz); load `WhisperModel` by size or path; run `transcribe()`; return plain text (and optionally segments/timestamps for future phases). Iterate segments to force completion (generator contract).
- **Key features:** Model size configurable (e.g., `tiny`, `base`, `small`, `medium`, `large-v3`, or `turbo` for speed; see [faster-whisper](https://github.com/SYSTRAN/faster-whisper)); optional `int8` compute type for lower memory on CPU/GPU; no cloud calls; no system FFmpeg (PyAV used by faster-whisper); errors when model is missing or inference fails.

### 7.4 Injection

- **Purpose:** Make the transcribed text available to the user and to the system.
- **Operations:**
  - **Clipboard:** Set system clipboard to the transcribed text (minimum).
  - **Keystroke (optional):** Simulate “paste” or type the text into the focused window so the user sees it immediately without a manual paste.
- **Key features:** At least one injection path required; clear behavior when injection fails (e.g., clipboard only); no silent truncation or substitution of the transcribed text.

### 7.5 Configuration

- **Purpose:** Control hotkey, device, model, and injection strategy without code changes.
- **Operations:** Load from config file (e.g., `vox.toml` or `.vox.yaml`) and/or environment variables; validate required fields and fail with explicit errors.
- **Key features:** Documented config schema; example config in repo; override via env for CI/scripting.

### 7.6 CLI

- **Purpose:** Start the push-to-talk loop and expose any secondary commands (e.g., “test mic,” “list devices”).
- **Operations:** e.g. `vox run` (main loop), `vox devices` (list audio devices), `vox test-mic` (record for N seconds, then **play back** the recording so the user can verify capture; optionally run transcribe and print text).
- **Key features:** Rich-style output (tables/panels) for user-facing commands per project rules; no raw JSON as default interactive output.

---

## 8. Technology Stack

### Backend / runtime

- **Language:** Python ≥ 3.12.
- **Package manager / runner:** `uv` for install and `uv run` for execution.
- **Build:** Hatchling; package in `src/vox` per repository layout.

### Core dependencies (MVP)

- **Audio capture:** Library for device enumeration and recording (e.g., `sounddevice`, `pyaudio`, or `numpy` + device backend). To be chosen in implementation plan with rationale. Output must be compatible with faster-whisper input (e.g., 16 kHz mono for Whisper; faster-whisper uses PyAV, no system FFmpeg required).
- **Transcription:** **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** (PyPI: `faster-whisper`). CTranslate2-based reimplementation of OpenAI Whisper; up to 4× faster and lower memory than openai/whisper; supports CPU (fp32/int8) and GPU (CUDA 12, cuDNN 9, fp16/int8). Model sizes: `tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3`, `turbo`, or Distil variants (e.g. `distil-large-v3`). Pin exact version in implementation plan; models auto-download from Hugging Face or load from local path.
- **Injection:** Clipboard (e.g., `pyperclip` or platform-specific); optional keyboard simulation (e.g., `pynput`, `pyautogui`) for “type into focused window.”
- **Hotkey:** Global hotkey registration (e.g., `keyboard`, `pynput`, or platform-native). Choice to be justified in plan (e.g., permissions, cross-platform).

### Optional / deferred

- Tray icon / GUI: deferred.
- Agent SDKs (Pepper, GROVE, etc.): deferred to integration phase.
- Streaming / chunked transcription: deferred if needed for latency improvements.

### Third-party integrations (post-MVP)

- **GROVE / HQ / Pepper / OpenClaw:** Consume text produced by Vox (clipboard or API); no direct dependency in MVP.
- **OS input APIs:** Use only well-documented, secure patterns for clipboard and keyboard simulation; respect user permissions and security boundaries.

---

## 9. Security & Configuration

### Authentication / authorization

- MVP has no remote services; no auth. If future phases add agent or cloud endpoints, auth will be scoped in a later spec.

### Configuration management

- **Primary:** Config file in a standard location (e.g., `~/.config/vox/vox.toml` or project-local `vox.toml`).
- **Override:** Environment variables for hotkey, device, model path, and injection mode where sensible.
- **Secrets:** MVP does not require secrets; any future API keys or tokens will be stored via env or a secure store, not in config file in plain text.

### Security scope

- **In scope:** Validate and bound audio and config inputs; safe handling of subprocess/model invocation; no arbitrary code execution from config; clear trust boundaries for mic and injection.
- **Out of scope:** Network encryption, auth, and rate limiting (no network in MVP); formal threat model (can be added in a later phase).

### Deployment

- MVP: run from repo with `uv run` or install as editable package. No installer or packaged service; document any OS-specific permissions (e.g., microphone, accessibility for global hotkey and injection).

---

## 10. API Specification

### CLI surface (MVP)

- `vox run` — Start push-to-talk loop (default command). Reads config; registers hotkey; on trigger: capture → transcribe → inject.
- `vox devices` — List available audio input devices (names and IDs) for config.
- `vox test-mic [--device ID] [--seconds N]` — Record for N seconds, **play back** the recording (so the user can verify the mic and level), then optionally run transcribe and print text; output success or error.

No REST API in MVP. Internal Python APIs (e.g., `capture.capture_until_stop()`, `transcribe.run(audio)`, `inject.to_clipboard(text)`) are implementation details; they should have clear function signatures and contracts for testability.

### Output contract

- **Transcription output:** Plain UTF-8 text. No required schema beyond “string.” Optional future: structured (e.g., segments with timestamps) for agent consumers.
- **Clipboard:** Exact transcribed text; no truncation or modification without explicit config.
- **Errors:** Stderr or structured error code; messages must be actionable (e.g., “Microphone access denied” with hint to check OS permissions).

---

## 11. Success Criteria

### MVP success definition

- A user can install Vox (e.g., from repo with `uv`), configure a hotkey and (optionally) device, run `vox run`, press the hotkey, speak, release the key, and see the transcribed text in the clipboard (and optionally in the focused window) with no cloud calls and no silent failures for valid input.

### Functional requirements

- ✅ Push-to-talk triggers recording for the duration of the key press (or toggle).
- ✅ Audio is captured from the configured (or default) microphone.
- ✅ Transcription runs locally using the specified (or default) model.
- ✅ Transcribed text is placed on the system clipboard at minimum.
- ✅ Optional: transcribed text is injected into the focused window (paste or type).
- ✅ Global hotkey works when another application is focused (subject to OS permissions).
- ✅ Configuration is loaded from file and/or env; missing required fields produce explicit errors.
- ✅ CLI commands `vox run`, `vox devices`, and `vox test-mic` behave as specified.
- ✅ All quality gates pass: `just quality && just test`; no new warnings without documented rationale.

### Quality indicators

- Unit tests for capture, transcribe, and inject in isolation (with mocks where appropriate).
- Integration test: record a short fixture → transcribe → verify text (and optionally injection).
- Lint, format, types, and security checks (ruff, mypy, bandit, etc.) passing per repository rules.
- Documentation: README and config schema describe how to run and configure Vox.

### User experience goals

- **Immediacy:** Time from “key up” to “text available” feels short (target: document acceptable latency in plan; optimize in later phase if needed).
- **Predictability:** Same action (press key, speak, release) always produces the same class of outcome (success or clear error).
- **Clarity:** Errors are human-readable and point to next steps (e.g., “Set microphone permission in System Preferences”).

---

## 12. Implementation Phases

### Phase 1: Foundation and capture (Goal: runnable capture pipeline)

- **Goal:** Project skeleton under `src/vox`, config loading, and audio capture with a configurable device. No transcription or injection yet.
- **Deliverables:**
  - ✅ Package layout in `src/vox` with `cli`, `config`, `capture` modules.
  - ✅ Config schema and loading from file/env; validation with clear errors.
  - ✅ List devices CLI (`vox devices`) and test-mic that records for N seconds and **plays back** the recording (so the user can verify capture and level).
  - ✅ Unit tests for config and capture; `just quality && just test` passing.
- **Validation:** `vox devices` and `vox test-mic` (record → play back) run successfully on at least one supported OS.
- **Estimate:** ~1–2 weeks (depending on device layer choice and OS quirks).

### Phase 2: Local transcription (Goal: audio → text)

- **Goal:** Integrate **faster-whisper**; input = captured audio buffer, output = plain text.
- **Deliverables:**
  - ✅ `transcribe` module using `faster_whisper.WhisperModel`; model size/path and compute type (e.g. `int8` for CPU) in config.
  - ✅ Audio capture output converted to format expected by faster-whisper (e.g. file or buffer at 16 kHz mono).
  - ✅ `vox test-mic` runs capture → play back → (optional) transcribe and prints text.
  - ✅ Unit tests for transcribe (e.g., with fixture audio); integration test for capture → transcribe.
  - ✅ Documentation for model download (auto from Hugging Face or local path) and optional GPU (CUDA 12 / cuDNN 9) or CPU/int8 setup.
- **Validation:** Short spoken phrase in a test fixture is transcribed correctly in CI or local run.
- **Estimate:** ~1–2 weeks.

### Phase 3: Injection and hotkey (Goal: full push-to-talk loop)

- **Goal:** Clipboard (and optionally keystroke) injection and global hotkey; end-to-end “press key, speak, release, text appears.”
- **Deliverables:**
  - ✅ `inject` module: clipboard required; optional “paste into focused window” or type simulation.
  - ✅ Hotkey registration (platform-specific); configurable key; start/stop recording on key events.
  - ✅ `vox run` runs the full loop: hotkey → capture → transcribe → inject.
  - ✅ Integration or e2e test that simulates trigger and verifies clipboard (and optionally focus behavior where testable).
  - ✅ Error handling for mic unavailable, model error, injection failure.
- **Validation:** Manual test: focus a text field, press hotkey, speak, release; transcribed text appears (clipboard and/or in field).
- **Estimate:** ~1–2 weeks.

### Phase 4: Polish and docs (Goal: shippable MVP)

- **Goal:** UX polish, docs, and any remaining quality/debt items.
- **Deliverables:**
  - ✅ README and config example; “Definition of Done” checklist for manual verification.
  - ✅ Rich-style CLI output where applicable (tables/panels for `vox devices` etc.).
  - ✅ Any accepted warnings documented with rationale; security and dependency review.
  - ✅ Optional: latency or robustness improvements identified and either implemented or logged as future work.
- **Validation:** New user can follow README to install, configure, and run push-to-talk successfully.
- **Estimate:** ~3–5 days.

---

## 13. Future Considerations

### Post-MVP enhancements

- **Background service and tray:** Run Vox as a background process with system tray icon; start/stop and basic settings from tray.
- **Voice commands:** Interpret certain phrases as commands (e.g., “send to Pepper”) and route text to specific agents or workflows.
- **Agent wiring:** Formal integration with Pepper, OpenClaw, GROVE, HQ (e.g., send transcribed text to a queue or API that those systems consume).
- **Streaming / lower latency:** Chunked or streaming transcription and injection to reduce perceived delay.
- **Multi-language and dialect:** Explicit language/dialect selection and tuning once multiple models or settings are supported.

### Integration opportunities

- **GROVE:** Supply transcribed segments as context or events.
- **HQ:** Show “last spoken” or “pending injection” in a control panel.
- **Pepper / OpenClaw:** Consume Vox output as the primary voice input channel for task and workflow handling.

### Advanced features (later phases)

- Wake word or continuous listening (with clear privacy and battery trade-offs).
- Custom vocabulary or domain-specific models.
- Packaged distribution (installer, auto-update) for less technical users.

---

## 14. Risks & Mitigations

| Risk | Mitigation |
|------|-------------|
| **Microphone or accessibility permissions** (OS blocks capture or global hotkey) | Document required permissions per OS; detect and report clear errors; provide `vox test-mic` and `vox devices` for troubleshooting. |
| **Transcription latency** (model too slow; user perceives delay) | Choose small model (e.g., tiny/base) for MVP; document latency expectations; design pipeline for future streaming/chunking. |
| **Model size and disk/CPU** (faster-whisper model too large or slow on target hardware) | Make model size configurable (e.g. `tiny`/`base`/`small`); document minimum specs; consider `tiny` or `base` as default; offer `int8` compute type for lower memory; document upgrade path to `turbo`/`large-v3`. |
| **Injection reliability** (clipboard/keystroke fails on some apps or OS versions) | Prefer clipboard as default; document known limitations; optional injectors behind config; fail with clear message. |
| **Global hotkey conflicts or permissions** (another app or OS restricts hotkeys) | Document conflict resolution; allow configurable key; detect and report when registration fails. |

---

## 15. Appendix

### Related documents

- **Repository rules:** `.ai/RULES.md` — workflow, quality gates, architecture boundaries.
- **CLI/output UX:** `.ai/REF/project-types/cli-tool.md` — Rich output, no raw JSON by default, validation expectations.
- **Conversation source:** `docs/ideas/2026-03-17_13-49-14__Branch-Push-to-talk-transcription-in-Python__chat.json` — naming, product direction, ecosystem role.

### Key dependencies (to be pinned in implementation)

- Python ≥ 3.12.
- `uv` for dependency and run management.
- **faster-whisper** ([SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper)); exact PyPI version pinned in implementation plan.
- Audio I/O and hotkey libraries; choices and versions to be justified in plan.

### Repository structure (relevant parts)

- `src/vox/` — Active Vox package (to be created).
- `tests/` — Unit, integration, e2e (to be created).
- `scripts/` — Operational scripts (optional).
- `docs/dev/` — Status, roadmap, debt (per `.ai/REF/status-surfaces.md`).
- `.ai/PLANS/` — Implementation plan(s) for this spec (e.g., `001-push-to-talk.md`).

---

*This PRD captures all ideas from the source conversation (naming, role of Vox as input layer, push-to-talk, local transcription, system injection, ecosystem fit, future tray/config/agent wiring), specifies [faster-whisper](https://github.com/SYSTRAN/faster-whisper) as the MVP transcription engine, and aligns the rest with repository conventions and a phased, testable MVP.*
