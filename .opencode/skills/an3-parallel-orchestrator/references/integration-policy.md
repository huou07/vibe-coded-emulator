# Integration policy

Integration is **serial**. Many agents may *review* incoming changes; exactly one
integration writer may cherry-pick, merge, resolve conflicts, or modify the
integration worktree. Never run multiple merge writers against one Git index.

## Ownership

- Branch `integration/<run-id>`, worktree `../an3-wt-<run-id>-integration`.
- The `an3-integrator` session (agent `an3-integrator`) is the only writer.
- The integrator is the only role allowed to deploy staging.

## Per-candidate sequence

```
incoming commit
→ independent review (an3-blind-reviewer, fresh context)
→ dependency check (does it depend on an un-merged commit?)
→ semantic overlap check (does another candidate touch the same interface?)
→ deterministic checks: validate_candidate.py scan
→ integrate (cherry-pick / merge) with a clear English message
→ focused tests for the affected subsystem (change-impact matrix)
→ record result, continue
```

## Integration adapters

Sometimes two valid worker features need a small glue change. Never modify a worker's
historical commit or pretend the integrator applied it unchanged. Record:

```text
worker A commits + worker B commits
→ explicit integration adapter commit (registration glue, shared enum addition,
  route connection, version/catalog reconciliation, conflict-resolution glue)
```

The adapter must NOT become a place for major feature implementation. Record it with
`record-provenance --method adapted --adapter-commit <sha>`; the provenance then shows
`contentEquivalent: false` and the exact changed files.

## Candidate provenance (mandatory)

Every candidate records an auditable chain: `workerCommit`, `reviewedCommit`,
`integrationInputCommit`, `integratedCommit`, `integrationMethod`, `workerPatchId`,
`integratedPatchId`, `contentEquivalent`, `adapterCommit`, `changedFiles`. An exact
cherry-pick/merge is `contentEquivalent: true`; a deliberate integration change is a
separate adapter commit with `contentEquivalent: false`. Never treat different SHAs as
equivalent without a `git patch-id`/tree comparison. `check-provenance` re-verifies
the recorded equivalence and flags an undeclared adaptation.

## Logical conflict checks (Git markers are not enough)

Run `scripts/validate_candidate.py scan`, which deterministically checks the
observed failure classes in `references/regression-lessons.md` (duplicate
regression-guard IDs, duplicate/unsupported Tauri commands, stale hard-coded
release filenames, version/catalog mismatch, catalog hash drift, release
automation-string leaks, model policy, manifest schema). Do not rely on LLM review
for anything a script can verify.

## Regression guard IDs

If the repo keeps global numeric `RG-###` IDs, only Integration allocates/resolves
final IDs; workers must not guess the next global ID. Prefer domain-scoped IDs
(`RG-<DOMAIN>-...`) where repository policy allows. Duplicate detection runs on
every candidate relative to its base, so a worker-introduced collision is caught.

## Target branch movement

Before promotion/handoff, compare target HEAD to the recorded start point. If the
target moved, do not fast-forward an old candidate: reconcile the new target with
the candidate and rerun affected tests. Never merge into `main`/`apps-web` unless
current project policy explicitly allows it.
