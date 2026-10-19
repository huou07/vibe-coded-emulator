# AN3 Arcade design system — P3

## Intent

The visual language is a compact dark arcade interface: near-black surfaces, a restrained technical grid, pixel-inspired display type, and lime as the one clear primary action. The dashboard reference establishes information density; the login reference establishes a calm focused form; the offline reference establishes cover-first game browsing and fact-based readiness states.

This document is visual guidance, not a behavior specification. Existing routes, controls, APIs, storage, and authorization remain authoritative.

## Tokens

| Role | Value |
| --- | --- |
| page | `#080b09` |
| raised surface | `#121714` |
| strong surface | `#171d19` |
| control boundary | `#56635a` |
| primary text | `#f3f5ef` |
| supporting text | `#a8b0aa` |
| primary / ready | `#b7f34a` |
| information | `#66d9ff` |
| warning | `#f5c451` |
| danger | `#ff7474` |

Use the local Pixelify and Roboto Condensed faces already included in the app shell. Pixel type is reserved for the brand and display headings; Roboto Condensed is the readable interface face; monospace is only for compact metadata and technical status.

## Components

- **App shell:** 72px desktop header; compact brand, Offline destination, and explicit menu control on small screens. No header wrapping or loss of account access.
- **Surface:** low-contrast panel with a single readable boundary; no decorative shadow stacks competing with cover art.
- **Action:** 42px minimum control height. Lime is reserved for Play, submit, and an explicitly selected state. Cyan denotes device/system information, not a competing primary action.
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
