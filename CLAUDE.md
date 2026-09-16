# Agent Guidance for Vox

Coding agents working in this repository should follow the rules and conventions defined in:

- **`.ai/RULES.md`** — Workflow invariants, quality gates, architecture boundaries, and project-type rules.

Use `src/vox` and the conventions in `.ai/RULES.md` for all implementation work.

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues for `jeffrichley/vox`, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
