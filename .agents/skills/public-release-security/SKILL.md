---
name: public-release-security
description: Use before any push, release, or publication to a public GitHub repository for Vibe Coded Emulator. Scans the working tree, the publication candidate, and selected Git history for secrets and personal data, checks third-party redistribution rights and source/licence compliance, and blocks publication on unresolved findings.
---

# Public release security gate

Fails closed. If a required scanner is unavailable or a check cannot finish,
publication is blocked.

## Run

```bash
tools/publication-check.sh            # scans the publication candidate
tools/publication-check.sh --history  # additionally scans selected Git history
```

The script scans the candidate, then runs `gitleaks` when available. It exits
non-zero on any unresolved finding. A non-zero exit means **do not publish**.

## What it checks

- Secrets and tokens (gitleaks plus project-specific patterns:
  `AN3_GOOGLE_CLIENT_SECRET`, `AN3_GOOGLE_CLIENT_ID`, `AN3_AUTH_PEPPER`,
  `BEGIN * PRIVATE KEY`, OAuth refresh tokens, Cloudflare tokens).
- Personal data: home-directory paths, personal email addresses, machine
  hostnames, SSH destinations.
- Private infrastructure: LAN addresses, staging/production hostnames, internal
  service URLs.
- Prohibited content: ROMs, saves, firmware, `prod.keys`/`title.keys`, BIOS,
  databases, dumps, archives, native binaries.
- Licence compliance: `LICENSE`, `THIRD_PARTY_NOTICES.md`, and the core licence
  texts are present; no third-party header was relicensed.
- Publication hygiene: `.opencode/`, `.codex/`, `AGENTS.md`, `reports/`, `work/`,
  `tools/ssh/`, handoff/status docs and real environment files are excluded.

## Rules

- Never print or commit a secret value. Report only: secret category, affected
  file (path redacted), whether it is in Git history, and whether rotation is
  required.
- Deleting a credential does not make it safe: rotate or revoke it first.
- Publishing is blocked while an active exposed credential is unresolved.
- False-positive suppressions must be narrowly scoped and documented in
  `.gitleaks.toml` without exposing private data.
- GitHub Actions cannot protect content that was already pushed; the local
  check must pass before the first push.
- The public repository is the product source only. The development history is
  not publishable; export a clean snapshot with a truthful provenance note.
