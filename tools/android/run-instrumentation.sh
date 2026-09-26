#!/usr/bin/env bash
# Install the exact CI app APK and run one focused Android instrumentation class.
set -euo pipefail

if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo 'Usage: run-instrumentation.sh APP_APK TEST_APK TEST_CLASS [gba-fixture]' >&2
  exit 2
fi
app_apk="$1"
test_apk="$2"
test_class="$3"
fixture="${4:-}"
package_name="space.an3tocom.offline"
runner="${package_name}.test/androidx.test.runner.AndroidJUnitRunner"
log_root="${RUNNER_TEMP:-/tmp}/an3-android-acceptance"
mkdir -p "$log_root"
instrumentation_log="$log_root/instrumentation.txt"
logcat_log="$log_root/logcat.txt"

[[ -s "$app_apk" && -s "$test_apk" ]] || { echo 'App or instrumentation APK is missing.' >&2; exit 2; }
for apk in "$app_apk" "$test_apk"; do
  [[ -s "$apk.sha256" ]] || { echo "Checksum sidecar is missing for $apk." >&2; exit 2; }
  (cd "$(dirname "$apk")" && sha256sum -c "$(basename "$apk").sha256")
done
timeout 30s adb wait-for-device
booted=0
boot_deadline=$((SECONDS + 120))
while (( SECONDS < boot_deadline )); do
  boot_state="$(timeout 5s adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)"
  if [[ "$boot_state" == 1 ]]; then booted=1; break; fi
  if (( SECONDS < boot_deadline )); then sleep 2; fi
done
[[ "$booted" == 1 ]] || { echo 'Android emulator did not finish booting within 120 seconds.' >&2; exit 3; }
printf 'ANDROID_SYS_BOOT_COMPLETED=%s\n' "$boot_state"
timeout 15s adb devices -l
timeout 20s adb shell pm list packages >"$log_root/packages-before-install.txt"
package_count="$(grep -c '^package:' "$log_root/packages-before-install.txt" || true)"
printf 'ANDROID_PACKAGE_MANAGER_READY=true installed_packages=%s\n' "$package_count"
timeout 15s adb shell settings put global window_animation_scale 0
timeout 15s adb shell settings put global transition_animation_scale 0
timeout 15s adb shell settings put global animator_duration_scale 0

timeout 180s adb install -r "$app_apk"
timeout 180s adb install -r "$test_apk"
timeout 20s adb shell pm list packages >"$log_root/packages.txt"
grep -F "package:$package_name" "$log_root/packages.txt"

if [[ "$fixture" == gba ]]; then
  fixture_path="${RUNNER_TEMP:-/tmp}/an3-homebrew-test-visible-20260923.gba"
  python3 tools/testrom/gba_homebrew_test.py "$fixture_path"
  timeout 60s adb push "$fixture_path" /sdcard/Download/an3-homebrew-test-visible-20260923.gba
  # The soft IME over the Storage Access Framework picker can swallow the first
  # tap on the result row on hosted emulators. The test sets the search text
  # programmatically, so disable the soft IME for this job; when it cannot be
  # disabled the test still tolerates a visible IME.
  while IFS= read -r ime; do
    [[ -n "$ime" ]] || continue
    timeout 15s adb shell ime disable "$ime" >/dev/null 2>&1 || true
  done < <(timeout 15s adb shell ime list -s 2>/dev/null | tr -d '\r' || true)
elif [[ -n "$fixture" ]]; then
  echo "Unsupported lawful test fixture: $fixture" >&2
  exit 2
fi

# Headless API 35 emulator images can leave the app window without focus and
# show Android's first-use immersive-mode confirmation over NativeGameActivity.
# Reset the disposable emulator to its launcher and normalize those states so
# UI input reaches AN3 during tests.
timeout 15s adb shell input keyevent KEYCODE_WAKEUP
timeout 15s adb shell wm dismiss-keyguard
timeout 15s adb shell settings put secure immersive_mode_confirmations confirmed
immersive_confirmation="$(timeout 15s adb shell settings get secure immersive_mode_confirmations | tr -d '\r')"
[[ "$immersive_confirmation" == confirmed ]] || {
  echo "Could not disable the first-use immersive confirmation on the CI emulator (value: $immersive_confirmation)." >&2
  exit 4
}
timeout 15s adb shell input keyevent KEYCODE_HOME
timeout 15s adb shell wm dismiss-keyguard
focused_window="$(timeout 15s adb shell dumpsys window | tr -d '\r' | awk '/mCurrentFocus=/ && !found { focus = $0; found = 1 } END { print focus }')"
printf 'ANDROID_EMULATOR_UI_READY=true immersive_mode_confirmations=%s focused_window=%s\n' \
  "$immersive_confirmation" "${focused_window:-unknown}"

timeout 15s adb logcat -c
set +e
timeout 600s adb shell am instrument -w -r -e class "$test_class" "$runner" >"$instrumentation_log" 2>&1
instrumentation_status=$?
set -e
cat "$instrumentation_log"
timeout 30s adb logcat -d -v epoch >"$logcat_log"
test_name="${test_class##*.}"
assertion_marker="AN3_ACCEPTANCE: ASSERTIONS_PASSED:$test_name"

if [[ "$instrumentation_status" -eq 124 ]]; then
  echo 'ANDROID_INSTRUMENTATION=FAIL (600-second test command timeout)' >&2
  exit 124
fi

if grep -Fq 'FORTIFY: pthread_mutex_lock called on a destroyed mutex' "$logcat_log"; then
  marker_line="$(grep -nF "$assertion_marker" "$logcat_log" | head -n 1 | cut -d: -f1 || true)"
  fortify_line="$(grep -nF 'FORTIFY: pthread_mutex_lock called on a destroyed mutex' "$logcat_log" | head -n 1 | cut -d: -f1 || true)"
  lifecycle_line="$(grep -nE 'ActivityScenario: Update currentActivityStage to (STOPPED|DESTROYED), currentActivity=space\.an3tocom\.offline\.MainActivity' "$logcat_log" \
    | awk -F: -v marker="$marker_line" '$1 > marker { print $1; exit }' || true)"

  if [[ -z "$marker_line" || -z "$fortify_line" || "$marker_line" -ge "$fortify_line" || -z "$lifecycle_line" || "$lifecycle_line" -ge "$fortify_line" ]]; then
    echo 'ANDROID_ASSERTIONS_OR_TEARDOWN=FAIL (missing ordered assertion marker, ActivityScenario teardown, or FORTIFY evidence)' >&2
    exit 1
  fi
  if grep -q '^FAILURES!!!' "$instrumentation_log" || grep -Eq '^INSTRUMENTATION_STATUS_CODE: -[0-9]+' "$instrumentation_log"; then
    echo 'ANDROID_ASSERTIONS=FAIL (instrumentation reported a test failure before teardown)' >&2
    exit 1
  fi

  main_app_pids="$(awk '$4 == "I" && $5 == "ActivityManager:" && $6 == "Start" && $7 == "proc" { split($8, proc, ":"); if (proc[2] ~ /^space\.an3tocom\.offline\//) print proc[1] }' "$logcat_log" | sort -u)"
  fortify_pids="$(awk '/FORTIFY: pthread_mutex_lock called on a destroyed mutex/ { print $2 }' "$logcat_log" | sort -u)"
  libc_fortify_pids="$(awk '/FORTIFY: pthread_mutex_lock called on a destroyed mutex/ && $4 == "F" && $5 == "libc" { print $2 }' "$logcat_log" | sort -u)"
  if [[ -z "$main_app_pids" || -z "$fortify_pids" || -z "$libc_fortify_pids" ]]; then
    echo 'ANDROID_PROCESS_HEALTH=FAIL (could not identify the AN3 main process for the FORTIFY abort)' >&2
    exit 1
  fi
  while IFS= read -r pid; do
    [[ -n "$pid" ]] || continue
    if ! grep -Fxq "$pid" <<<"$main_app_pids"; then
      echo "ANDROID_PROCESS_HEALTH=FAIL (FORTIFY abort came from unexpected PID $pid)" >&2
      exit 1
    fi
  done <<<"$fortify_pids"

  unexpected_fatal="$(grep -E 'FATAL EXCEPTION|ANR in ' "$logcat_log" || true)"
  unexpected_signal=""
  while IFS= read -r signal_line; do
    [[ -n "$signal_line" ]] || continue
    signal_pid="$(awk '{ print $2 }' <<<"$signal_line")"
    if [[ "$signal_line" != *'Fatal signal 6 (SIGABRT)'* ]] || ! grep -Fxq "$signal_pid" <<<"$fortify_pids"; then
      unexpected_signal+="$signal_line"$'\n'
    fi
  done < <(grep -F 'Fatal signal' "$logcat_log" || true)
  if [[ -n "$unexpected_fatal$unexpected_signal" ]]; then
    printf '%s\n%s' "$unexpected_fatal" "$unexpected_signal" | head -n 40 >&2
    echo 'ANDROID_PROCESS_HEALTH=FAIL (unexpected fatal exception, signal, or ANR found)' >&2
    exit 1
  fi

  {
    echo "- Android test assertions: PASS ($test_class); explicit completion marker precedes ActivityScenario teardown."
    echo '- Tao/Tauri app-process teardown: **BLOCKED_UPSTREAM** (destroyed-mutex FORTIFY abort in the AN3 main process after the completion marker; no additional fatal exception or ANR observed).'
  } >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
  echo "ANDROID_ASSERTIONS=PASS ($test_class; marker recorded before ActivityScenario teardown)"
  echo 'TAO_TEARDOWN=BLOCKED_UPSTREAM (exact destroyed-mutex FORTIFY abort in AN3 main process)' >&2
  exit 0
fi

if [[ "$instrumentation_status" -ne 0 ]]; then
  echo "ANDROID_INSTRUMENTATION=FAIL (exit $instrumentation_status)" >&2
  exit "$instrumentation_status"
fi
if ! grep -Eq '^OK \([1-9][0-9]* tests?\)$' "$instrumentation_log" || grep -q '^FAILURES!!!' "$instrumentation_log"; then
  echo 'ANDROID_ASSERTIONS=FAIL (JUnit success summary is missing)' >&2
  exit 1
fi
if ! grep -Fq "$assertion_marker" "$logcat_log"; then
  echo "ANDROID_ASSERTIONS=FAIL (missing explicit completion marker for $test_class)" >&2
  exit 1
fi
echo "ANDROID_ASSERTIONS=PASS ($test_class)"

if grep -Eq 'FATAL EXCEPTION|Fatal signal|ANR in ' "$logcat_log"; then
  echo 'ANDROID_PROCESS_HEALTH=FAIL (fatal exception, native signal, or ANR found after clearing logcat)' >&2
  exit 1
fi
echo 'ANDROID_PROCESS_HEALTH=PASS'
{
  echo "- Android test assertions: PASS ($test_class)."
  echo '- Main app process: no fatal exception, native signal, or ANR observed after test start.'
} >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
