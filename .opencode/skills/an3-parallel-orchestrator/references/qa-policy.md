# QA policy

QA is independent verification. A worker's test claims are **evidence**, not final
verification.

## Independence

- Verify incoming commits from a **clean candidate worktree** when risk warrants it:
  `base → clean worktree → apply candidate → build/test → PASS/FAIL`.
- This catches reliance on untracked files, generated artifacts, stale binaries,
  worker-local configuration, and undeclared dependencies.
- Do not require expensive clean rebuilds for documentation-only or comment-only
  changes; use the change-impact matrix (`release-gates.md`).
- QA does not implement product fixes; it reproduces, documents, and routes.

## What QA records

For each item: exact command, platform/runtime, base + candidate SHA, expected vs
observed, and a label `GOOD`/`FAIL`/`UNVERIFIED`. A green static check or suite run
is not interactive acceptance. If a browser or packaged runtime was not exercised,
record `UNVERIFIED`, never `GOOD`.

## Platform testers

At most one platform-specific tester per isolated platform/resource, and each must
hold that resource's lease. Android runs use the QA AVD; never root a device or
record device serials/private data.

## Routing a failure

A QA failure goes back to the **owning worker session** with reproduction + logs.
The worker fixes on its branch (`NEEDS_FIX` → `READY_FOR_REVIEW`), then QA again,
then integration. Integration fixes only tiny adapters. Never broad-revert a shared
subsystem to fix one bug; user-reported packaged-runtime regressions override earlier
PASS claims.
