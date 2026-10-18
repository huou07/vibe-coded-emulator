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

# --- Emulator-loop throughput budget ------------------------------------------
# docs/QUALITY.md claims this gate enforces the emulator-loop throughput budget.
# That claim only holds when the lane is claimed: tests/an3ctl.test.mjs skips the
# budget assertion unless AN3_PLAYER or AN3_PLAYER_TARGET is set. The portable
# player and its cores are vendored in-tree, so a host that can run this gate can
# claim the lane. A player or fixture that is missing is a failure, never a
# silent skip. Callers may still override both paths.
export AN3_PLAYER="${AN3_PLAYER:-$ROOT/native-offline/vendor/runtime/linux-x86_64/an3-offline-native}"
export AN3_FIXTURE="${AN3_FIXTURE:-$ROOT/work/fixtures/an3-synthetic-gba.gba}"

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
# The Android app is served from committed assets, not from `dist`, so a Web
# edit that skips the mirror ships a stale stylesheet or script. This compares
# every mirrored file against the source it must copy and names the entries that
# are deliberately not copies. Pure file comparison: no build, no device.
run_check 'Native web-asset mirror' 'native-mirror' \
  python3 tools/check-native-mirror.py
# `-v` so unittest reports each skipped test with its reason; the skip manifest
# reads those lines. Verbosity changes what is printed, never what is asserted.
run_check 'Web/backend Python tests' 'python' \
  python3 -m unittest discover -s tests -v
# The fixture is git-ignored build output, so the gate regenerates it before the
# lane runs; on a clean checkout the file does not exist. A caller-supplied
# AN3_FIXTURE is left alone and the test fails loudly if it is absent.
if [[ "$AN3_FIXTURE" == "$ROOT/work/fixtures/an3-synthetic-gba.gba" ]]; then
  run_check 'Emulator fixture' 'emulator-fixture' \
    python3 tools/make-synthetic-gba-fixture.py --output "$AN3_FIXTURE"
fi
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

# --- AEH gate report ----------------------------------------------------------
# The quality contract (.aeh/quality.json) declares .hub/gate-report.json, which
# the Hub ingests after the run; the skipped/not_run lists are taken from the
# skip manifest above and are never re-derived. This step does not change the
# gate's own verdict: exit 0/1 is decided by the checks above exactly as before,
# and a report that was never produced is reported by the Hub as BLOCKED, never
# as a pass, so the gap stays visible without moving the verdict.
printf '\n== Gate report ==\n'
MANIFEST="$LOG_DIR/skip-manifest.json"
if [[ -f "$MANIFEST" ]]; then
  EVIDENCE_CLASS=UNVERIFIED
  (( failed )) || EVIDENCE_CLASS=VERIFIED_SOURCE
  report_args=(
    --root "$ROOT"
    --manifest "$MANIFEST"
    --out "$ROOT/.hub/gate-report.json"
    --covered-gate source-integrity
    --evidence-class "$EVIDENCE_CLASS"
    --runner-label vce-local-source-gate
    --artifact "skip-manifest.json|${MANIFEST#"$ROOT"/}"
    --not-run "native-tauri-build|cross-platform Tauri packaging needs per-platform toolchains and pinned core artifacts and stays with the dedicated builders and GitHub Actions, never with this Debian gate"
    --not-run "android-instrumentation|no Android device or emulator is attached to this host"
    --not-run "windows-macos-native-acceptance|no Windows or macOS host is available to this Debian workstation"
    --not-run "hosted-browser-lane|the Playwright browser semantics lane is the separate browser-runtime CI job and does not run here"
    --limitation "this is the local source gate: it proves source behaviour only and never establishes packaged, native, Android, Windows or macOS acceptance"
    --limitation "the enforced emulator budget is the emulator loop's measured frame-time distribution and its whole-run throughput, both emulator-loop timings: it is not display frame pacing and not audio, and the headless lane runs no audio device (it reports audioMeasured=false); sustained display frame pacing and audio underruns remain UNVERIFIED"
    --limitation "the skipped list comes from tools/verify-skip-manifest.py; a skip is never a pass"
  )
  if ! python3 tools/verify-gate-report.py "${report_args[@]}"; then
    printf 'RESULT: WARN — gate report not written; the Hub blocks on a missing declared report\n'
  fi
else
  # The manifest step above already failed this gate; nothing else to report.
  printf 'RESULT: WARN — no skip manifest, so no gate report was written\n'
fi

if (( failed )); then
  printf '\nPROJECT_VERIFY=FAIL\n'
  exit 1
fi
printf '\nPROJECT_VERIFY=PASS\n'
