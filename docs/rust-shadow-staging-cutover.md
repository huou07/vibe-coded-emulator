# Rust shadow staging cutover — disabled in this release

There is no supported Rust gateway cutover in this release. The normal
staging-only topology is intentionally limited to:

| Component | Address | Status |
| --- | --- | --- |
| Existing Python staging | `http://192.168.1.8:8092` | Legacy upstream; unchanged. |
| Rust shadow gateway | `http://127.0.0.1:18093` by default | Loopback-only observer/proxy. |
| Redis | `127.0.0.1:16379` in host networking | Explicit loopback-only isolated cache. |

`cutover-rust-shadow-staging.sh` and
`rollback-rust-shadow-staging-cutover.sh` deliberately exit with status `64`
before making any change. They do not alter a listener, systemd unit, Docker
container, Redis volume, retained release/archive, database, ROM, session, or
backup.

The previous bridge-network idea would have moved Python staging to host
loopback while a Docker bridge container tried to reach it through a host
gateway alias. That topology cannot reliably reach a host-loopback listener,
so it is fail-closed rather than presented as a runnable operation.

A future cutover requires a separately reviewed, staging-only network design
that proves end-to-end reachability, preserves legacy client behavior, has an
immutable image rollback target, and includes an explicit new owner approval.
It must not be improvised by editing the staging environment, systemd, port
bindings, or Compose file. This document never authorizes a production deploy.
