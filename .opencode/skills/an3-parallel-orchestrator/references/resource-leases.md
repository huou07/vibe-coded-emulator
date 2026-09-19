# Resource leases

Shared resources must be leased atomically **before** use and released when done.
Use `scripts/resource_lock.py`; do not rely on a note in the manifest.

## What must be leased

- Android emulator: `android-avd:codex-nds-api35`, `android-avd:an3qa-api35`
- Windows build VM: `windows-vm:an3-win11-build`
- Linux builder: `linux-builder:an3-dell`
- Staging: `staging:8092`
- Fixed server ports: `port-range:<a>-<b>`
- Shared artifact output: `artifact-dir:native-offline/releases`

Add new resources to `config.json` (`resources`) so names stay in one place.

## Lease contents

`resource`, `ownerSession`, `runId`, `pid`, `acquiredAt`, `leaseUntil`, `purpose`.

## Semantics

- Acquisition is atomic (`mkdir` of a lock directory); a held lease is never
  overwritten.
- Release requires the matching owner; releasing someone else's lease is refused.
- A lease past `leaseUntil` whose PID is no longer alive is reported `STALE`.
- `--break-stale` may remove only a **stale + dead-PID** lease, and renames the old
  directory aside first. An apparently active lease is never stolen automatically.
- `status` is read-only and safe to run at any time.

## Why it matters

This prevents: two agents installing different APKs on one AVD; simultaneous
Windows-VM manipulation; multiple staging deployments; two GUI tests using one fixed
port; and agents killing each other's test processes. Exit codes: `0` acquired,
`2` denied (held), `3` refused unsafe force, `4` usage.
