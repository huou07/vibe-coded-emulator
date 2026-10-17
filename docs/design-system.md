# AN3 Arcade design system — P3

## Intent

The visual language is a compact dark arcade interface: near-black surfaces, a restrained technical grid, pixel-inspired display type, and lime as the one clear primary action. The dashboard reference establishes information density; the login reference establishes a calm focused form; the offline reference establishes cover-first game browsing and fact-based readiness states.

This document is visual guidance, not a behavior specification. Existing routes, controls, APIs, storage, and authorization remain authoritative.

## Tokens

The shared non-player shell is the "quiet violet" theme in
`static/theme-violet.css`, loaded after `static/site.css` on every
`body:not(.player-page)` surface. It rebinds the base token set, so these are the
values a page actually computes (asserted by the browser lane in
`tests/web-runtime.test.mjs`):

| Role | Token | Value |
| --- | --- | --- |
| page | `--ui-bg` | `#07060c` |
| raised surface | `--ui-surface` | `#131020` |
| strong surface | `--ui-surface-strong` | `#191532` |
| control boundary | `--ui-border` | `#282238` |
| primary text | `--ui-text` | `#f3f1fa` |
| supporting text | `--ui-muted` | `#a5a0b6` |
| primary / ready | `--ui-lime` | `#a855f7` |
| information | `--ui-cyan` | `#8b5cf6` |
| warning | `--ui-amber` | `#c4b5fd` |
| danger | `--ui-danger` | `#f87171` |

The in-game player deliberately keeps the base token set from `site.css` (page
`#080b09`, primary `#b7f34a`); gameplay controls, canvases and touch geometry are
outside this design system, and `static/theme-violet.css` scopes every rule to
`body:not(.player-page)` for that reason.

Use the local Pixelify and Roboto Condensed faces already included in the app shell. Pixel type is reserved for the brand and display headings; Roboto Condensed is the readable interface face; monospace is only for compact metadata and technical status.

## Components

- **App shell:** 72px desktop header; compact brand, Offline destination, and explicit menu control on small screens. No header wrapping or loss of account access.
- **Surface:** low-contrast panel with a single readable boundary; no decorative shadow stacks competing with cover art.
- **Action:** two tiers, both asserted by the browser lane and scoped away from the player. **Primary actions** — form submits and `.button` calls to action — are at least 42px tall. **Compact controls** — the system filter chips, table row actions, the admin range selector and the small nav toggle — are deliberately dense at 28–38px; they are a recorded gap against the 42px guidance (`docs/QUALITY.md`), not an approved target. Violet is reserved for Play, submit, and an explicitly selected state. Cyan denotes device/system information, not a competing primary action.
- **Game card:** stable 3:4 artwork, title, system/status metadata, and one unambiguous action. Artwork and title both reach the existing detail route.
- **Status:** uses actual state supplied by the application. Offline destination, network reachability, cached shell/core, and device-local ROM are separate facts.
- **Metric:** a label, value, and status in a bounded card. Unavailable metrics say unavailable; they never display a fabricated zero.

## Responsive contract

| Width | Header | Grid | Gutter |
| --- | --- | --- | --- |
| 360–479px | brand + destination + Menu | two covers | 12px |
| 480–767px | compact expanded menu | two–three covers | 16px |
| 768–1023px | one-row navigation | three–four covers | 24px |
| 1024px+ | full header | four–six covers | 32px |

Every page must avoid document-level horizontal overflow at 360px and 390px. A system-chip rail may scroll inside its own bounded control.

## Protected player boundary

Do not apply general consumer/admin selectors to `.player-page`, `.player-stage`, `#game`, canvas, `#tvPad`, EmulatorJS-injected UI, or touch-control geometry. Any appearance request that requires changing NDS mapping, transforms, layering, hitboxes, or virtual-pad coordinates is `BLOCKED_FOR_SEPARATE_TOUCH_TASK`.

## Route coverage

All actual non-player routes use the shared shell and scoped `body:not(.player-page)` system: library, game detail/community, login/register, account/favorites, offline/readiness, admin dashboard/edit/enrichment/batch views, and 403/404 status states. Admin queue and batch controls use the same bounded surfaces, action hierarchy, focus states, responsive form/grid behavior, and no-horizontal-overflow requirement.

The player remains deliberately excluded. Any player visual or DOM change must first follow `docs/player-layering.md` and is not implied by this route coverage.
