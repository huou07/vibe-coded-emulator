#!/usr/bin/env bash
set -euo pipefail

# Staging-only rollback for a retained Rust shadow release.  It switches no
# production or legacy service, deletes no release/archive, and never uses
# `docker compose down -v` or `docker volume rm`.

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

assert_secure_root_env() {
  local file="$1" mode group_digit other_digit
  [[ -f "$file" && ! -L "$file" ]] || die "Missing or unsafe staging-only env file: $file"
  [[ "$(stat -c '%U' -- "$file")" == root ]] || die "Staging shadow env file must be root-owned: $file"
  mode="$(stat -c '%a' -- "$file")" || die "Cannot read staging shadow env permissions: $file"
  [[ "$mode" =~ ^[0-7]{3,4}$ ]] || die "Staging shadow env mode is invalid: $file"
  group_digit="${mode: -2:1}"
  other_digit="${mode: -1}"
  (( (10#$group_digit & 2) == 0 && (10#$other_digit & 2) == 0 )) \
    || die "Staging shadow env file must not be group- or other-writable: $file"
}

[[ "$(id -u)" -eq 0 ]] || die 'The staging shadow rollback helper must run as root.'
if [[ "$#" -ne 1 ]]; then
  printf 'usage: an3-rust-shadow-staging-rollback /opt/an3-rust-shadow-staging/releases/YYYYMMDD-HHMMSS-asset\n' >&2
  exit 2
fi

TARGET="$1"
STATE_ROOT=/opt/an3-rust-shadow-staging
RELEASES="$STATE_ROOT/releases"
CURRENT="$STATE_ROOT/current"
NEXT="$STATE_ROOT/current.next"
ENV_FILE=/etc/an3-rust-shadow-staging.env
PROJECT=an3-rust-shadow-staging
COMPOSE_NAME=compose.rust-shadow.staging.yml
IMAGE_REPOSITORY=an3-arcade/rust-gateway-shadow

[[ -L "$CURRENT" ]] || die "Staging shadow current release is missing: $CURRENT"
[[ -d "$TARGET" && ! -L "$TARGET" ]] || die 'Rollback target must be a retained, non-symlink release directory.'
[[ "$(dirname "$TARGET")" == "$RELEASES" ]] || die "Rollback target must be directly inside $RELEASES."
[[ ! -e "$NEXT" && ! -L "$NEXT" ]] || die "Refusing to overwrite pending staging-shadow symlink: $NEXT"
assert_secure_root_env "$ENV_FILE"

# shellcheck disable=SC1090
set -a
source "$ENV_FILE"
set +a

PORT="${AN3_SHADOW_STAGE_PORT:-18093}"
UPSTREAM="${AN3_GATEWAY_UPSTREAM:-http://192.168.1.8:8092}"
REDIS_PORT=16379
[[ "$PORT" =~ ^[1-9][0-9]{0,4}$ ]] || die 'AN3_SHADOW_STAGE_PORT must be a TCP port number.'
(( PORT >= 1024 && PORT <= 65535 )) || die 'AN3_SHADOW_STAGE_PORT must be between 1024 and 65535.'
[[ "$PORT" != 8091 && "$PORT" != 8092 && "$PORT" != 8093 ]] || die 'Shadow port must not reuse a legacy or container service port.'
[[ "$UPSTREAM" == 'http://192.168.1.8:8092' ]] || die 'The staging shadow may only proxy the isolated staging LAN upstream on 192.168.1.8:8092.'

export AN3_SHADOW_STAGE_PORT="$PORT"
export AN3_GATEWAY_UPSTREAM="$UPSTREAM"
export COMPOSE_PROJECT_NAME="$PROJECT"

compose_for() {
  local release_dir="$1"
  shift
  local image_tag
  image_tag="$(image_tag_for "$release_dir")"
  AN3_SHADOW_IMAGE_TAG="$image_tag" docker compose \
    --project-name "$PROJECT" \
    --env-file "$ENV_FILE" \
    --project-directory "$release_dir" \
    -f "$release_dir/$COMPOSE_NAME" \
    "$@"
}

image_tag_for() {
  local release_dir="$1"
  local tag_file="$release_dir/.image-tag"
  local image_tag
  [[ -f "$tag_file" && ! -L "$tag_file" ]] || die "Release is missing immutable image metadata: $tag_file"
  image_tag="$(<"$tag_file")"
  [[ "$image_tag" =~ ^staging-[a-f0-9]{64}$ ]] || die "Release has an invalid immutable image tag: $tag_file"
  printf '%s\n' "$image_tag"
}

image_ref_for() {
  printf '%s:%s\n' "$IMAGE_REPOSITORY" "$(image_tag_for "$1")"
}

image_id_for() {
  local release_dir="$1"
  local id_file="$release_dir/.image-id"
  local image_id
  [[ -f "$id_file" && ! -L "$id_file" ]] || die "Release is missing retained image identity: $id_file"
  image_id="$(<"$id_file")"
  [[ "$image_id" =~ ^sha256:[a-f0-9]{64}$ ]] || die "Release has an invalid retained image identity: $id_file"
  printf '%s\n' "$image_id"
}

ensure_release_image() {
  local image_ref expected_id actual_id
  image_ref="$(image_ref_for "$1")"
  expected_id="$(image_id_for "$1")"
  actual_id="$(docker image inspect "$image_ref" --format '{{.Id}}')" \
    || die "Retained rollback image is unavailable locally: $image_ref; refusing a rebuild during rollback."
  [[ "$actual_id" == "$expected_id" ]] \
    || die "Retained rollback image identity changed for $image_ref; refusing a rebuild during rollback."
}

release_image_is_available() {
  local release_dir="$1"
  local tag_file="$release_dir/.image-tag" id_file="$release_dir/.image-id"
  local image_tag expected_id actual_id
  [[ -f "$tag_file" && ! -L "$tag_file" ]] || return 1
  [[ -f "$id_file" && ! -L "$id_file" ]] || return 1
  image_tag="$(<"$tag_file")"
  expected_id="$(<"$id_file")"
  [[ "$image_tag" =~ ^staging-[a-f0-9]{64}$ ]] || return 1
  [[ "$expected_id" =~ ^sha256:[a-f0-9]{64}$ ]] || return 1
  actual_id="$(docker image inspect "$IMAGE_REPOSITORY:$image_tag" --format '{{.Id}}')" || return 1
  [[ "$actual_id" == "$expected_id" ]]
}

validate_compose() {
  local release_dir="$1"
  local compose_file="$release_dir/$COMPOSE_NAME"
  local rendered
  [[ -f "$compose_file" ]] || die "Rollback release lacks $COMPOSE_NAME"
  if grep -nE '(/srv/an3-arcade|/opt/an3-arcade|arcade\.db|/roms?([/:]|$)|sqlite:)' "$compose_file"; then
    die 'Rollback release attempts to reference legacy data.'
  fi
  grep -Fq 'rust-shadow-redis-data' "$compose_file" || die 'Rollback release lacks its isolated Redis volume.'
  compose_for "$release_dir" config -q
  compose_for "$release_dir" config --services | grep -Fxq gateway
  compose_for "$release_dir" config --services | grep -Fxq redis
  rendered="$(compose_for "$release_dir" config)"
  [[ "$(printf '%s\n' "$rendered" | grep -Fc 'network_mode: host')" -eq 2 ]] \
    || die 'Gateway and Redis must both use host networking on this staging host.'
  if printf '%s\n' "$rendered" | grep -Eq '^[[:space:]]+ports:'; then
    die 'Host-network shadow services must not have Docker port mappings.'
  fi
  printf '%s\n' "$rendered" | grep -Fq "AN3_GATEWAY_BIND: 127.0.0.1:$PORT" \
    || die 'Gateway must bind only the configured host loopback port.'
  printf '%s\n' "$rendered" | grep -Fq 'AN3_GATEWAY_REDIS_URL: redis://127.0.0.1:16379/0' \
    || die 'Gateway must use only the loopback Redis listener.'
  printf '%s\n' "$rendered" | grep -Fq -- '- --bind' \
    || die 'Redis must explicitly bind its loopback listener.'
  printf '%s\n' "$rendered" | grep -Fq -- '- "16379"' \
    || die 'Redis must use the dedicated loopback cache port.'
}

assert_loopback_listener() {
  local port="$1" component="$2"
  local listeners listener local_address
  command -v ss >/dev/null 2>&1 || die 'The staging host requires ss to validate host-network listeners.'
  listeners="$(ss -H -ltn4 "sport = :$port" 2>/dev/null || true)"
  [[ -n "$listeners" ]] || die "$component is not listening on 127.0.0.1:$port."
  while IFS= read -r listener; do
    [[ -n "$listener" ]] || continue
    read -r _ _ _ local_address _ <<< "$listener"
    [[ "$local_address" == "127.0.0.1:$port" ]] \
      || die "$component has a non-loopback IPv4 listener on port $port: $local_address"
  done <<< "$listeners"
  if ss -H -ltn6 "sport = :$port" 2>/dev/null | grep -q .; then
    die "$component must not expose an IPv6 listener on port $port."
  fi
}

check_redis() {
  local redis_id="$1" attempt
  for attempt in $(seq 1 30); do
    if docker exec "$redis_id" redis-cli -h 127.0.0.1 -p "$REDIS_PORT" ping 2>/dev/null | grep -Fxq PONG; then
      return 0
    fi
    sleep 1
  done
  return 1
}

validate_runtime() {
  local release_dir="$1"
  local gateway_id redis_id gateway_network redis_network gateway_bindings redis_bindings gateway_mounts redis_data_mount expected_image actual_image expected_id actual_id

  gateway_id="$(compose_for "$release_dir" ps -q gateway)"
  redis_id="$(compose_for "$release_dir" ps -q redis)"
  [[ -n "$gateway_id" && -n "$redis_id" ]] || die 'Rust shadow gateway or Redis container did not start.'
  expected_image="$(image_ref_for "$release_dir")"
  actual_image="$(docker inspect "$gateway_id" --format '{{.Config.Image}}')"
  [[ "$actual_image" == "$expected_image" ]] || die "Gateway did not start the retained immutable image (expected: $expected_image; observed: ${actual_image:-none})."
  expected_id="$(image_id_for "$release_dir")"
  actual_id="$(docker inspect "$gateway_id" --format '{{.Image}}')"
  [[ "$actual_id" == "$expected_id" ]] || die "Gateway did not start the retained image identity (expected: $expected_id; observed: ${actual_id:-none})."
  gateway_network="$(docker inspect "$gateway_id" --format '{{.HostConfig.NetworkMode}}')"
  redis_network="$(docker inspect "$redis_id" --format '{{.HostConfig.NetworkMode}}')"
  [[ "$gateway_network" == host && "$redis_network" == host ]] \
    || die "Gateway and Redis must use host networking (observed: gateway=${gateway_network:-none}, redis=${redis_network:-none})."
  gateway_bindings="$(docker inspect "$gateway_id" --format '{{json .HostConfig.PortBindings}}')"
  redis_bindings="$(docker inspect "$redis_id" --format '{{json .HostConfig.PortBindings}}')"
  [[ "$gateway_bindings" == null || "$gateway_bindings" == '{}' ]] \
    || die "Gateway must not have Docker port mappings (observed: $gateway_bindings)."
  [[ "$redis_bindings" == null || "$redis_bindings" == '{}' ]] \
    || die "Redis must not have Docker port mappings (observed: $redis_bindings)."
  assert_loopback_listener "$PORT" 'Gateway'
  assert_loopback_listener "$REDIS_PORT" 'Redis'
  check_redis "$redis_id" || die 'Redis did not answer PING on its loopback-only cache listener.'
  gateway_mounts="$(docker inspect "$gateway_id" --format '{{range .Mounts}}{{printf "%s:%s\n" .Type .Destination}}{{end}}')"
  [[ -z "$gateway_mounts" || "$gateway_mounts" == 'tmpfs:/tmp' ]] || die 'Gateway must not receive any host/data mount (only tmpfs:/tmp is allowed).'
  redis_data_mount="$(docker inspect "$redis_id" --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{printf "%s:%t" .Name .RW}}{{end}}{{end}}')"
  [[ "$redis_data_mount" == 'an3-rust-shadow-staging-redis-data:true' ]] || die "Redis must mount only its project-isolated cache volume at /data (observed: ${redis_data_mount:-none})."
}

check_health() {
  local release_dir="$1"
  local header_file="$release_dir/rollback-health.headers"
  local body_file="$release_dir/rollback-health.body"
  local attempt
  for attempt in $(seq 1 30); do
    if curl --fail --silent --show-error --connect-timeout 2 --max-time 5 \
      --dump-header "$header_file" --output "$body_file" "http://127.0.0.1:$PORT/health"; then
      if grep -qi '^X-AN3-Gateway:[[:space:]]*rust-shadow[[:space:]]*' "$header_file" \
        && grep -Eq '"ok"[[:space:]]*:[[:space:]]*true' "$body_file" \
        && grep -Eq '"environment"[[:space:]]*:[[:space:]]*"staging"' "$body_file"; then
        return 0
      fi
    fi
    sleep 1
  done
  return 1
}

previous_link="$(readlink "$CURRENT")"
[[ "$previous_link" == releases/* && "$previous_link" != *'..'* ]] || die 'Staging shadow current symlink is outside its releases directory.'
previous_release="$STATE_ROOT/$previous_link"
[[ -d "$previous_release" && ! -L "$previous_release" ]] || die 'Staging shadow previous release is unavailable.'

# A failed rollback must be able to restore the currently active image without
# rebuilding from source. Refuse the rollback before changing containers if
# that retained image is unavailable.
ensure_release_image "$previous_release"

deploy_started=0
committed=0
recover_on_failure() {
  local status=$?
  trap - EXIT
  if (( status != 0 && deploy_started == 1 && committed == 0 )); then
    printf 'STAGING_SHADOW_ROLLBACK=RESTORING_PREVIOUS\n' >&2
    if release_image_is_available "$previous_release"; then
      compose_for "$previous_release" up --detach --no-build || true
    else
      printf 'STAGING_SHADOW_ROLLBACK_IMAGE=UNAVAILABLE_NO_REBUILD\n' >&2
    fi
    printf 'STAGING_SHADOW_ROLLBACK_PREVIOUS=%s\n' "$previous_release" >&2
  fi
  exit "$status"
}
trap recover_on_failure EXIT

validate_compose "$TARGET"
ensure_release_image "$TARGET"
deploy_started=1
compose_for "$TARGET" up --detach --no-build
validate_runtime "$TARGET"
check_health "$TARGET" || die 'Rollback target did not return the legacy staging health body through the Rust gateway.'

ln -s "releases/$(basename "$TARGET")" "$NEXT"
mv -T "$NEXT" "$CURRENT"
committed=1

printf 'STAGING_SHADOW_ROLLBACK=PASS\n'
printf 'STAGING_SHADOW_IMAGE=%s\n' "$(image_ref_for "$TARGET")"
printf 'STAGING_SHADOW_RELEASE_PATH=%s\n' "$TARGET"
printf 'STAGING_SHADOW_ROLLBACK_PREVIOUS=%s\n' "$previous_release"
printf 'STAGING_SHADOW_PORT=127.0.0.1:%s\n' "$PORT"
