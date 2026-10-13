#!/usr/bin/env bash
set -uo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT" || exit 1
failed=0
run_check() {
  local name=$1
  shift
  printf '\n== %s ==\n' "$name"
  if "$@"; then
    printf 'RESULT: PASS — %s\n' "$name"
  else
    local rc=$?
    printf 'RESULT: FAIL (exit %s) — %s\n' "$rc" "$name"
    failed=1
  fi
}
run_check 'Web/backend Python tests' python3 -m unittest discover -s tests
run_check 'Web/native JavaScript behavior tests' node --test --test-concurrency=1 tests/*.test.mjs tests/*.test.js
run_check 'Native application source checks' npm --prefix native-offline run check
if (( failed )); then
  printf '\nPROJECT_VERIFY=FAIL\n'
  exit 1
fi
printf '\nPROJECT_VERIFY=PASS\n'
