#!/usr/bin/env bash
set -euo pipefail

# Staging-only release switch. It retains every prior staging release and
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
  HEALTH="$(curl --fail --silent --connect-timeout 2 http://192.0.2.8:8092/health || true)"
  if [[ "$HEALTH" == *'"environment": "staging"'* && "$HEALTH" == *"\"asset_version\": \"$ASSET\""* ]]; then
    printf 'STAGING_RELEASE=PASS\n'
    printf 'STAGING_ASSET=%s\n' "$ASSET"
    printf 'STAGING_RELEASE_PATH=%s\n' "$RELEASE"
    printf 'STAGING_ROLLBACK_TARGET=%s\n' "$PREVIOUS_RELEASE"
    exit 0
  fi
  sleep 1
done

ln -s "$PREVIOUS" "$NEXT"
mv -T "$NEXT" "$CURRENT"
systemctl restart "$UNIT"
echo "Staging health failed; previous staging release was restored." >&2
exit 1
