#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Fail-closed pre-publication security check for the public source snapshot.
# Policy: .opencode/skills/public-release-security/SKILL.md
#
# Usage:
#   tools/publication-check.sh [--history] [CANDIDATE_DIR]
# Env:
#   AN3_PUBLICATION_CANDIDATE  candidate directory (default: see below)
#
# Exits non-zero on any unresolved finding. Never prints secret values.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANDIDATE="${AN3_PUBLICATION_CANDIDATE:-/tmp/an3-public/vibe-coded-emulator}"
SCAN_HISTORY=0
for argument in "$@"; do
  case "$argument" in
    --history) SCAN_HISTORY=1 ;;
    *) CANDIDATE="$argument" ;;
  esac
done

fail() { printf 'PUBLICATION_CHECK=FAIL %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }

[[ -d "$CANDIDATE" ]] || fail "candidate directory is missing: $CANDIDATE"
note "candidate=$CANDIDATE"

# --- 1. Required public files -------------------------------------------------
for required in LICENSE THIRD_PARTY_NOTICES.md README.md SECURITY.md CONTRIBUTING.md .env.example .gitignore; do
  [[ -f "$CANDIDATE/$required" ]] || fail "missing required public file: $required"
done
grep -q "GNU GENERAL PUBLIC LICENSE" "$CANDIDATE/LICENSE" || fail "LICENSE text looks incomplete"
grep -q "Version 3, 29 June 2007" "$CANDIDATE/LICENSE" || fail "LICENSE is not the GPLv3 text"
grep -q "GPL-3.0-or-later" "$CANDIDATE/README.md" || fail "README does not state GPL-3.0-or-later"

# --- 2. Forbidden AI/workflow/private material --------------------------------
for forbidden in .opencode .codex AGENTS.md reports work tools/ssh; do
  if [[ -e "$CANDIDATE/$forbidden" ]]; then
    fail "forbidden path present in the candidate: $forbidden"
  fi
done

# --- 3. Prohibited binary/content types ---------------------------------------
if find "$CANDIDATE" -type f \( -iname '*.gba' -o -iname '*.nds' -o -iname '*.3ds' \
  -o -iname '*.nro' -o -iname '*.xci' -o -iname '*.db' -o -iname '*.sqlite*' \
  -o -iname 'prod.keys' -o -iname 'title.keys' -o -iname '*.dmg' -o -iname '*.apk' \
  -o -iname '*.exe' -o -iname '*.dll' -o -iname '*.dylib' -o -iname '*.so' \) \
  -print -quit | grep -q .; then
  fail "prohibited binary or game/keys content found in the candidate"
fi

# --- 4. Secret scanning (fail closed when unavailable) ------------------------
command -v gitleaks >/dev/null 2>&1 || fail "gitleaks is required but not installed"
REPORT="$(mktemp -t an3-gitleaks.XXXXXX.json)"
if ! gitleaks dir "$CANDIDATE" --config "$CANDIDATE/.gitleaks.toml" \
      --report-format json --report-path "$REPORT" --exit-code 0 >/dev/null 2>&1; then
  fail "gitleaks could not complete; publication blocked"
fi
FINDINGS="$(python3 - "$REPORT" <<'PY'
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    print("unparsable")
    raise SystemExit(0)
if not isinstance(data, list):
    print("unparsable")
else:
    print(len(data))
PY
)"
rm -f "$REPORT"
case "$FINDINGS" in
  unparsable) fail "gitleaks report could not be parsed" ;;
  0) note "gitleaks: 0 findings" ;;
  *) fail "gitleaks reported $FINDINGS finding(s); inspect the report and rotate if real" ;;
esac

# --- 5. Project-specific patterns (no values printed) -------------------------
if git -C "$CANDIDATE" grep -lIE \
    'AN3_GOOGLE_CLIENT_SECRET=[A-Za-z0-9_-]{8,}|AN3_AUTH_PEPPER=[A-Za-z0-9]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|/Users/[A-Za-z][A-Za-z0-9._-]*/|192\.168\.[0-9]+\.[0-9]+|an3tocom\.space|[A-Za-z0-9._%+-]+@(gmail|outlook|yahoo|hotmail)\.' \
    -- . 2>/dev/null | grep -q .; then
  fail "project-specific personal-data/secret patterns matched"
fi
note "personal-data and infra patterns: clean"

# --- 6. Optional Git history scan --------------------------------------------
if [[ "$SCAN_HISTORY" -eq 1 ]]; then
  if [[ -d "$CANDIDATE/.git" ]]; then
    gitleaks git "$CANDIDATE" --config "$CANDIDATE/.gitleaks.toml" --exit-code 0 >/dev/null 2>&1 \
      || fail "gitleaks history scan could not complete"
    note "history scan completed"
  else
    note "history scan skipped: candidate is not a Git repository"
  fi
fi

note "PUBLICATION_CHECK=PASS"
