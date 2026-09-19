---
name: parallelism
description: Use when a request contains genuinely independent implementation work that could run concurrently. The current session is the Master and implements work directly; it spawns optional helper sessions only for concrete, independent tasks, then integrates, tests, reviews and reports itself. Not for ordinary single-threaded coding, questions, or docs.
---

# parallelism — Master session + optional helper workers (v1.2)

The current OpenCode session **is the Master**. No separate orchestration agent,
no autonomous supervisor, no background scheduling, no role pipeline. One Master
authority; zero helpers by default.

## Decide before spawning

Implement directly unless independent execution clearly beats sequential:

- **2+ tasks** that are genuinely independent;
- **low overlap** in owned files (divergent scopes);
- **low initialization** and **low integration** cost;
- enough local resources to run them concurrently.

`scripts/parallelism.py decide --tasks N --independence … --overlap … --init-cost
… --integration-cost …` returns a deterministic `parallel`/`sequential`
recommendation. The Master decides from this — **never** by spending another LLM
call on the question. If the benefit is unclear, do it yourself.

## Worker identity, idempotent dispatch, recovery

- Each helper has a **stable id** (`--id`, default = name). The checkpoint records
  id, branch, worktree, model, pid, owned files, status — nothing more.
- `spawn` is **idempotent**: a live worker with the same id is never duplicated
  (it refuses); a finished worker requires a new id (or `--force`).
- A worker whose pid died mid-flight is reported as `interrupted`; re-dispatch
  only with `--resume`, which **reconciles in place** (same worktree/id) instead
  of spawning a blind replacement. A resumed Master runs `status` first and
  reuses/reconciles existing workers.
- Conflicting ownership is rejected before dispatch: two live workers cannot own
  the same file.

## Minimal worker contract

Prefer `--objective --owns --excludes --accept --tests` (the script writes the
contract); or pass `--assignment <file>`. Each helper gets only: objective, owned
files, excluded files, acceptance criteria, required tests, required project and
safety rules, and the completion output — never the full Master conversation.
Helpers must not spawn further helpers, and must stop generating messages once
their assignment is complete.

## Event-driven completion

`scripts/parallelism.py wait --name <id> | --names a,b | --group <g> [--timeout S]`
blocks on worker process exit using deterministic process checks — **no LLM
polling**; a group waits for exactly its known members and never waits forever on
a failed/interrupted/cancelled/blocked worker. Workers finish by writing a compact
JSON result (`status`, `commit`, `files`, `tests`, `acceptance`, `blockers`);
ingest it with `result --name <id> --file <json>`, and read a whole group with
`collect --group <g>`. The Master may implement its own independent task while
helpers run.

Lifecycle: `ASSIGNED → WORKING → VALIDATING → COMPLETED`, plus `BLOCKED`,
`FAILED`, `CANCELLED`. No worker→reviewer→worker loop.

## Model inheritance

- **Subagents (native, preferred):** an agent file without a `model:` field
  inherits the Master's model natively (verified: e.g. `player-verifier.md` has no
  `model:` and inherits). Use native subagents for read-only work.
- **Independent CLI workers:** pass the Master's exact model explicitly and verify
  it. `resolve-model --model <id>` (→ `PARALLELISM_MASTER_MODEL` → resolved project
  config) fails rather than guess; `verify-model --session <id> --expect <id>`
  reads the worker's stored session model and fails on mismatch.
- Never hardcode a provider/model. Never assume the configured project default is
  the Master's selected model. Never silently fall back. Running helpers keep
  their original model.

## Master-owned integration and safety

The Master integrates directly after a dependency-ordered batch is ready:

1. collect commits; 2. acquire the exclusive integration lock; 3. verify commits,
   ownership, ancestry, dependencies and required tests; 4. merge in order;
   5. resolve conflicts; 6. run integration + broader regression tests; 7. review;
   8. record evidence; 9. release the lock; 10. report.

`scripts/parallelism.py premerge --candidate <sha> [--base <sha>] [--target <integration-sha>]
[--expect-head <sha>] [--worktree <path>] --tests "<evidence>"` refuses unless the
lock is held, tests evidence says `pass`, `--base` is an ancestor of the candidate,
the worktree is clean, the integration HEAD matches `--expect-head` (stale-HEAD
rejection), and `git merge-tree --write-tree` reports no conflict against
`--target`. It **never merges** — the Master re-checks HEAD, lock ownership and
candidate identity immediately before running the merge itself. A conflict-free
merge is not proof of semantic correctness. Never auto-merge a worker branch on
completion. Preserve mandatory independent review and security gates. Never
modify `main`, deploy, or publish without authorization. One writer per branch.

## Deterministic test selection, results and evidence

Move test work out of LLM reasoning while keeping required gates:

- `select-tests --base <a> --head <b>` reads an explicit map
  (`<repo>/.parallelism/test-map.json` or `--map`) of known modules → tests plus a
  `shared` list of central files. A `shared` change, or any change that matches no
  rule, selects the **broad/full** suite (fail-safe); never silently skips
  coverage. Full regression, security, release and platform gates are preserved.
- `run-tests --cmd "<command>" [--reuse] [--timeout S]` runs the command, writes
  the **full log to disk**, and returns a bounded structured result: command,
  exit code, passed/failed/skipped/timed-out counts, failed test ids, an error
  excerpt, log path, platform and runtime identity. A missing error excerpt is
  never treated as success. `--reuse` returns a stored PASS only when the cache
  key (command + HEAD + python/node + platform) matches; never reuse for
  freshly-built final-artifact validation.
- No LLM call is used to check liveness, test pass/fail, unchanged hashes, lock
  validity, waits, or machine-readable results — all deterministic.

## Token-efficiency rules

- Use deterministic CLI (`git`, tests, this script) for dependency checks, status,
  process monitoring, locks, tests and duplicate detection. Never use an LLM to
  poll a session.
- **No-progress detection** uses meaningful progress (commits, acceptance
  evidence, test results, blocker changes), not a bare unchanged tree;
  `progress --limit N` parks a stalled task (`BLOCKED`, no redispatch).
- Concise structured reports; don't repeat unchanged status or whole logs, but
  never drop required evidence or error detail.

## Script

`scripts/parallelism.py`: `decide`, `resolve-model`, `verify-model`, `spawn`,
`wait`, `collect`, `result`, `checkpoint`, `status`, `progress`, `lock`,
`premerge`, `select-tests`, `run-tests`. Python stdlib only. It never merges,
never deploys, and never starts a background service.
`scripts/parallelism_selftest.py` runs the deterministic regression suite (uses
`PARALLELISM_LAUNCHER` to mock workers; no real provider calls).

## Project specifics

Project paths, agents, model policy, test commands, security gates and release
rules live in the project's `AGENTS.md`, not here. This skill is model-agnostic.
