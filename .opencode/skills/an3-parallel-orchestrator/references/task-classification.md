# Task classification

Classify every work item before scheduling. Classification is by **structure**
(ownership, dependencies, test loop), not by feature name — Switch, Controller
and Sync are only current examples and must not be baked into the rules.

## Decision procedure

1. Does it produce independent, reviewable implementation that will likely become
   one or more commits and owns a subsystem/domain with its own test loop?
   → **S — Session** (branch + worktree + top-level session).
2. Else does it only read, explore, analyze, or report (research, CodeGraph, logs,
   review, security, comparison, narrow testing)? → **A — Subagent** (read-only).
3. Else is it a small write that clearly belongs to a session that already exists
   and already owns those files? → **W — Owner write** (no new session).
4. Else does it touch a shared contract or a serial resource (shared API, schema,
   dependency manifest, lockfile, version/catalog metadata, release scripts,
   merge resolution, staging state, shared dispatcher)? → **I — Integration/serial**.

Tie-break: prefer **W** over **S** (do not spawn a session for a small write);
prefer **A** over **S** (do not spawn a writer for research). Prefer **I** whenever
two S nodes would have to edit the same contract.

## S — Session

Signals: meaningful independent implementation; persistent-context benefit; one or
more expected commits; owns a subsystem/domain; mostly independent test loop; can
safely proceed concurrently with the other ready nodes.

Each S node gets exactly one branch `agent/<run-id>/<domain>` and one worktree
`../an3-wt-<run-id>-<domain>`, and is started from the recorded base SHA unless a
DAG dependency requires a later commit.

## A — Subagent

Use for CodeGraph/architecture exploration, upstream research, review, test/log
analysis, security review, comparison and narrow focused testing. Prefer read-only
agents (`an3-code-explorer`, `an3-blind-reviewer`, `an3-test-analyzer`,
`an3-integration-reviewer`). A subagent must not create sessions, must not edit
product code (except a tightly scoped test-analyzer run), and must summarize large
output rather than flooding the parent context.

## W — Owner write

A small change inside a domain that already has an owning session/worktree. Send it
to that session; do not create another branch. Example: a one-line fix in a file the
existing worker already owns, a doc line, a follow-up test in the same module.

## I — Integration/serial

Serialize and route to the single integrator when work touches: shared API
contracts; dependency manifests and lockfiles; central schemas; version/catalog
metadata; release scripts; merge-conflict resolution; staging or production state;
shared dispatchers/registries. If two S nodes both need an evolving shared contract,
pause both writes, land the contract as **I**, then resume both S nodes against the
frozen interface.

## Classification record

Record for every item in `tasks.json`: `id`, `goal`, `owner`, `nonGoals`,
`class` (`S|A|W|I`), `dependsOn`, `expectedModules`, `sharedFiles`, `apisAffected`,
`resources`, `tests`, `integrationRisk`, `write` (bool), `reason`. The `reason`
field is mandatory — it is how the run manifest explains each choice.
