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

State is durable and machine-readable. Recovery is inspect-first:

```bash
python3 $SK/inspect_run.py recover --run-id <id>
```

It reports the baseline, session lifecycle
(`PROCESS_RUNNING`/`SESSION_RESUMABLE`/`SESSION_UNKNOWN`/`SESSION_DEAD`), worktrees
and dirty state, candidate/QA/integration state, leases, staging state, target-branch
movement and the safe next actions. A launcher that exited is not a dead session: the
durable session can be resumed with `session.py send --session-id ...`, or a worker
can be restarted in the **same** worktree with a checkpoint. Destructive recovery is
never automatic.

## Candidate provenance

Every candidate records how worker bytes became integration bytes:

```bash
python3 $SK/orchestrator_state.py record-provenance --run-id <id> --domain <d> \
  --worker-commit <sha> --integrated-commit <sha> --method cherry-pick|merge|adapted \
  [--adapter-commit <sha>]
python3 $SK/orchestrator_state.py check-provenance --run-id <id>
```

A cherry-pick rewrites the SHA but keeps the patch identity, so
`contentEquivalent: true` and the changed-file list is empty. If integration must
change content, record it as a separate adapter commit with `--method adapted`; that
is stored as `contentEquivalent: false` with the explicit changed files. The two
different SHAs are never assumed equivalent without a patch-id/tree check.

## Warning hygiene

Deterministic checks report `PASS`, `WARN_KNOWN`, `WARN_NEW` or `FAIL`. `WARN_NEW` is
always distinguishable from accepted history, and each accepted warning needs an
explicit, justified entry in `config.json` (`knownAcceptedWarnings`). The scan summary
shows `newWarningCount` and `knownWarningCount`; only `FAIL` (or `WARN_NEW` with
`--strict-warnings`) blocks. Prefer removing a warning over adding it to the allowlist.

## Scheduling pressure and overlap

```bash
python3 $SK/scheduler.py overlap --tasks-file tasks.json   # PARALLEL_OK/CONTRACT_FIRST/SERIALIZE
python3 $SK/orchestrator_state.py pressure --run-id <id>   # LOW/MEDIUM/HIGH + allowNewWriters
```

`overlap` flags two writers that declare the same file or a central contract
(`config.json` `centralContracts`). `pressure` throttles new write sessions when the
READY_FOR_REVIEW / QA / integration backlog is high; read-only investigation stays
allowed.

## Deterministic checks and stress harness

```bash
python3 $SK/validate_candidate.py scan --run-id <id>       # all logical-conflict checks
python3 $SK/orchestrator_selftest.py                       # 36 self-tests
python3 $SK/stress_test.py                                 # disposable real-session stress run
```

Checks cover duplicate regression-guard IDs, duplicate/unsupported Tauri commands,
catalog hash/size drift, version inconsistency, hard-coded release filenames,
test-only automation strings in shipped artifacts, model policy, candidate provenance
and manifest schema. `stress_test.py` builds a throwaway repo under the OS temp area
and exercises 3 real worker sessions, read-only subagents, a dependency edge, a lease,
a deliberate integration conflict and provenance; it never touches product code or
staging.

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
- The `skill` tool's available list is captured when a session starts, so a skill
  created after a session opened is not listed until that session restarts
  (`opencode debug skill` in a fresh process sees it immediately). Edited content of
  an already-listed skill is read from disk (verified: a fresh process returned the
  current v1.1 body, frontmatter stripped from `content`).
- Installed OpenCode 1.18.31 enforces a **primary** agent's permissions under
  `opencode run --agent` but not a **subagent-mode** agent's. Read-only subagents
  (`an3-code-explorer`, `an3-blind-reviewer`, `an3-test-analyzer`,
  `an3-integration-reviewer`) are therefore invoked only through the Task tool
  inside a primary session, where their denies ARE enforced; `session.py` refuses
  to launch them as top-level sessions.
- Orchestration run state lives in the shared Git common dir, outside the
  worktree; the `an3-*` agents grant `external_directory` for the narrow pattern
  `*/.git/opencode-orchestrator/*` so non-interactive sessions can read it.
- Hardware-bound checks (physical phones, real two-device transfer) remain
  `UNVERIFIED` unless the hardware is actually exercised.
