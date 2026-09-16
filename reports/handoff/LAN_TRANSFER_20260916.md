# LAN save/state transfer — two-device verification (2026-09-16)

Implements byte transfer on top of the existing LAN discovery + sync-mode work.
The staging app server is the **LAN rendezvous**; bytes are hash-verified,
in-memory, TTL-bound, and never persisted. Everything stays on the LAN.

## API

- `POST /api/sync/lan/publish` — `{deviceId, kind, items:[{key, contentHash, data(base64)}]}`.
  Only `sync_engine`-eligible kinds (rom/save/state/metadata/settings) are
  accepted; `firmware`/`keys` are rejected. Each item's SHA-256 prefix must match
  `contentHash`, items are capped at 16 MiB, and the list at 512 entries.
- `GET /api/sync/lan/manifest?kind=` — `{kind, items:[{key, contentHash, size, deviceId, ageSeconds}]}`.
- `GET /api/sync/lan/blob?kind=&key=&hash=` — `application/octet-stream`, only
  when the stored hash matches, else 404.
- All are `SYNC_ENABLED`-gated (staging/development); blobs expire after 900 s and
  are reaped on every LAN request. Production returns 404.

## Two-device verification (VERIFIED)

MacBook publishes → Debian pulls:

```
Mac   POST /api/sync/lan/publish  → stored 1 (sha256 d610c3a8…, 1041 B)
Debian GET /api/sync/lan/manifest?kind=state → deviceId macbook-device01
Debian GET /api/sync/lan/blob?…&hash=d610c3a8… → 200, 1041 B
Debian sha256 → d610c3a8b50b02edadf8b1ef44cb3a282ceb9fe462ac3e36eb5cdd62d3192485  (matches)
```

Debian publishes → MacBook pulls:

```
Debian POST /api/sync/lan/publish → stored 1 (sha256 ea48442b…, 780 B)
Mac    GET  /api/sync/lan/manifest?kind=save → deviceId debian-device01
Mac    GET  /api/sync/lan/blob?…&hash=ea48442b… → 200, 780 B
Mac    sha256 → ea48442b2ea2b0d8ed61c7b08deb299e5506cd461a941d8a94ecbefd07200f8a  (matches)
```

Both devices are on the same LAN; the MacBook is `192.168.1.6`, the Debian
staging host `192.168.1.8`. Deployed asset `e792e8578089`, release
`/opt/an3-arcade-staging/releases/20260916-180157-e792e8578089`.

## Tests

Suite **264 tests, 0 failures**; 5 new `tests/test_sync_api.py` cases:
publish/manifest/download round-trip, exact-hash requirement, ineligible
kinds + bad hashes, oversize items, production 404.

## UNVERIFIED / not done

- **True peer-to-peer** transfer (a device serving bytes directly from its own
  LAN listener). This is LAN-mediated through the staging app server; the
  registry already exposes same-subnet peer addresses for a future direct mode.
- Client wiring: the `/sync` page and the native shells do not yet read their
  local save stores and call publish/pull; the API is verified with the two
  devices via HTTP.
