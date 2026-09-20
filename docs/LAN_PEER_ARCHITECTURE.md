# AN3 direct-LAN peer contract

Installed AN3 applications communicate with each other directly. The AN3
Internet service is not a LAN relay, blob store, rendezvous service, or
controller endpoint. The old `/api/sync/*` and `/api/controller/*` routes are
development/test fixtures only.

## Shared peer layer

The native peer service is `an3-peer`, protocol version `1`, discovered over
local multicast `239.255.43.3:47831`. An advertisement contains only:

```json
{"an3":"peer","service":"an3-peer","v":1,"id":"device-id","name":"short label","port":47832,"capabilities":["controller","sync"]}
```

The datagram contains no email, account identifier, access token, password, or
credential. The receiving socket supplies the source address. A direct session
negotiates the protocol and capability before any feature payload is accepted.
Each listener advertises only the capabilities it currently serves; the checked-in
native listener currently advertises `controller` while the generic peer contract
also reserves `sync` for the account-backed sync adapter.

Sync transports implement the browser-independent interface:

```text
discover() -> public peer advertisements
sameAccount(context) -> true only after a direct authenticated account-scope handshake
manifest(kind)
plan(payload)
publish(payload)
blob(kind, member)
resolve(payload)
close()
```

`sameAccount` is deliberately a transport hook. It uses the existing account
provider's opaque proof/challenge mechanism when an account provider is
available; it is never advertised in multicast and is never implemented by
sending a bearer token through the AN3 server. A peer without a successful
proof is not eligible for sync. This offline build currently has no account
login provider, so a native sync adapter must supply that proof before sync is
enabled.

## Save-set identity and atomicity

Normal saves use one logical save set. Its identity is:

```text
setId = save:<core>:<gameId>:<full-rom-sha256>
```

The manifest contains `core`, `gameId`, `romHash`, `setId`, `memberCount`,
`totalSize`, deterministically sorted `members`, and `manifestHash`. Each
member contains a safe `memberId`, `/data/saves/<memberId>` path, deterministic
key `<setId>:<memberId>`, byte `size`, and SHA-256 `contentHash`. One-file saves
are exactly one-member save sets. Members with different core, game, or ROM
identity cannot share a set. Save states remain `kind=state` artifacts and are
never members of a normal save set.

The receiver rejects duplicate, missing, unexpected, misordered, malformed,
size-mismatched, or hash-mismatched members. It downloads and validates the
complete set before calling the storage adapter. Only then does it atomically
write all members, run `syncfs`, and reload the game save. A `.conflict` set
uses the same identity and preserves the logical set-level conflict choice.

## Controller pairing

Either installed app may host. Starting a session creates a six-decimal-digit
code valid for 120 seconds and one active session. The code is used only in
the direct encrypted handshake; it is cleared after successful pairing and is
not a long-term secret. The session uses ephemeral P-256 ECDH, HKDF-SHA-256,
and AES-256-GCM frames with direction/counter binding. Controller input and
acknowledgements stay on that direct TCP connection.

The current native hosts are implemented in Rust for desktop and Kotlin for
Android. The protocol does not assign a permanent host/controller role to a
platform. Browser-only pages cannot listen on LAN sockets; they expose only an
explicit development adapter and never silently fall back to the AN3 server.
