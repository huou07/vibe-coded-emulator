#!/usr/bin/env bash
set -euo pipefail

# Enable the separately packaged Rust EmulatorJS Netplay relay on the isolated
# staging host only.  It has no production paths, data mounts, or database
# access.  The script is intentionally root-only because it changes one
# staging environment file, one staging service, and one narrow LAN firewall
# rule.

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die 'Run as root on the staging host.'
[[ "$#" -eq 0 ]] || die 'Usage: enable-staging-netplay.sh'

STAGING_ROOT=/opt/an3-arcade-staging
CURRENT="$STAGING_ROOT/current"
ENV_FILE=/etc/an3-arcade-staging.env
UNIT=an3-arcade-staging.service
LAN_HOST=192.0.2.8
LAN_CIDR=192.0.2.0/24
PORT=8094
NETPLAY_ORIGIN="http://$LAN_HOST:$PORT"

APP_ROOT="$(readlink -f "$CURRENT")"
[[ "$APP_ROOT" == "$STAGING_ROOT"/releases/* && -f "$APP_ROOT/app.py" ]] || die 'Staging current release is unsafe or unavailable.'
[[ -f "$APP_ROOT/Dockerfile.rust-netplay" && -f "$APP_ROOT/compose.rust-netplay.staging.yml" ]] || die 'Current staging release does not contain the reviewed netplay relay.'
[[ -f "$ENV_FILE" && ! -L "$ENV_FILE" ]] || die 'Staging environment file is unsafe or unavailable.'
grep -Fxq 'AN3_ENVIRONMENT=staging' "$ENV_FILE" || die 'Refusing to enable netplay outside staging.'
grep -Fxq "AN3_HOST=$LAN_HOST" "$ENV_FILE" || die 'Staging environment does not use the approved LAN host.'
command -v docker >/dev/null 2>&1 || die 'Docker is unavailable on the staging host.'
docker compose version >/dev/null 2>&1 || die 'Docker Compose is unavailable on the staging host.'

docker compose -f "$APP_ROOT/compose.rust-netplay.staging.yml" up --build -d
# The host port intentionally binds to the LAN address rather than loopback.
# Check the service from its network namespace before the UFW exception exists;
# this avoids treating UFW's own correct default-deny policy as a relay failure.
docker compose -f "$APP_ROOT/compose.rust-netplay.staging.yml" exec -T netplay \
  curl --fail --silent --show-error --connect-timeout 5 http://127.0.0.1:4000/games >/dev/null

# The Compose file publishes only this LAN address.  Add the narrow firewall
# rule only after the relay is actually healthy; a failed build leaves no new
# network exposure behind.  Never open a WAN listener or touch production.
command -v ufw >/dev/null 2>&1 || die 'UFW is unavailable on the staging host.'
ufw allow proto tcp from "$LAN_CIDR" to "$LAN_HOST" port "$PORT" comment 'AN3 staging netplay LAN'
# Docker/UFW can reject a same-host connection to its own LAN address even
# while other LAN peers reach the published port.  Validate the exact bind
# locally; deployment acceptance performs the real LAN probe from another host.
command -v ss >/dev/null 2>&1 || die 'ss is unavailable on the staging host.'
ss -ltn "sport = :$PORT" | grep -Fq "$LAN_HOST:$PORT" || die 'Netplay relay is not bound to the approved staging LAN address.'

if grep -q '^AN3_NETPLAY_ORIGIN=' "$ENV_FILE"; then
  sed -i "s|^AN3_NETPLAY_ORIGIN=.*$|AN3_NETPLAY_ORIGIN=$NETPLAY_ORIGIN|" "$ENV_FILE"
else
  printf 'AN3_NETPLAY_ORIGIN=%s\n' "$NETPLAY_ORIGIN" >> "$ENV_FILE"
fi
chmod 0600 "$ENV_FILE"
systemctl restart "$UNIT"

# systemd has accepted the restart before the Python listener necessarily owns
# its socket.  Bound retries avoid treating that short, normal startup window
# as a failed deployment.
health=""
for _ in {1..10}; do
  if health="$(curl --fail --silent --connect-timeout 2 "http://$LAN_HOST:8092/health" 2>/dev/null)"; then
    break
  fi
  sleep 1
done
[[ "$health" == *'"environment": "staging"'* ]] || die 'Staging app health did not return the staging environment.'
csp="$(curl --silent --show-error --connect-timeout 5 --head "http://$LAN_HOST:8092/offline" | tr -d '\r')"
printf '%s\n' "$csp" | grep -Fq "connect-src 'self' blob: https://cdn.emulatorjs.org $NETPLAY_ORIGIN" || die 'Staging player CSP did not allow the reviewed netplay origin.'

printf 'STAGING_NETPLAY=PASS\n'
printf 'STAGING_NETPLAY_ORIGIN=%s\n' "$NETPLAY_ORIGIN"
printf 'STAGING_NETPLAY_PRODUCTION_EXECUTED=NO\n'
