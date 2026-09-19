---
name: parallelism
description: Use when a request contains genuinely independent implementation work that could run concurrently. The current session is the Master and implements work directly; it spawns optional helper sessions only for concrete, independent tasks, then integrates, tests, reviews and reports itself. Not for ordinary single-threaded coding, questions, or docs.
---

# parallelism — Master session + optional helper workers

The current OpenCode session **is the Master**. There is no separate
orchestration agent, no autonomous supervisor, and no continuous background
scheduling. One Master authority, zero helpers by default.

## Default: one session, zero helpers

Do the work directly in this session. Spawn a helper only when **all** hold:

- two or more independent implementation tasks can proceed concurrently;
- each has a concrete deliverable, acceptance criteria, explicit file ownership,
  and an isolated worktree;
- the work is large enough that coordination costs less than doing it serially.

Never spawn helpers for questions, docs, trivial edits, or to "use spare
concurrency". Never create planner/reviewer/tester/auditor/integrator/security/
documentation/release sessions by default. No idle sessions, no
worker→reviewer→worker loops, no background LLM polling. Helpers must not spawn
helpers. A configurable helper limit caps concurrency; the normal default is 0.

## Model inheritance (mandatory)

Every helper runs on the Master's **actual** effective provider/model.

1. **Resolve** — the Master knows its own model from its own context (the
   `exact model ID` in its system prompt). `scripts/parallelism.py resolve-model`
   accepts `--model`, else `PARALLELISM_MASTER_MODEL`, else the resolved project
   config model; it **fails** rather than guess.
2. **Pass** it explicitly as `--model provider/model-id`.
3. **Verify** — `scripts/parallelism.py verify-model --session <id> --expect <model>`
   reads the helper's stored session model and fails on mismatch.
4. **Record** it in the helper checkpoint.

Never hardcode a model (no DeepSeek/OpenCode Go/etc.). If the model cannot be
resolved or verified, do not spawn. Already-running helpers keep their original
model. If the Master changes models, later helpers inherit the new selection
without editing this skill. Never silently fall back to another provider/model.

## Lifecycle (minimal)

`ASSIGNED → WORKING → VALIDATING → COMPLETED`, plus `BLOCKED`, `FAILED`,
`CANCELLED`. A helper implements its assignment, runs focused tests, commits
when appropriate, returns a compact report, and stops consuming LLM usage:

- commit SHA (or explicit no-commit outcome)
- changed files
- acceptance results
- test results
- blockers, if any

Do not re-dispatch a helper for information already in its checkpoint.

## Master-owned integration

When a dependency-ordered batch is ready the Master integrates directly:
collect commits → acquire the exclusive integration lock → verify ownership and
branch ancestry → integrate in dependency order → resolve conflicts → run
integration tests → ordinary final review → required broader regression checks →
record evidence → release the lock → report.

The Master obeys the same ownership rules as helpers: one writer per branch and
worktree, never concurrent integration writers, never modify `main` or publish,
deploy, or promote without explicit authorization. Do not wait indefinitely for
unrelated or externally blocked tasks.

## Token-efficiency rules

- Prefer deterministic CLI (`git`, test commands, `scripts/parallelism.py`) over
  LLM calls for dependency checks, git status, process monitoring, locks, test
  execution, and duplicate detection. Never use an LLM merely to poll a session.
- Give each helper only: requirements, necessary project rules, relevant file
  references, ownership boundaries, acceptance criteria, and required test
  commands. Never copy the full Master conversation or orchestration history.
- **No-progress detection** uses meaningful progress (commits, acceptance
  evidence, test results, blocker changes) — not a bare unchanged tree. If
  repeated checks show no meaningful progress, stop redispatch and park the task
  (`parallelism.py progress`). Do not re-review identical candidates.
- Concise, structured reports; do not repeat unchanged status or whole logs, but
  never drop required evidence or error detail.
- Project-mandated independent verification for security-sensitive or
  release-critical changes is preserved via a temporary, narrowly scoped session
  after a stable candidate exists — never a permanent role. Required checks are
  never skipped to save tokens.

## Script

`scripts/parallelism.py` (Python stdlib only): `resolve-model`, `verify-model`,
`spawn`, `checkpoint`, `status`, `progress`, `lock acquire|release`. It never
merges, never deploys, and never starts a background service.

## Project specifics

Project paths, agents, model policy, test commands, security gates and release
rules belong in the project's `AGENTS.md`, not here. This skill is model-agnostic
and reusable beyond any single project.
