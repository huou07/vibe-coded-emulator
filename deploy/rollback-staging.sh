#!/usr/bin/env bash
set -euo pipefail

# Staging-only rollback to one retained, already-built release. The current
# target is restored if the requested rollback target fails health validation.

if [[ "$#" -ne 1 ]]; then
  echo "usage: rollback-staging.sh /opt/an3-arcade-staging/releases/YYYYMMDD-HHMMSS-asset" >&2
  exit 2
fi

TARGET="$1"
STAGING_ROOT=/opt/an3-arcade-staging
RELEASES="$STAGING_ROOT/releases"
CURRENT="$STAGING_ROOT/current"
NEXT="$STAGING_ROOT/current.next"
UNIT=an3-arcade-staging.service

[[ -L "$CURRENT" ]] || { echo "Staging current release is missing." >&2; exit 1; }
[[ -d "$TARGET" && ! -L "$TARGET" ]] || { echo "Rollback target is not a release directory." >&2; exit 1; }
[[ "$(dirname "$TARGET")" == "$RELEASES" ]] || { echo "Rollback target must be directly inside $RELEASES." >&2; exit 1; }
[[ ! -e "$NEXT" && ! -L "$NEXT" ]] || { echo "Refusing to overwrite pending staging symlink." >&2; exit 1; }

PREVIOUS="$(readlink "$CURRENT")"
ln -s "releases/$(basename "$TARGET")" "$NEXT"
mv -T "$NEXT" "$CURRENT"
systemctl restart "$UNIT"

for attempt in $(seq 1 15); do
  if curl --fail --silent --connect-timeout 2 http://192.0.2.8:8092/health | grep -q '"environment": "staging"'; then
    printf 'STAGING_ROLLBACK=PASS\n'
    printf 'STAGING_RELEASE_PATH=%s\n' "$TARGET"
    printf 'STAGING_ROLLBACK_PREVIOUS=%s\n' "$PREVIOUS"
    exit 0
  fi
  sleep 1
done

ln -s "$PREVIOUS" "$NEXT"
mv -T "$NEXT" "$CURRENT"
systemctl restart "$UNIT"
echo "Rollback target failed health; previous staging release was restored." >&2
exit 1
