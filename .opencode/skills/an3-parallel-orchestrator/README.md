# AN3 parallel orchestrator — user guide

`an3-parallel-orchestrator` turns a large multi-domain AN3/Vibe Coded Emulator
request into isolated parallel writer sessions, read-only verification subagents,
and one serial integrator. You describe goals; the skill handles the mechanics.

## What it does

- Classifies each work item as **S**ession, **A**subagent, **W** owner-write or
  **I**ntegration/serial, and builds a dependency DAG.
- Gives every substantial writer its own branch, worktree and top-level session.
- Keeps research/review/QA in read-only subagents (never many writers in one tree).
- Pins every session and subagent to `opencode-go/deepseek-v4.1-flash`.
- Runs deterministic worktree/resource/conflict scripts instead of hand-rolled shell.
- Serializes integration, gates staging, and reports per-dimension status.

## When it activates

Use it for **2+ independent domains, 3+ parallelizable tasks, or 2+ platforms in
one wave** that will outlive one short context. It is **not** used for a single
file, a typo, one focused fix, or a question. When unsure, start with a short plan.

## How to invoke it

Just ask for it, for example:

```text
Use an3-parallel-orchestrator.

Goals:
- <feature A across its own module>
- <feature B in another subsystem>
- <cross-platform/test work>

Integrate verified changes and deploy staging when appropriate.
```

You can also `@`-mention the agents directly: `@an3-orchestrator`.

## Session vs subagent

| Class | Use for | Gets |
| --- | --- | --- |
| S — session | independent implementation, own commits/test loop | branch + worktree + `an3-worker` session |
| A — subagent | research, CodeGraph, review, log/test analysis, security | read-only agent, no worktree |
| W — owner write | small change inside an existing session's domain | sent to that session |
| I — serial | shared API/schema/manifest/lockfile/version/release/staging | single `an3-integrator` writer |

## Runtime state

State lives in the shared Git common directory so every worktree sees it:

```text
$(git rev-parse --git-common-dir)/opencode-orchestrator/<run-id>/
├── manifest.json      tasks.json      sessions.json
├── candidates.json    status.json     sessions/*.ndjson
├── resources/         evidence/       status/
```

Inspect it any time (read-only):

```bash
SK=.opencode/skills/an3-parallel-orchestrator/scripts
python3 $SK/inspect_run.py list
python3 $SK/inspect_run.py --run-id <run-id>
```

## Model policy

Only `opencode-go/deepseek-v4.1-flash`, pinned in `opencode.json` and every
`an3-*` agent. If the model is unavailable the run stops with a structured
`MODEL_UNAVAILABLE` status — it never silently falls back. Verify with:

```bash
python3 $SK/orchestrator_state.py check-model --run-id <run-id>
```

## Resource locking

Shared devices/hosts/ports/staging are leased before use:

```bash
python3 $SK/resource_lock.py acquire "staging:8092" <owner> "deploy" --run-id <id>
python3 $SK/resource_lock.py status
python3 $SK/resource_lock.py release "staging:8092" <owner>
```

A held lease cannot be stolen. `--break-stale` only removes a lease that is both
expired and owned by a dead PID.

## Staging and production

Only the integrator deploys staging, after the release gates, and re-verifies the
deployed bytes/health. **Production is never deployed** unless you explicitly
authorize it in the request.

## Cleanup

```bash
python3 $SK/cleanup_run.py --run-id <id>                 # dry run (default)
python3 $SK/cleanup_run.py --run-id <id> --apply         # release leases + remove worktrees
```

Evidence under the Git common dir is kept. A dirty or unmerged worktree is refused
without `--allow-unmerged`.

## Resuming after an interruption

State is durable and machine-readable. Inspect the run, keep the worktree, then
either resume the same session (`session.py send --session-id ...`) or restart a
worker in the same worktree with a concise checkpoint. Completed commits are never
discarded automatically.

## Deterministic checks

```bash
python3 $SK/validate_candidate.py scan --run-id <id>       # all logical-conflict checks
python3 $SK/orchestrator_selftest.py                       # 14 self-tests
```

Checks cover duplicate regression-guard IDs, duplicate/unsupported Tauri commands,
catalog hash/size drift, version inconsistency, hard-coded release filenames,
test-only automation strings in shipped artifacts, model policy and manifest schema.

## Examples

Small (do **not** orchestrate — just do it):

```text
Fix the typo in docs/design-system.md
```

Large (orchestrate):

```text
Use an3-parallel-orchestrator. Goals:
- finish Switch Android input handling
- improve phone controller reconnect
- finish LAN sync edge cases
- run cross-platform tests
Integrate verified changes and deploy staging when appropriate.
```

## Known limitations (installed OpenCode 1.18.31)

- Sessions are launched with `opencode run --format json` and resumed with
  `--session`; there is no separate "create session without running" API, so the
  first prompt is always sent at start.
- Top-level sessions are real OpenCode sessions recorded by id and PID; a session
  is not "message delivered" until its id appears in the JSON event stream.
- Subagent step budgets (`steps`) are enforced by OpenCode; primary worker
  sessions stay long-lived.
- Hardware-bound checks (physical phones, real two-device transfer) remain
  `UNVERIFIED` unless the hardware is actually exercised.
