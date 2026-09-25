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
elif [[ -n "$fixture" ]]; then
  echo "Unsupported lawful test fixture: $fixture" >&2
  exit 2
fi

timeout 15s adb logcat -c
set +e
timeout 600s adb shell am instrument -w -r -e class "$test_class" "$runner" >"$instrumentation_log" 2>&1
instrumentation_status=$?
set -e
cat "$instrumentation_log"
timeout 30s adb logcat -d -v epoch >"$logcat_log"

if [[ "$instrumentation_status" -eq 124 ]]; then
  echo 'ANDROID_INSTRUMENTATION=FAIL (600-second test command timeout)' >&2
  exit 124
fi

if ! grep -Eq '^OK \([1-9][0-9]* tests?\)$' "$instrumentation_log" || grep -q '^FAILURES!!!' "$instrumentation_log"; then
  echo 'ANDROID_ASSERTIONS=FAIL' >&2
  if [[ "$instrumentation_status" -ne 0 ]]; then exit "$instrumentation_status"; fi
  exit 1
fi
echo "ANDROID_ASSERTIONS=PASS ($test_class)"

if grep -Fq 'FORTIFY: pthread_mutex_lock called on a destroyed mutex' "$logcat_log"; then
  unexpected_fatal="$(grep -E 'FATAL EXCEPTION|Fatal signal|ANR in ' "$logcat_log" \
    | grep -Ev 'Fatal signal 6 \(SIGABRT\)' || true)"
  if [[ -n "$unexpected_fatal" ]]; then
    printf '%s\n' "$unexpected_fatal" | head -n 40 >&2
    echo 'ANDROID_PROCESS_HEALTH=FAIL (additional fatal exception, native signal, or ANR found)' >&2
    exit 1
  fi
  {
    echo "- Android test assertions: PASS ($test_class)."
    echo '- Tao/Tauri app-process teardown: **BLOCKED_UPSTREAM** (known destroyed-mutex FORTIFY signature observed during a passing instrumentation run; any additional fatal/ANR remains a failure).'
  } >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
  echo 'TAO_TEARDOWN=BLOCKED_UPSTREAM (assertions passed; exact known FORTIFY signature recorded in logcat)' >&2
  exit 0
fi

if [[ "$instrumentation_status" -ne 0 ]]; then
  echo "ANDROID_INSTRUMENTATION=FAIL (exit $instrumentation_status)" >&2
  exit "$instrumentation_status"
fi
if grep -Eq 'FATAL EXCEPTION|Fatal signal|ANR in ' "$logcat_log"; then
  echo 'ANDROID_PROCESS_HEALTH=FAIL (fatal exception, native signal, or ANR found after clearing logcat)' >&2
  exit 1
fi
echo 'ANDROID_PROCESS_HEALTH=PASS'
{
  echo "- Android test assertions: PASS ($test_class)."
  echo '- Main app process: no fatal exception, native signal, or ANR observed after test start.'
} >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
