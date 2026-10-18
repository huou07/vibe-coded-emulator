# Feature pages

One page per product feature. An agent reads the page for the feature it is
changing — not the whole documentation set. Each page is deliberately short
(roughly 40–80 lines): status, code map, invariants, how to verify, open work.

## How to use this directory

1. Find the row in the table below that matches the task.
2. Read that page fully. Do not read the other pages "for context"; the shared
   boundaries are in [../ARCHITECTURE.md](../ARCHITECTURE.md).
3. Open only the reference contracts the page names. Long reference documents
   (`docs/REGRESSION_GUARDS.md`, `docs/UI_TESTING.md`) are read when a page or a
   guard index tells you to, not by default.
4. Take status from the page and its tracker, never from a dated summary. When
   the page and the code disagree, the code wins and the page is a bug.

## Pages

| Page | Read when | Status (2026-10-18) |
| --- | --- | --- |
| [web-player](web-player.md) | Changing browser playback, the Web player UI, ROM delivery or the EmulatorJS proxy | GBA/NDS `GOOD` in the browser lane; 3DS not playable (see [web-3ds](web-3ds.md)) |
| [web-3ds](web-3ds.md) | Making Nintendo 3DS playable in the browser | Not playable; an upstream video limitation is recorded (2026-09-15) and must be retested against the repaired runtime |
| [core-selection](core-selection.md) | Touching core choice, capability report, EmulatorJS contract or the core cache | Contract and cache key `GOOD`; selection order enforced by tests |
| [saves](saves.md) | Save states, autosave, 10 quick slots, save storage | Covered paths `GOOD`; packaged native round trip `GOOD`; new-feature saves `UNVERIFIED` |
| [nds-touch](nds-touch.md) | NDS playback, touch bridge, virtual pad, input precedence | `GOOD` in source and browser tests; device touch acceptance `UNVERIFIED` |
| [screen-layout](screen-layout.md) | Layout chooser, per-core screen layout, persisted layout keys | Schema and generators `GOOD`; Linux/Android runtime layout `UNVERIFIED` |
| [lan-sync](lan-sync.md) | Direct LAN save transfer, peer discovery, conflict choice | Source + unit tests `GOOD`; two-real-peer transfer `UNVERIFIED` |
| [phone-controller](phone-controller.md) | Phone-as-controller, pairing, input dispatch, reconnect | Source + staging pair `GOOD`; two-device gameplay acceptance `UNVERIFIED` |
| [switch-eden](switch-eden.md) | Adding or extending the Eden/Switch companion | macOS companion `GOOD` at source level; Linux/Windows/Android companions not built; web out of scope |
| [native-app](native-app.md) | Tauri shell, library/import, player process lifecycle, Exit Game, vendoring, `an3ctl` | Linux DEB builds and launches `GOOD`; Exit Game `BROKEN`; packaged NDS/3DS, audio and visual review `UNVERIFIED` |
| [android](android.md) | Android host, asset mirror, APK builds, AVD/device acceptance | Hosted build lane `GOOD`; device acceptance `UNVERIFIED`; a dedicated AVD is authorized on this host |
| [ui-shell](ui-shell.md) | UI/UX, design tokens, navigation, layout clutter, accessibility | Tokens, 360 px overflow and phone-width touch targets `GOOD` (RG-159); dense desktop controls documented but unmeasured; Linux UI clutter is an owner-reported requirement |

## The page contract

Every page carries these headings, in this order:

- **Read when / Skip when** — the routing decision, stated explicitly.
- **Status** — a short table or list with a date and an evidence word.
- **Code map** — the files a change belongs in.
- **Invariants** — only the ones that page's feature must not break.
- **How to verify** — the commands or journeys that produce real evidence.
- **Open work** — the next discriminating action, linked to its tracker.
- **Related** — reference contracts and trackers, never a second copy of them.

## Status words

This repository uses two evidence words literally, from
[../REGRESSION_GUARDS.md](../REGRESSION_GUARDS.md): `GOOD` means the named live
check is current for the source you are reading, `UNVERIFIED` means the
implementation exists but no live check establishes it. This directory adds
`BROKEN` for a live check that ran and failed. A skip is never `GOOD`; "should
work" is always `UNVERIFIED`.

## Maintenance

- Update the page in the same change that alters its status, and keep the date.
- A feature that closes moves to `docs/archive/` with a one-line reason; do not
  leave a completed page here to rot.
- A new feature starts as a page with an honest `UNVERIFIED` table, not as a
  claim in the README.
- Reference contracts in `docs/` are not duplicated here; link them.
