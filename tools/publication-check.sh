#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Fail-closed pre-publication security check for the public source snapshot.
# Policy: .agents/skills/public-release-security/SKILL.md
#
# Usage:
#   tools/publication-check.sh [--history] [CANDIDATE_DIR]
# Env:
#   AN3_PUBLICATION_CANDIDATE  candidate directory (default: see below)
#
# Exits non-zero on any unresolved finding. Never prints secret values.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CANDIDATE="${AN3_PUBLICATION_CANDIDATE:-$ROOT/work/public-snapshot}"
SCAN_HISTORY=0

usage() {
  cat <<'USAGE'
Usage: tools/publication-check.sh [--history] [--candidate DIR]

  --history         also scan the candidate's Git history
  --candidate DIR   candidate directory (default: work/public-snapshot)
  -h, --help        show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --history) SCAN_HISTORY=1; shift ;;
    --candidate) [[ -n "${2:-}" ]] || { printf 'ERROR: --candidate needs a directory\n' >&2; exit 2; }; CANDIDATE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) printf 'ERROR: unknown option: %s\n' "$1" >&2; exit 2 ;;
    *)
      # A bare path is accepted only when it really is a directory.
      [[ -d "$1" ]] || { printf 'ERROR: not a directory: %s\n(use --candidate DIR; run tools/build-public-snapshot.sh first)\n' "$1" >&2; exit 2; }
      CANDIDATE="$1"; shift ;;
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
# Agent frameworks, handoff/status notes and operator scratch must never reach
# the public candidate. build-public-snapshot.sh does not copy them; this list
# is the second line of defence for --prebuilt snapshots.
for forbidden in .opencode .codex .agents .parallelism AGENTS.md opencode.json \
                 reports work tools/ssh AN3-ARCADE-FULL-SYSTEM-HANDOFF-*.md \
                 .codegraph docs/prompts docs/AGENT-AUTHORITY.md \
                 AGENT_INTERACTION_CAPABILITY_AUDIT.md; do
  if compgen -G "$CANDIDATE/$forbidden" >/dev/null; then
    fail "forbidden path present in the candidate: $forbidden"
  fi
done

# --- 2b. Published workflows may only call scripts the candidate contains -----
# A published job that runs a script the snapshot never copies is a workflow that
# can only fail (the removed native-build.yml did exactly that with
# tools/release-train.sh). Fail closed rather than advertise it.
python3 "$ROOT/tools/publication/check-workflow-scripts.py" "$CANDIDATE" \
  || fail "published workflow references a script the candidate does not contain"

# --- 3. Prohibited binary/content types ---------------------------------------
# A find error must not read as "nothing prohibited was found".
prohibited_error=""
prohibited_hit="$(find "$CANDIDATE" -type f \( -iname '*.gba' -o -iname '*.nds' -o -iname '*.3ds' \
  -o -iname '*.nro' -o -iname '*.xci' -o -iname '*.db' -o -iname '*.sqlite*' \
  -o -iname 'prod.keys' -o -iname 'title.keys' -o -iname '*.dmg' -o -iname '*.apk' \
  -o -iname '*.exe' -o -iname '*.dll' -o -iname '*.dylib' -o -iname '*.so' \
  -o -iname '*.iso' -o -iname '*.img' -o -iname '*.bin' \
  -o -iname '*.tgz' -o -iname '*.tar.gz' -o -iname '*.zip' -o -iname '*.7z' \
  -o -iname '*.pem' -o -iname '*.p12' -o -iname '*.keystore' -o -iname 'id_rsa*' \) \
  -print -quit 2>/tmp/an3-find.err)" || prohibited_error="$(head -5 /tmp/an3-find.err)"
rm -f /tmp/an3-find.err
[[ -z "$prohibited_error" ]] || fail "prohibited-content scan could not complete; publication blocked"
[[ -z "$prohibited_hit" ]] || fail "prohibited binary or game/keys content found: $prohibited_hit"

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
# This scan must not depend on the candidate being a Git repository.
# tools/build-public-snapshot.sh does not run `git init`, and
# tools/publish-github.sh runs this gate *before* it initialises the snapshot,
# so a `git grep` here silently matched nothing on the primary publication path
# and reported "clean". Plain grep is used instead, and a scanner error is
# treated as a failure rather than as a clean result.
PROJECT_PATTERNS='AN3_GOOGLE_CLIENT_SECRET=[A-Za-z0-9_-]{8,}|AN3_AUTH_PEPPER=[A-Za-z0-9]{8,}|AN3_GOOGLE_CLIENT_ID=[0-9]+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com|CF_API_TOKEN=[A-Za-z0-9_-]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|/Users/[A-Za-z][A-Za-z0-9._-]*/|/home/[A-Za-z0-9._-]+/|(^|[^A-Za-z0-9_])~/|192\.168\.[0-9]+\.[0-9]+|an3tocom\.space|[A-Za-z0-9._%+-]+@(gmail|outlook|yahoo|hotmail)\.'

# grep exit codes: 0 = at least one match, 1 = no match, >=2 = error.
scan_error=""
scan_matches="$(grep -rIlE "$PROJECT_PATTERNS" -- "$CANDIDATE" 2>/tmp/an3-pubscan.err)" \
  || scan_error="$(head -5 /tmp/an3-pubscan.err)"
rm -f /tmp/an3-pubscan.err

if [[ -n "$scan_error" ]]; then
  fail "project-specific pattern scan could not complete; publication blocked"
fi
if [[ -n "$scan_matches" ]]; then
  # Report file names only. Never print matched content.
  fail "project-specific personal-data/secret patterns matched in: $(printf '%s' "$scan_matches" | tr '\n' ' ')"
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
