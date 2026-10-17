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
#
# Each check's output is also captured, so the run can end with a machine-readable
# skip manifest (tools/verify-skip-manifest.py). A green run must not hide what it
# did not run: the ledger previously counted 20 Python skips with no visible
# reason.
set -uo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT" || exit 1

# Per-check wall clock, overridable with VCE_CHECK_TIMEOUT (seconds).
CHECK_TIMEOUT=${VCE_CHECK_TIMEOUT:-600}
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$ROOT/work/verify-pycache}"

LOG_DIR="${VCE_VERIFY_LOG_DIR:-$ROOT/work/verify-logs}"
rm -rf "$LOG_DIR"
mkdir -p "$LOG_DIR"

failed=0
run_check() {
  local name=$1
  local slug=$2
  shift 2
  printf '\n== %s ==\n' "$name"
  local log="$LOG_DIR/$slug.log"
  local rc=0
  timeout --signal=TERM --kill-after=30 "${CHECK_TIMEOUT}s" "$@" >"$log" 2>&1 || rc=$?
  cat "$log"
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

run_check 'Documentation references' 'docs-refs' \
  python3 tools/check-docs-refs.py
# `-v` so unittest reports each skipped test with its reason; the skip manifest
# reads those lines. Verbosity changes what is printed, never what is asserted.
run_check 'Web/backend Python tests' 'python' \
  python3 -m unittest discover -s tests -v
run_check 'Web/native JavaScript behavior tests' 'node' \
  node --test --test-concurrency=1 tests/*.test.mjs tests/*.test.js
run_check 'Native application source checks' 'native-source' \
  npm --prefix native-offline run check
run_check 'Whitespace and conflict markers' 'whitespace' \
  git diff --check

# --- Skip manifest ------------------------------------------------------------
# Printed even when a check failed, so the reason a lane did not run is never
# hidden behind a red verdict either. A manifest that cannot be produced fails
# the gate rather than disappearing.
printf '\n== Skip manifest ==\n'
REVISION="$(git rev-parse HEAD 2>/dev/null || true)"
if ! python3 tools/verify-skip-manifest.py \
      --python-log "$LOG_DIR/python.log" \
      --node-log "$LOG_DIR/node.log" \
      --revision "$REVISION" \
      --out "$LOG_DIR/skip-manifest.json"; then
  printf 'RESULT: FAIL — skip manifest could not be produced\n'
  failed=1
fi

if (( failed )); then
  printf '\nPROJECT_VERIFY=FAIL\n'
  exit 1
fi
printf '\nPROJECT_VERIFY=PASS\n'
