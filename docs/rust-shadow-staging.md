# Rust gateway shadow — staging-only deployment runbook

This is a new, isolated Docker path for validating the Rust cache gateway
alongside the existing Python service. It does **not** replace or restart
`an3-arcade.service`, `an3-arcade-staging.service`, `deploy-stage.sh`, or
`deploy.sh`.

The current release contract from
`/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/09-admin-tab-layout-production-2026-08-24.md`
still applies: validate staging first, retain artifacts/rollback targets, prepare
a matching production review artifact, and never let Codex deploy production.

## Hard boundaries

| Surface | Address / path | Boundary |
| --- | --- | --- |
| Existing Python production | `http://192.168.1.8:8091` | Untouched. |
| Existing Python staging | `http://192.168.1.8:8092` | Read-only upstream for the shadow proxy. |
| Rust shadow gateway | `http://127.0.0.1:18093` by default | Host-network container, explicitly bound only to loopback; port is configurable only in `/etc/an3-rust-shadow-staging.env`. |
| Rust shadow state | `/opt/an3-rust-shadow-staging` | Separate retained source archives and releases only. |
| Redis cache | `127.0.0.1:16379` in the host network; named volume `an3-rust-shadow-staging-redis-data` | Explicit loopback-only cache listener; isolated cache data only; no legacy data volume is mounted. |

The Compose file must use the `gateway` and `redis` services. Both use host
networking only because the staging host drops bridge forwarding to the Python
staging LAN listener. This does not expose either service: the gateway binds
only `127.0.0.1:${AN3_SHADOW_STAGE_PORT:-18093}` and Redis binds only
`127.0.0.1:16379`; the release/rollback helpers verify those listeners with
`ss`, and verify Redis with a direct `PING`. The gateway has no host/data mount
(only a disposable `/tmp` tmpfs), so it cannot open or write SQLite. It proxies
the existing staging `/health` body and adds `X-AN3-Gateway: rust-shadow`; it
never writes legacy SQLite, ROM, session, account, PWA, dashboard, or admin
data. Redis alone retains its isolated cache volume at `/data`.

Do not add a Cloudflare/tunnel route for port `18093`.

## Verified SSH requirement

Use the owner-installed key/agent and verified host key process in
`/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/tools/ssh/README.md`.
The supplied SSH **client-key** fingerprint is not a staging-server host-key
verification; verify the server key out of band and store it in a persistent,
owner-controlled known-hosts file first.

```bash
ROOT=/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade
export AN3_STAGING_SSH_IDENTITY_FILE=/absolute/path/to/owner-approved-staging-key
export AN3_STAGING_SSH_KNOWN_HOSTS=/absolute/path/to/verified-known_hosts
"$ROOT/tools/ssh/check-staging-key.sh"
```

Only `STAGING_SSH_KEY_AUTH=PASS` permits the next step. The provided scripts
use `BatchMode=yes`, public-key authentication only, and
`StrictHostKeyChecking=yes`. Do not use password helpers,
`StrictHostKeyChecking=no`, a temporary known-hosts file, or an unverified IP
address.

## One-time staging helper bootstrap

This is performed only on the authorized staging host, after review. It
installs root-owned helpers and creates the root-owned staging config if absent;
it does not start Docker, delete anything, or touch existing application data.

```bash
ROOT=/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade
source "$ROOT/tools/ssh/staging-common.sh"
"$ROOT/tools/ssh/check-staging-key.sh"
BOOTSTRAP_DIR="/tmp/an3-rust-shadow-helper-$(date +%Y%m%d-%H%M%S)"
staging_ssh "umask 077; mkdir -p '$BOOTSTRAP_DIR'"
scp "${AN3_STAGING_SSH_ARGS[@]}" \
  "$ROOT/deploy/shadow/install-rust-shadow-staging-helper.sh" \
  "$ROOT/deploy/shadow/update-rust-shadow-staging.sh" \
  "$ROOT/deploy/shadow/rollback-rust-shadow-staging.sh" \
  "$AN3_STAGING_SSH_TARGET:$BOOTSTRAP_DIR/"
staging_ssh "sudo -n /bin/bash '$BOOTSTRAP_DIR/install-rust-shadow-staging-helper.sh' '$BOOTSTRAP_DIR'"
```

It installs only:

- `/usr/local/sbin/an3-rust-shadow-staging-release`
- `/usr/local/sbin/an3-rust-shadow-staging-rollback`
- `/etc/an3-rust-shadow-staging.env`
- `/opt/an3-rust-shadow-staging/{incoming,releases}`

The config defaults to `AN3_SHADOW_STAGE_PORT=18093` and the sole allowed
upstream `http://192.168.1.8:8092`. Compose derives the gateway loopback bind
from that port and fixes Redis at `127.0.0.1:16379`; neither listener has a
Docker port mapping. The gateway port can be changed only to an unused
non-legacy port; `8091`, `8092`, and `8093` are rejected by both release and
rollback helpers. Do not point it at production.

## Staging release

Run local tests first. This runbook changes only the shadow service; it does
not authorize a legacy service or production release.

```bash
ROOT=/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade
cd "$ROOT"
bash -n deploy-rust-shadow-stage.sh deploy/shadow/*.sh
SMOKE_DIR="$ROOT/work/shadow-deploy-artifacts/package-smoke-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$SMOKE_DIR"
./deploy/shadow/package-rust-shadow.sh "$SMOKE_DIR/an3-rust-shadow-smoke.tgz"
./deploy-rust-shadow-stage.sh
```

`deploy-rust-shadow-stage.sh` first creates a new retained directory under
`work/shadow-deploy-artifacts/<timestamp>/`. It then creates the staging source
archive, a byte-identical production-review archive, an owner-gated production
script, and a review manifest. Only the staging archive is copied via the
verified SSH path. The root-owned staging helper moves that archive into
`/opt/an3-rust-shadow-staging/incoming/`, creates a retained release, validates
the host-network loopback binding/Redis isolation/no-gateway-mount contract,
checks direct Redis `PING` on `127.0.0.1:16379`, and health checks
`http://127.0.0.1:18093/health` before atomically switching `current`.

`rust-gateway/Cargo.lock` is mandatory. Packaging and the Docker builder both
refuse an unlocked dependency graph; update the reviewed lockfile with Rust
1.88 before making a candidate artifact.

Expected success markers include:

```text
STAGING_SHADOW_RELEASE=PASS
STAGING_SHADOW_PORT=127.0.0.1:18093
PRODUCTION_SHADOW_RELEASE_READY=PASS
PRODUCTION_SHADOW_EXECUTED=NO
```

Validate the returned staging shadow directly through the same strict SSH path:

```bash
ROOT=/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade
source "$ROOT/tools/ssh/staging-common.sh"
staging_ssh 'curl --fail --silent --show-error -D - http://127.0.0.1:18093/health'
```

The response must retain the legacy staging health JSON and include
`X-AN3-Gateway: rust-shadow`. It must not be exposed publicly.

## Rollback and safe handling

Every successful release prints `STAGING_SHADOW_ROLLBACK_TARGET`. To rollback,
use that retained direct release directory:

```bash
ROOT=/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade
source "$ROOT/tools/ssh/staging-common.sh"
staging_ssh 'sudo -n /usr/local/sbin/an3-rust-shadow-staging-rollback /opt/an3-rust-shadow-staging/releases/YYYYMMDD-HHMMSS-asset'
```

Each source archive is built under a full archive-digest image tag and records
the resulting local image identity in its retained release. If a new candidate
fails health, the release helper restores the preceding shadow Compose release
with `--no-build`; it refuses a release or rollback when the needed retained
image/tag identity is unavailable locally. On an initial-release failure it
stops the candidate containers but retains its source archive, candidate
directory, health output, and Redis volume for inspection. It never rolls back,
restarts, or alters the legacy Python staging/production services.

Do not remove anything as routine cleanup:

- Never run `docker compose down -v`, `docker volume rm`, `rm -rf` on
  `/opt/an3-rust-shadow-staging`, or delete the artifact/release/archive trees.
- Do not delete existing project backups, SQLite files, Redis cache volumes,
  ROMs, sessions, or production/staging data.
- If a temporary shutdown is necessary, use `docker compose ... stop` for the
  `an3-rust-shadow-staging` project; this is reversible and preserves volumes.

## Matching production artifact — prepared only

For handoff parity, every staging command produces:

- `an3-rust-shadow-production-candidate-<timestamp>.tgz`
- `deploy-an3-rust-shadow-production-<timestamp>.sh`
- `an3-rust-shadow-production-review-<timestamp>.txt`

They remain local in the retained artifact directory. The staging command never
copies them to a production host and never invokes their script. The generated
script refuses to run unless a future owner manually supplies the exact
`AN3_RUST_SHADOW_PRODUCTION_OWNER_APPROVAL=EXPLICIT_OWNER_APPROVAL` gate and a
separate production-specific release helper exists. That future action requires
a fresh, explicit owner approval and its own production backup/validation plan;
it is outside this staging-only refactor.

## Cutover is unavailable in this release

The normal shadow service remains loopback-only. There is no supported staging
or production cutover in this release: both retained cutover helper paths fail
closed without changing listeners, systemd units, containers, or legacy
services. See
`/Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/docs/rust-shadow-staging-cutover.md`
for the boundary and future-design requirements.
