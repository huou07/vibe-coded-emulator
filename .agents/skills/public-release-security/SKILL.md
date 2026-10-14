---
name: public-release-security
description: Use before any push, release, or publication to a public GitHub repository for Vibe Coded Emulator. Runs the fail-closed publication gate over the publication candidate, checks secrets, personal data, private infrastructure and prohibited content, and blocks publication on unresolved findings. Triggers on "publish to GitHub", "public release", "push to public repo", "build public snapshot".
---

# Public release security gate

Fails closed. If a required scanner is unavailable or a check cannot finish,
publication is blocked. A scanner that silently matches nothing is treated as
a failure, never as a clean result — see "Fail-open history" below.

## Preconditions and authority

Resolve the exact publication candidate, source identity and requested operation.
Skip routine internal edits and non-public status requests. Review and snapshot
preparation do not by themselves authorize a push or release: check the active
session mandate and `AGENTS.md`, then stay within its scope, gates and effective
tool/OS permissions. Read snapshot/gate scripts before running them and inspect
the candidate's licence contract rather than changing licence text to obtain a
pass.

## Run

```bash
tools/build-public-snapshot.sh --output work/public-snapshot  # build it first
tools/publication-check.sh work/public-snapshot                # scan the candidate
tools/publication-check.sh --history work/public-snapshot     # also scan Git history
```

`tools/publish-github.sh` runs the gate itself at step 2/7, **before** it
`git init`s the snapshot. Do not add a step between those two that assumes the
candidate is a Git repository; it is not one.

Non-zero exit means **do not publish**.

## What the gate actually checks

- Required public files exist: `LICENSE`, `THIRD_PARTY_NOTICES.md`, `README.md`,
  `SECURITY.md`, `CONTRIBUTING.md`, `.env.example`, `.gitignore`.
- `LICENSE` contains the GPLv3 text and `README.md` states `GPL-3.0-or-later`.
- Forbidden paths are absent: `.opencode/`, `.codex/`, `.agents/`,
  `.parallelism/`, `AGENTS.md`, `opencode.json`, `reports/`, `work/`,
  `tools/ssh/`, `AN3-ARCADE-FULL-SYSTEM-HANDOFF-*.md`.
- Prohibited content is absent: ROMs (`*.gba`, `*.nds`, `*.3ds`, `*.nro`,
  `*.xci`), `*.db`/`*.sqlite*`, `prod.keys`/`title.keys`, `*.dmg`, `*.apk`,
  native binaries (`*.exe`, `*.dll`, `*.dylib`, `*.so`, `*.iso`, `*.img`,
  `*.bin`), archives (`*.tgz`, `*.tar.gz`, `*.zip`, `*.7z`) and private key
  material (`*.pem`, `*.p12`, `*.keystore`, `id_rsa*`).
- `gitleaks` is installed, runs to completion, and reports zero findings.
- Project-specific patterns do not match: `AN3_GOOGLE_CLIENT_SECRET`,
  `AN3_AUTH_PEPPER`, Google OAuth client IDs, `CF_API_TOKEN`,
  `BEGIN * PRIVATE KEY`, `/Users/<name>/…`, `192.168.x.x`, the production
  domain, and consumer email addresses.

The gate does **not** verify third-party licence headers or redistributable
rights. Those are reviewed by hand; see `docs/licensing/`.

## Adding a fixture

`tests/` is copied verbatim into the public snapshot, so anything written in a
test is scanned as part of the real release candidate. Build secret-shaped
fixture values from fragments so no literal appears in published source, and
re-run the gate against a real snapshot after touching the test suite. The
`AN3_AUTH_PEPPER` case in `tests/test_publication_gate.py` is written this way
for exactly that reason.

## Fail-open history

The project-specific scan used to run through `git grep`. Because
`build-public-snapshot.sh` never runs `git init` and the gate runs before the
publisher does, the scan always matched nothing and the gate reported
`personal-data and infra patterns: clean` — including on a candidate holding a
live auth pepper. It now uses a recursive grep that works on a plain directory.
`tests/test_publication_gate.py` pins this: run it against the old script and
it fails.

Do not reintroduce a scan whose correctness depends on the candidate's VCS
state, and do not pipe a scanner through `grep -q` such that a non-zero scanner
exit is indistinguishable from "no findings".

## Stop and report

Stop at the candidate verdict or a failed/unavailable gate. Report source and
candidate identity, scanner coverage/results, licence review, redacted findings
and owner-only next actions. A clean gate is not proof of safety or permission
to publish. Do not execute publication merely because review passed.

## Rules

- Never print or commit a secret value. Report only: secret category, affected
  file (path redacted), whether it is in Git history, and whether rotation is
  required.
- Deleting a credential does not make it safe. The owner must rotate or revoke
  it through the authorized credential-management path; review grants no such access.
- Publishing is blocked while an active exposed credential is unresolved.
- False-positive suppressions must be narrowly scoped and documented in
  `.gitleaks.toml` without exposing private data.
- GitHub Actions cannot protect content that was already pushed; the local
  check must pass before the first push.
- The public repository is the product source only. The development history is
  not publishable; export a clean snapshot with a truthful provenance note.
