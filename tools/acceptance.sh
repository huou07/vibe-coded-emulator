#!/usr/bin/env bash
# VCE scoped product admission gate.
# Product evidence is required separately from source and publication checks.
# Hosted builds and browser component checks never imply packaged acceptance.
#
# A check that cannot run is reported as UNVERIFIED with its reason; it is never
# a silent pass. The publication gate is fail-closed by design: when a candidate
# snapshot exists it runs, and any finding fails this gate.
#
# Usage: tools/acceptance.sh --evidence FILE [--with-publication] [--timeout N]
set -uo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT" || exit 1

CHECK_TIMEOUT=900
WITH_PUBLICATION=0
EVIDENCE="${VCE_PRODUCT_EVIDENCE:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --evidence) EVIDENCE=${2:?}; shift 2 ;;
    --with-publication) WITH_PUBLICATION=1; shift ;;
    --timeout) CHECK_TIMEOUT=${2:?}; shift 2 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

if [[ -z "$EVIDENCE" ]]; then
  printf 'PROJECT_ACCEPTANCE=BLOCKED — --evidence FILE is required; source/build success is insufficient\n'
  exit 2
fi
# Fail before spending build/test resources when the claim lacks evidence.
python3 tools/verify-product-evidence.py "$EVIDENCE" --revision "$(git rev-parse HEAD)"
evidence_result=$?
if (( evidence_result != 0 )); then
  if (( evidence_result == 1 )); then
    printf 'PROJECT_ACCEPTANCE=FAIL — observed product failure\n'
  else
    printf 'PROJECT_ACCEPTANCE=BLOCKED — product evidence was rejected (exit %s)\n' "$evidence_result"
  fi
  exit "$evidence_result"
fi
if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  printf 'PROJECT_ACCEPTANCE=BLOCKED — working tree differs from the accepted source\n'
  exit 2
fi

failed=0
run() {
  local name=$1; shift
  printf '\n== %s ==\n' "$name"
  local rc=0
  timeout --signal=TERM --kill-after=30 "${CHECK_TIMEOUT}s" "$@" || rc=$?
  case "$rc" in
    0) printf 'RESULT: PASS — %s\n' "$name" ;;
    124|137) printf 'RESULT: FAIL (timeout %ss) — %s\n' "$CHECK_TIMEOUT" "$name"; failed=1 ;;
    *) printf 'RESULT: FAIL (exit %s) — %s\n' "$rc" "$name"; failed=1 ;;
  esac
}

run 'Source gate (docs refs, Python, JS, native source, whitespace)' \
  bash tools/verify-project.sh

CANDIDATE="${AN3_PUBLICATION_CANDIDATE:-$ROOT/work/public-snapshot}"
if (( WITH_PUBLICATION )); then
  run 'Build the sanitized public snapshot' bash tools/build-public-snapshot.sh
fi
if [[ -d "$CANDIDATE" ]]; then
  run 'Publication gate (fail closed)' bash tools/publication-check.sh "$CANDIDATE"
else
  printf '\nRESULT: UNVERIFIED — no publication candidate at %s\n' "$CANDIDATE"
  printf '        The fail-closed publication gate did not run. Build a candidate\n'
  printf '        with tools/build-public-snapshot.sh (or --with-publication) before\n'
  printf '        any publication claim.\n'
fi

printf '\nNOTE: acceptance covers only the evidence record claim and runtime.\n'
printf '      Other platforms, gameplay and publication remain separate claims.\n'
if (( failed )); then
  printf '\nPROJECT_ACCEPTANCE=FAIL\n'
  exit 1
fi
printf '\nPROJECT_ACCEPTANCE=PASS\n'
