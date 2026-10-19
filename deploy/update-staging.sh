#!/usr/bin/env bash
set -euo pipefail

# Staging-only release switch. It keeps the release it switched to, the previous
# release as the named rollback target, and the newest AN3_STAGING_KEEP releases
# in total; older timestamped releases are pruned only after a healthy switch. It
# restores the previous symlink if the new release does not become healthy.

if [[ "$#" -ne 1 ]]; then
  echo "usage: update-staging.sh /path/to/source-archive.tgz" >&2
  exit 2
fi

ARCHIVE="$1"
STAGING_ROOT=/opt/an3-arcade-staging
CURRENT="$STAGING_ROOT/current"
NEXT="$STAGING_ROOT/current.next"
UNIT=an3-arcade-staging.service

[[ -r "$ARCHIVE" ]] || { echo "Staging archive is not readable." >&2; exit 1; }
[[ -L "$CURRENT" ]] || { echo "Staging current release is missing." >&2; exit 1; }
[[ ! -e "$NEXT" ]] || { echo "Refusing to overwrite pending staging symlink." >&2; exit 1; }

PREVIOUS="$(readlink "$CURRENT")"
PREVIOUS_RELEASE="$STAGING_ROOT/$PREVIOUS"
CANDIDATE="$STAGING_ROOT/releases/.candidate-$(date +%Y%m%d-%H%M%S)-$$"

cleanup_candidate() {
  if [[ -n "${CANDIDATE:-}" ]]; then
    rm -rf -- "$CANDIDATE"
  fi
}

# Bounded retention for release directories. Retaining every staging release
# filled 54 GiB with 169 trees on 2026-10-19 for no rollback benefit: only
# `current` and the release it replaced are referenced. This runs after the
# service is healthy, so a prune problem is reported and never fails a release.
prune_staging_releases() {
  local keep="$1" current_name="$2" previous_name="$3" extra old kept=0
  local -a candidates
  if [[ ! "$keep" =~ ^[1-9][0-9]*$ ]]; then
    printf 'STAGING_PRUNE=SKIPPED reason=AN3_STAGING_KEEP-must-be-a-positive-whole-number\n' >&2
    return 0
  fi
  extra=$((keep - 2))
  (( extra > 0 )) || extra=0
  mapfile -t candidates < <(find "$STAGING_ROOT/releases" -mindepth 1 -maxdepth 1 -type d -name '2*' -printf '%f\n' | sort -r)
  for old in "${candidates[@]}"; do
    [[ "$old" == "$current_name" || "$old" == "$previous_name" ]] && continue
    if (( kept < extra )); then
      kept=$((kept + 1))
      continue
    fi
    rm -rf -- "${STAGING_ROOT:?}/releases/$old"
    printf 'STAGING_PRUNED_RELEASE=%s\n' "$old"
  done
}

trap cleanup_candidate EXIT
install -d -m 0755 "$CANDIDATE"
tar -xzf "$ARCHIVE" -C "$CANDIDATE"
[[ -f "$CANDIDATE/app.py" && -d "$CANDIDATE/static" ]] || {
  echo "Staging archive has an unexpected layout." >&2
  exit 1
}
find "$CANDIDATE" -type f -name '._*' -delete
chown -R root:root "$CANDIDATE"
find "$CANDIDATE" -type d -exec chmod 0755 {} +
find "$CANDIDATE" -type f -exec chmod 0644 {} +
chmod 0755 "$CANDIDATE/app.py"
install -o root -g root -m 0755 "$CANDIDATE/deploy/an3-arcade-turbostat.sh" /usr/local/libexec/an3-arcade-turbostat
install -o root -g root -m 0440 "$CANDIDATE/deploy/an3-arcade-turbostat.sudoers" /etc/sudoers.d/an3-arcade-turbostat
visudo -cf /etc/sudoers.d/an3-arcade-turbostat >/dev/null

ASSET="$(python3 - "$CANDIDATE/static" <<'PY'
import hashlib
import os
import sys

root = sys.argv[1]
digest = hashlib.sha256()
for directory, directories, filenames in os.walk(root):
    directories.sort()
    for name in sorted(filenames):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        relative = os.path.relpath(path, root).replace(os.sep, "/")
        digest.update(relative.encode("utf-8"))
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
print(digest.hexdigest()[:12])
PY
)"
RELEASE="$STAGING_ROOT/releases/$(date +%Y%m%d-%H%M%S)-$ASSET"
[[ ! -e "$RELEASE" && ! -L "$RELEASE" ]] || { echo "Release path already exists: $RELEASE" >&2; exit 1; }
mv "$CANDIDATE" "$RELEASE"
CANDIDATE=""

ln -s "releases/$(basename "$RELEASE")" "$NEXT"
mv -T "$NEXT" "$CURRENT"
systemctl restart "$UNIT"
for attempt in $(seq 1 15); do
  HEALTH="$(curl --fail --silent --connect-timeout 2 http://192.168.1.8:8092/health || true)"
  if [[ "$HEALTH" == *'"environment": "staging"'* && "$HEALTH" == *"\"asset_version\": \"$ASSET\""* ]]; then
    printf 'STAGING_RELEASE=PASS\n'
    printf 'STAGING_ASSET=%s\n' "$ASSET"
    printf 'STAGING_RELEASE_PATH=%s\n' "$RELEASE"
    printf 'STAGING_ROLLBACK_TARGET=%s\n' "$PREVIOUS_RELEASE"
    prune_staging_releases "${AN3_STAGING_KEEP:-3}" \
      "$(basename "$RELEASE")" "$(basename "$PREVIOUS_RELEASE")" ||
      printf 'STAGING_PRUNE=FAILED\n' >&2
    exit 0
  fi
  sleep 1
done

ln -s "$PREVIOUS" "$NEXT"
mv -T "$NEXT" "$CURRENT"
systemctl restart "$UNIT"
echo "Staging health failed; previous staging release was restored." >&2
exit 1
