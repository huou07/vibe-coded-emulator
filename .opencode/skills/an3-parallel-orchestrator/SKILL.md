---
name: an3-parallel-orchestrator
description: Use when a large AN3/Vibe Coded Emulator request spans several independent domains, platforms, or long-running features and benefits from multiple persistent development contexts run in parallel — multi-feature initiatives, cross-platform implementation waves, large bug-fixing campaigns, release/integration runs. Gives each substantial writer its own session, branch and worktree, keeps research/review/QA in read-only subagents, pins the model, and drives deterministic worktree, resource-lease and conflict scripts plus single-writer integration and staging gates. Do NOT use for a single-file edit, a typo, one focused fix, or a question — do those directly.
license: MIT
compatibility: opencode
metadata:
  version: "1.1.0"
  manifest-schema: "1"
---

# AN3 parallel orchestrator

User-facing guide and invocation examples: `README.md` in this skill directory.

Turns a large multi-domain request into isolated parallel writer sessions, read-only
verification subagents, and one serial integrator. The orchestrator owns the plan,
the worktrees, the leases, the integration, and the run state; workers own one domain each.

## Model policy (non-negotiable)

Use **only** `opencode-go/deepseek-v4.1-flash` for the orchestrator, every top-level
worker session, every subagent, QA, integration and review. Do not fall back.
The canonical value lives in `config.json` (`"model"`). Before dispatching work run
`orchestrator_state.py check-model`; if the model is unavailable, stop spawning and
return a structured `MODEL_UNAVAILABLE` status. See `references/worker-contract.md`.

## When to orchestrate (do not over-orchestrate)

Orchestrate only when the request has **2+ independent domains OR 3+ parallelizable
tasks OR 2+ platforms in one wave** and will outlive a single short context. For
"fix this typo", one file, one bug, one question: skip this skill and just do it.
When unsure, write a short plan first; do not spawn sessions speculatively.

## Lifecycle

1. **Recon** — CodeGraph first (`an3-codegraph-first`), read `AGENTS.md`,
   `docs/REGRESSION_GUARDS.md`, the current handoff. Establish the committed base SHA.
2. **Decompose** — classify every work item S / A / W / I (below), build the DAG,
   score parallelism, choose concurrency within limits.
3. **Prepare** — `orchestrator_state.py init`, then `worktree.py create*` per S node,
   `resource_lock.py acquire` per shared resource.
4. **Dispatch** — spawn each S node as a top-level session with
   `scripts/session.py start` on the `an3-worker` agent in its own worktree, pinned
   to the model; render prompts from `templates/worker-prompt.md`. A nodes become
   subagents inside the owning session. Follow-ups go to the **same** session with
   `session.py send`.
5. **Collect** — parse each worker's `WORKER_STATUS` JSON; validate against
   `templates/worker-status.json`.
6. **Review + QA** — fresh-context `an3-blind-reviewer` on the diff, then
   `an3-test-analyzer`/QA from a clean candidate worktree when risk warrants.
7. **Integrate** — only the `an3-integrator` session merges, serially, into
   `integration/<run-id>`; run `validate_candidate.py scan` before each integration
   and record candidate provenance (`orchestrator_state.py record-provenance`).
8. **Stage** — only the integrator deploys staging, after gates; verify bytes and health.
9. **Report** — per-dimension status; never collapse the run to a single "complete".

## Task classification (summary — full rules in `references/task-classification.md`)

- **S (session)** — independent implementation, persistent context, own commits and
  test loop. Gets branch + worktree + session.
- **A (subagent)** — research, CodeGraph exploration, review, log/test analysis,
  security review, comparison. Read-only agents, no worktree. Review/QA/testing/
  analysis are **always A, never W**; W is only a small code/doc write inside an
  existing session's own domain.
- **W (owner write)** — small write clearly belonging to an existing session. Do not
  create a session.
- **I (integration/serial)** — shared contracts, manifests, lockfiles, version/catalog
  metadata, merge conflict resolution, release scripts, staging state, shared
  dispatchers. Serialize; Integration alone writes.

## Scheduling (summary — full rules in `references/scheduling.md`)

Build the DAG before spawning writers. Parallelize only ready nodes; do not call a
dependent node early. When two writers need one shared contract, pause both, fix the
contract first, resume both against it. Check declared-file overlap with
`scheduler.py overlap` (central contracts in `config.json`) before dispatch. Optimize
`throughput - coordination - risk`, not raw parallelism. Limits: **1 orchestrator,
≤5 top-level sessions, ≤3 subagents per session, 1 platform tester per isolated
resource.** Watch `orchestrator_state.py pressure`: when the integration backlog is
high, stop spawning lower-priority write sessions, allow read-only investigation, and
drain QA/integration. Only the orchestrator creates top-level sessions; workers and
subagents never do.

## State, worktrees, resources (deterministic — do not hand-roll)

State lives under the shared Git common dir, readable from every worktree:
`$(git rev-parse --git-common-dir)/opencode-orchestrator/<run-id>/`.

| Need | Command |
| --- | --- |
| Print canonical model | `scripts/orchestrator_state.py model` |
| Create a run + manifest | `scripts/orchestrator_state.py init --goal ... --base-sha <sha>` |
| Record task / session / candidate / status | `orchestrator_state.py add-task\|add-session\|set-candidate\|set-status` |
| Record integration / staging head | `orchestrator_state.py set-head --field integrationHead\|stagingHead` |
| Record candidate provenance (worker→integration) | `orchestrator_state.py record-provenance --domain ... --worker-commit ... --integrated-commit ... --method cherry-pick\|merge\|adapted` |
| Verify all provenance records | `orchestrator_state.py check-provenance --run-id <id>` |
| Integration backlog pressure / run metrics | `orchestrator_state.py pressure\|metrics --run-id <id>` |
| Target-branch movement check | `orchestrator_state.py check-target --run-id <id>` |
| Verify model on all recorded sessions | `orchestrator_state.py check-model --run-id <id>` |
| Shared-file overlap + DAG frontier | `scripts/scheduler.py overlap --tasks-file ...` |
| Create agent/integration worktree + branch | `scripts/worktree.py create --run-id ... --domain ... --base-sha ...` |
| Launch a worker/QA/integration session | `scripts/session.py start --run-id ... --domain ... --worktree ... --prompt-file ...` |
| Send a follow-up to the same session | `scripts/session.py send --session-id ... --prompt-file ...` |
| Session lifecycle (`PROCESS_RUNNING`/`SESSION_RESUMABLE`/…) | `scripts/session.py status --run-id <id>` |
| List / validate / remove worktrees | `worktree.py list\|validate\|remove --run-id ...` |
| Acquire / release / inspect a resource | `scripts/resource_lock.py acquire\|release\|status` |
| Inspect / recover a run (read-only) | `scripts/inspect_run.py --run-id <id>` / `inspect_run.py recover --run-id <id>` |
| Deterministic conflict checks | `scripts/validate_candidate.py scan --run-id <id>` |
| Safe cleanup | `scripts/cleanup_run.py --run-id <id> --apply` |
| Deterministic self-test / stress harness | `scripts/orchestrator_selftest.py`, `scripts/stress_test.py` |

All scripts emit JSON, fail closed, never discard work, and never steal an active lease.
Deterministic checks use `PASS`/`WARN_KNOWN`/`WARN_NEW`/`FAIL`; a newly introduced
warning is never hidden among accepted history, and known warnings need an explicit
justified allowlist entry in `config.json`. Candidate provenance always explains how
worker bytes became integration bytes: an exact cherry-pick is `contentEquivalent: true`,
and a deliberate integration change is recorded as a separate adapter commit with
`contentEquivalent: false` and the changed files.

## Worker / QA / integration contracts

- Worker prompt + rules: `templates/worker-prompt.md`, `references/worker-contract.md`.
- Worker status JSON: `templates/worker-status.json` (`WORKER_STATUS_BEGIN/END`).
- QA policy: `references/qa-policy.md`, `templates/qa-prompt.md`.
- Integration policy: `references/integration-policy.md`, `templates/integrator-prompt.md`.
- Release/staging gates: `references/release-gates.md`.
- Platform facts (single source): `references/an3-platforms.md`.
- Past failures → permanent checks: `references/regression-lessons.md`.

## Hard invariants

1. One top-level session owns one branch and one worktree; writers never share a worktree.
2. Workers never merge, rebase, force-push, or touch another worktree; they never deploy.
3. Integration is the single writer to `integration/<run-id>` and to staging. Production
   is forbidden unless the user explicitly authorizes it in the current request.
4. QA is independent: worker test claims are evidence, not final verification.
5. Reviewer starts from fresh context with the spec/diff; it does not receive the
   worker's chain-of-thought or self-justification.
6. No secret, token, key, or environment value may be printed, committed, or logged.
7. A mandatory test marked `UNVERIFIED` prevents a false `COMPLETE`.
8. Do not modify `main`/`apps-web` without explicit project policy; reconcile target
   branch movement before any promotion.
9. If the model is unavailable, stop and report `MODEL_UNAVAILABLE`; never substitute.
10. Every candidate has an auditable provenance chain; never treat two different SHAs
    as equivalent without a patch-id/tree check, and record an integration adaptation
    as its own adapter commit rather than hiding it in a cherry-pick.
11. Recovery is inspect-first: `inspect_run.py recover` recommends actions and never
    performs destructive recovery automatically; a dead launcher is not a dead session.

## Failure routing, recovery, interruption

- Defect found by QA/review → route to the **owning worker session** with reproduction
  and logs; it fixes on its own branch; then QA → integration again. Integration may
  fix only tiny glue through an explicit adapter commit, never a feature rewrite.
- Worker crash → keep the worktree, run `inspect_run.py recover`, resume the same
  session (`SESSION_RESUMABLE`) or restart in the **same** worktree with a checkpoint.
- User changes priorities mid-run → keep validated commits, update the DAG, cancel
  obsolete unstarted work, redirect workers; record the scope change in the manifest.
- Target branch moved during the run → `check-target` fails; reconcile candidate + new
  target and rerun affected tests; never blindly fast-forward an old candidate.

## Final report

Report each dimension separately (`IMPLEMENTATION`, `QA`, `INTEGRATION`,
`CROSS_PLATFORM`, `STAGING`, `PROMOTION`) and an overall status (`COMPLETE`,
`PARTIAL_VERIFIED`, `BLOCKED`, `FAILED`, `CANCELLED`), with the exact commands and
`file_path:line` evidence, and explicit `UNVERIFIED` labels. Keep the user-facing
report short; detail belongs in `reports/`.
