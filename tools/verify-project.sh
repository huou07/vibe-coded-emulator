#!/usr/bin/env bash
# The local verification gate.
#
# Scope is deliberately narrow: this runs only what a Debian workstation can
# run correctly and quickly. Anything needing a real toolchain — Rust/C++
# compilation, Tauri bundles, installers, Android instrumentation, per-platform
# runtime acceptance — is the authority of GitHub Actions and of
# tools/release-train.sh on its dedicated builders, and is NOT simulated here.
#
# Every check is bounded by a wall clock so a hung subprocess cannot wedge a
# session, and the script fails loudly: a check that cannot run is a failure,
# never a silent pass.
set -uo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT" || exit 1

# Per-check wall clock, overridable with VCE_CHECK_TIMEOUT (seconds).
CHECK_TIMEOUT=${VCE_CHECK_TIMEOUT:-600}
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$ROOT/work/verify-pycache}"

failed=0
run_check() {
  local name=$1
  shift
  printf '\n== %s ==\n' "$name"
  local rc=0
  timeout --signal=TERM --kill-after=30 "${CHECK_TIMEOUT}s" "$@" || rc=$?
  if (( rc == 124 || rc == 137 )); then
    printf 'RESULT: FAIL (exit %s) — %s (timed out after %ss)\n' "$rc" "$name" "$CHECK_TIMEOUT"
    failed=1
  elif (( rc != 0 )); then
    printf 'RESULT: FAIL (exit %s) — %s\n' "$rc" "$name"
    failed=1
  else
    printf 'RESULT: PASS — %s\n' "$name"
  fi
}

run_check 'Documentation references' \
  python3 tools/check-docs-refs.py
run_check 'Web/backend Python tests' \
  python3 -m unittest discover -s tests
run_check 'Web/native JavaScript behavior tests' \
  node --test --test-concurrency=1 tests/*.test.mjs tests/*.test.js
run_check 'Native application source checks' \
  npm --prefix native-offline run check
run_check 'Whitespace and conflict markers' \
  git diff --check

if (( failed )); then
  printf '\nPROJECT_VERIFY=FAIL\n'
  exit 1
fi
printf '\nPROJECT_VERIFY=PASS\n'
