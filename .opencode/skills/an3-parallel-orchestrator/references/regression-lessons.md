# Regression lessons → permanent checks

Every failure observed in a previous orchestration run becomes a deterministic
check enforced by `scripts/validate_candidate.py scan`, run on every candidate
(relative to its base so pre-existing debt is reported, not silently fixed).

## Observed failures and their checks

| Observed failure | Check |
| --- | --- |
| Two workers produced the same global `RG-###` ID | `duplicate-rg` — duplicate guard IDs introduced vs base |
| A `#[tauri::command]` was duplicated or registered for an unsupported target | `tauri-commands` — duplicate/foreign handler entries, `build.rs`/ACL mismatch |
| An API was renamed leaving stale callers | `stale-callers` — invocation sites vs exported symbols (report; review) |
| Generated assets/manifests drifted from shipped bytes | `manifest-hash` — catalog sha256/size vs present files |
| Package/catalog versions disagreed | `versions` — catalog version vs filename vs changed platform version fields |
| Version assumptions were hard-coded per platform | `versions` + `stale-release-filenames` |
| Test-only automation leaked into distribution binaries | `distribution-strings` — forbidden test-bridge/token signatures in shipped artifacts |
| Hard-coded release filenames survived a bump | `stale-release-filenames` — version literals in release scripts |
| Duplicated protocol implementations / port conflicts | resource leases + `ports` report (advisory) |
| Save-format or shared-state divergence | review + focused tests (cannot be fully scripted) |
| Lockfile divergence | `versions` report (advisory; integration owns lockfiles) |
| Model drift away from DeepSeek V4.1 Flash | `model-policy` — every `an3-*` agent pins the canonical model |
| Manifest/record corruption across worktrees | `validate-manifest` — schema + required fields |

## Regression guard ID policy

- Preferred: domain-scoped IDs `RG-<DOMAIN>-###` (`RG-SWITCH-...`,
  `RG-CONTROLLER-...`, `RG-SYNC-...`, `RG-ANDROID-...`, `RG-RELEASE-...`) when
  repository policy allows.
- If the repo keeps global numeric IDs, **only Integration** allocates the final
  next ID; workers must not guess. `duplicate-rg` catches collisions.
- Never renumber an existing guard just to make room; append.

## Test-only security boundary (release gate)

Before a release/promotion, `distribution-strings` must confirm shipped artifacts
contain no test-only bridge, no debug bearer token, no debug endpoint, and no
unrestricted JS-control signature. Docs-only and non-affected candidates skip this
with an explicit `UNVERIFIED`/`N/A` label rather than a silent pass.

## Adding a new lesson

When a new orchestration failure is found: add the guard to
`docs/REGRESSION_GUARDS.md` with its validation, add a deterministic check here if
possible, and test it with a planted fixture in `scripts/orchestrator_selftest.py`.
