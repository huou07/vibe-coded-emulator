# AN3 Rust shadow gateway

This is a staging-only Axum reverse proxy placed in front of the existing AN3
Python application. It is deliberately not a rewrite or a cutover: Python
continues to own all routes, SQLite data, ROMs, accounts, sessions, uploads,
admin authorization, emulator delivery, and application logic.

The accompanying Compose stack starts only a gateway and an isolated Redis
cache. It mounts **no** legacy database, ROM, session, upload, static, or
production path. The staging host drops Docker bridge forwarding to the Python
LAN listener, so both containers use host networking; their own listeners are
nevertheless fixed to loopback: gateway `127.0.0.1:18093` by default and Redis
`127.0.0.1:16379`. The default upstream remains the isolated staging service
at `192.0.2.8:8092`. Set `AN3_GATEWAY_UPSTREAM` only to a reviewed staging
upstream; it is intentionally never defaulted to production.

`Dockerfile.rust-gateway.dockerignore` sends only the Rust gateway source and
its Docker files to the builder; the rest of the AN3 checkout is excluded even
from the image build context.

## Proxy compatibility

All HTTP methods, request bodies, end-to-end headers, query strings, response
status codes, response bodies, redirects, and Range requests are relayed to the
legacy service. RFC hop-by-hop headers (`Connection`, `Transfer-Encoding`,
`Upgrade`, and related fields) and the incoming `Host` are not replayed; the
HTTP client creates the correct upstream connection headers and host. Redirects
are not followed by the gateway.

`GET /health` is always proxied to the legacy `/health` endpoint, never cached,
and returns the upstream status/body unchanged. Successful checks include
`X-AN3-Gateway-Upstream: reachable`; an unreachable legacy service returns a
non-cacheable HTTP 503 with `X-AN3-Gateway-Upstream: unavailable`.

The legacy Python server does not consume `X-Forwarded-For`; therefore this
shadow service is intentionally loopback-only and is not a public traffic
cutover. This release has no supported cutover topology: the cutover helpers
fail closed without changing any listener, systemd unit, or Compose service.
It forwards `X-Forwarded-Host` and `X-Forwarded-Proto` only for ordinary proxy
compatibility and future separately reviewed work; it must never be used for
production.

## Redis cache policy

Redis is strictly best-effort. Any unavailable, malformed, or failed Redis
operation becomes a normal direct proxy request; it cannot make the app
unavailable. Entries are binary-encoded, namespaced by a hash of the configured
upstream and request target, limited to 5 MiB by default, and expire after 60
seconds (configurable only from 1 to 300 seconds). The effective Redis expiry
is also capped to the remaining upstream `s-maxage`/`max-age` freshness, so it
cannot extend the legacy cache contract.

An entry can be read or written only when all of the following are true:

- The request is an anonymous, body-less `GET`, with no `Cookie`,
  `Authorization`, `Proxy-Authorization`, `Range`, `If-Range`, or client
  cache/revalidation directive (`Cache-Control`, `Pragma`, or `If-*`).
- The path is in the narrow public allowlist: `/`, `/game/…`, `/static/…`,
  `/cover/…`, or `/screenshot/…`.
- The upstream response is `200`, explicitly `Cache-Control: public`, has a
  bounded `Content-Length`, a static-page/asset content type, no `Set-Cookie`,
  no `Vary`, and no private/no-store/no-cache directive.

The gateway never caches `/admin…`, `/api/…`, upload/download routes,
`/game-file/…`, `/emulatorjs/…`, `/custom/…`, `/play/…`, `/offline…`, core
preload pages, authentication/account routes, or `/health`. Current Python
HTML pages use `Cache-Control: no-store`, so they continue to bypass Redis;
the practical cache target is the public static/image asset set. This is
intentional privacy and behavior preservation, not a bypass of legacy cache
controls. In particular, the gateway does **not** loosen Python's no-store
HTML/API behavior merely to make Redis busy: assets are retained as the useful
opt-in acceleration layer because they are anonymous, public, and already
marked cacheable by the legacy application. A Redis cache hit records when the
entry was stored and rewrites `Age` as the original upstream age plus elapsed
seconds, so downstream clients retain a correct freshness calculation.

## Configuration

| Variable | Required | Default / bounds |
| --- | --- | --- |
| `AN3_GATEWAY_UPSTREAM` | Yes | Reviewed HTTP(S) legacy staging origin/path; queries/fragments are rejected. |
| `AN3_GATEWAY_BIND` | No | `0.0.0.0:8093` for standalone use; staging Compose fixes it to `127.0.0.1:${AN3_SHADOW_STAGE_PORT:-18093}`. |
| `AN3_GATEWAY_REDIS_URL` | No | Cache disabled gracefully if omitted. Staging Compose fixes it to `redis://127.0.0.1:16379/0`. |
| `AN3_GATEWAY_CACHE_TTL_SECONDS` | No | `60`, bounded `1..300`. |
| `AN3_GATEWAY_CACHE_MAX_BODY_BYTES` | No | `5242880`, bounded `1..8388608`. |
| `AN3_GATEWAY_CONNECT_TIMEOUT_SECONDS` | No | `5`, bounded `1..30`; no total stream timeout is imposed. |
| `AN3_GATEWAY_HEALTH_TIMEOUT_SECONDS` | No | `5`, bounded `1..30`, health only. |
| `AN3_SHADOW_STAGE_PORT` | No | Compose host port `18093`, loopback-only. |

Do not put credentials in this repository, Compose file, reports, command
history, or logs. Staging Redis has no external listener: despite host
networking it is explicitly bound only to `127.0.0.1:16379`.

## Build, test, and staging-only smoke check

From the AN3 repository root:

```bash
docker build -f Dockerfile.rust-gateway -t an3-arcade/rust-gateway-shadow:staging .
docker compose --project-name an3-rust-shadow-staging -f compose.rust-shadow.staging.yml config
docker compose --project-name an3-rust-shadow-staging -f compose.rust-shadow.staging.yml up --build -d
curl --fail --silent --show-error http://127.0.0.1:${AN3_SHADOW_STAGE_PORT:-18093}/health
docker compose --project-name an3-rust-shadow-staging -f compose.rust-shadow.staging.yml ps
```

The image build runs the Rust unit/integration tests. They cover sensitive-route
cache exclusion, anonymous/range/body cache guards, cache response guards,
request body/header relay, Range forwarding, and upstream-backed health.
Its container healthcheck uses `AN3_GATEWAY_HEALTHCHECK_PORT` when supplied;
staging Compose supplies the same loopback port as `AN3_GATEWAY_BIND`.

When the reviewed staging check is finished, stop only the shadow stack if
needed:

```bash
docker compose --project-name an3-rust-shadow-staging -f compose.rust-shadow.staging.yml down
```

Never use `down -v`, do not remove `an3-rust-shadow-staging-redis-data`, and do
not use this Compose file for production deployment. Follow the existing
staging-first release/rollback procedure for any deployment action.
