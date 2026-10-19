#!/usr/bin/env bash
# Run a command against an AVD using temporary writable userdata and cache.
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo 'Usage: run-with-disposable-avd.sh AVD_NAME [emulator options...] -- COMMAND [ARG...]' >&2
  exit 2
fi

avd_name="$1"
shift
emulator_args=()
emulator_args_count=0
while (($#)) && [[ "$1" != -- ]]; do
  emulator_args+=("$1")
  emulator_args_count=$((emulator_args_count + 1))
  shift
done
[[ "${1:-}" == -- ]] || { echo 'Expected -- before the command.' >&2; exit 2; }
shift
(($#)) || { echo 'A command is required after --.' >&2; exit 2; }
[[ "$avd_name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo 'Invalid AVD name.' >&2; exit 2; }

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
bash "$repo_root/tools/disk-preflight.sh" 'Android disposable AVD' "$repo_root"
sdk_root="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
emulator="$sdk_root/emulator/emulator"
adb="$sdk_root/platform-tools/adb"
[[ -x "$emulator" && -x "$adb" ]] || { echo 'Android emulator and adb are required.' >&2; exit 2; }

port="${AN3_ANDROID_EMULATOR_PORT:-5554}"
[[ "$port" =~ ^[0-9]+$ ]] && (( port >= 5554 && port <= 5682 && port % 2 == 0 )) || {
  echo 'AN3_ANDROID_EMULATOR_PORT must be an even port from 5554 through 5682.' >&2
  exit 2
}
serial="emulator-$port"
if "$adb" devices | awk -v serial="$serial" '$1 == serial { found = 1 } END { exit !found }'; then
  echo "Android emulator $serial is already present; refusing to interfere with it." >&2
  exit 3
fi

run_bounded() {
  local seconds="$1" pid deadline
  shift
  "$@" &
  pid=$!
  deadline=$((SECONDS + seconds))
  while kill -0 "$pid" 2>/dev/null; do
    if (( SECONDS >= deadline )); then
      kill -TERM "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
      return 124
    fi
    sleep 1
  done
  wait "$pid"
}

scratch="$(mktemp -d "${TMPDIR:-/tmp}/an3-avd.XXXXXX")"
emulator_pid=''
cleanup() {
  if [[ -n "$emulator_pid" ]]; then
    "$adb" -s "$serial" emu kill >/dev/null 2>&1 || kill -TERM "$emulator_pid" 2>/dev/null || true
    wait "$emulator_pid" 2>/dev/null || true
  fi
  rm -rf -- "$scratch"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

emulator_command=("$emulator" -avd "$avd_name" -port "$port"
  -data "$scratch/userdata.img" -cache "$scratch/cache.img"
  -no-snapshot -no-boot-anim -no-audio)
if (( emulator_args_count > 0 )); then emulator_command+=("${emulator_args[@]}"); fi
"${emulator_command[@]}" >/dev/null 2>&1 &
emulator_pid=$!
run_bounded 180 "$adb" -s "$serial" wait-for-device
deadline=$((SECONDS + 180))
while (( SECONDS < deadline )); do
  booted="$(run_bounded 5 "$adb" -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)"
  [[ "$booted" == 1 ]] && break
  kill -0 "$emulator_pid" 2>/dev/null || { echo 'Disposable Android emulator exited during boot.' >&2; exit 4; }
  sleep 2
done
[[ "${booted:-}" == 1 ]] || { echo 'Disposable Android emulator did not boot within 180 seconds.' >&2; exit 4; }

ANDROID_SERIAL="$serial" AN3_DISPOSABLE_AVD=1 "$@"
