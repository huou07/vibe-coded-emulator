# DAG scheduling and parallelism scoring

## Build the DAG first

Before spawning any writer, write every task with its dependencies. Then only
start nodes whose dependencies are complete.

- If `A → B`, B must not begin before A is integrated (or the exact interface B
  needs is frozen).
- If A and B are independent, they may run concurrently.
- If A and B both need a shared contract, pause both write paths, establish the
  contract as an `I` task, then resume both against the same interface.

## Parallelism score (heuristic, consistent not perfect)

Score each candidate S node; schedule the highest scores while the DAG frontier and
limits allow. Record the score in the run manifest.

Positive:
- domain independence (separate directories, no shared files) — high
- independent test loop — high
- persistent-context benefit over a short task — medium
- long build/research latency that can overlap other work — medium

Negative:
- shared-file overlap with another ready node — strong negative
- unstable/evolving shared API consumed by the node — strong negative
- dependency coupling on another writer's uncommitted output — strong negative
- same exclusive device/resource requirement — disqualifies concurrency
- touches manifests/lockfiles/version metadata — serialize as `I`
- duplicated investigation already assigned elsewhere — negative
- high integration complexity / wide blast radius — negative

## Concurrency limits (limits, not targets)

- 1 orchestrator
- ≤ 5 active top-level sessions (including the integrator)
- ≤ 3 concurrent subagents per primary session
- ≤ 1 platform-specific tester per isolated platform/resource

Reduce concurrency when: the integration backlog grows, shared APIs are unstable,
tests fail systemically, scarce resources saturate, or worker branches increasingly
overlap. A two-domain task spawns two writers, not five.

## Pre-flight checks before dispatch

1. Base SHA committed and recorded; no uncommitted user work touched.
2. Every S node has a unique branch/worktree path and a disjoint or declared file set.
3. Every shared resource has an acquired lease (`resource_lock.py`).
4. `orchestrator_state.py check-model` returns `OK`.
5. Concurrency within limits; every session assigned a distinct model confirmation.

## Manifest explanation

For each major task the manifest records whether it was parallelized, serialized,
given to a subagent, or kept in an existing session, plus the score factors that
drove that decision. The orchestrator must be able to justify the schedule without
re-deriving it from prose.
