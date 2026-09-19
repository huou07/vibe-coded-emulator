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
