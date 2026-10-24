# Provenance

This repository is a **clean source snapshot** exported from the Vibe Coded
Emulator development history on 2026-10-23. The public line's later fixes were
merged into it on 2026-10-24: the browser library no longer offers a Switch
title it cannot run, the required core licence notices are present, and the
core-only test contract names every Python test module explicitly instead of
relying on blanket discovery.

- Only the product source is published here. The private development history
  (which contains local machine paths, private infrastructure configuration and
  personal development notes) is intentionally **not** published, and its commit
  history is not part of this repository.
- The snapshot was produced by `tools/build-public-snapshot.sh` at the source
  revision recorded below; it is a faithful export of that revision with
  personal data and private infrastructure values replaced by documented
  examples.
- No third-party source has been removed or re-licensed. Emulator cores and
  other third-party components retain their own licenses; see
  `THIRD_PARTY_NOTICES.md` and `docs/licensing/`.

Exported source revision: a46f664
