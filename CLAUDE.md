# Vox

Local Push-to-talk and Continuous dictation voice input: capture speech, transcribe with faster-whisper, inject text. Runtime code lives in `src/vox`; tests in `tests/unit` and `tests/integration`. Domain terms are defined in `CONTEXT.md`; use them.

## Workflow

- Work on a feature branch; never commit directly to `main`.
- Before commit or PR, run the full gate: `just quality && just test`. CI runs `just quality-check` + `just test-cov` and requires ≥80% diff coverage on changed lines.
- Treat test and runtime warnings as defects. Fix them, or document why a residual warning is accepted.
- PR descriptions follow `.github/pull_request_template.md`: state what is complete, what is temporary, and what is deferred.
- Prefer `uv run python` over bare `python` in docs and scripts.

## Code standards

- No new dependencies without a stated rationale in the issue or PR.
- No suppression comments (`# nosec`, `type: ignore`, lint disables) unless the reason is documented next to them.
- Keep strict typing clean (mypy, pyright). Prefer upstream stubs over local ignores; match protocol parameter names exactly.
- Prefer dispatch tables or registries over long `if`/`elif` chains when branching by mode, backend, or type.
- Fail fast on invalid or missing config with field-specific errors; no silent fallback defaults. Vox never fails silently.
- User-facing CLI output uses Rich (tables, panels), not raw JSON.
- Treat runtime and model inputs as untrusted: validate subprocess, network, and model-download boundaries; pin model revisions where applicable.

## Tests

- pytest with `pytest-drill-sergeant`: markers required, Arrange/Act/Assert structure, test files ≤350 lines.
- Coverage ≥85% (`src/vox/gui/*` excluded).
- Use `tmp_path`; no hardcoded temp paths.

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues for `jeffrichley/vox`, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
