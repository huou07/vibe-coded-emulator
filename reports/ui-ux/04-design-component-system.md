# AN3 Arcade lightweight design and component system

Recorded: 2026-08-13

Selected direction: the first displayed Product Design concept — a cover-first, two-column mobile artwork deck with a compact header, full-width search, simple system filters, and restrained lime/cyan accents.

## Translation principles

- Game artwork is the dominant visual layer. The application continues to render the real cover associated with each game; concept artwork is not production content.
- The mobile browse view uses two useful columns at 360–390px, then scales to denser shelves on tablet and desktop without introducing a marketing hero.
- Play remains the clearest action. Details remain available through the artwork/title, not a competing ambiguous icon.
- Dark surfaces use spacing and subtle tonal separation before borders or shadows.
- Lime communicates the primary action and active selection; cyan identifies system/device information; amber/red remain warning/destructive colors.
- System/native fonts and same-origin assets only. No CDN font or icon dependency is introduced, preserving CSP and offline behavior.
- Motion is optional and short; every animation and transition must stop under `prefers-reduced-motion: reduce`.

## Scoped tokens

The new tokens live on `body:not(.player-page)` so they cannot change EmulatorJS-injected UI, `.player-stage`, `#game`, canvas, or `#tvPad`.

| Role | Token | Value / rule |
| --- | --- | --- |
| Page | `--ui-bg` | `#080b09` |
| Raised surface | `--ui-surface` | `#121714` |
| Strong surface | `--ui-surface-strong` | `#171d19` |
| Border | `--ui-border` | `#445047` (at least 3:1 for interactive boundaries after verification) |
| Text | `--ui-text` | `#f3f5ef` |
| Muted text | `--ui-muted` | `#a8b0aa` |
| Primary | `--ui-lime` | `#b7f34a` |
| Information | `--ui-cyan` | `#66d9ff` |
| Warning | `--ui-amber` | `#f5c451` |
| Danger | `--ui-danger` | `#ff7474` |
| Consumer font | `--ui-sans` | system UI sans stack |
| Technical font | `--ui-mono` | system monospace stack |
| Radius | `--ui-radius-sm/md/lg` | `6px / 10px / 14px` |
| Spacing | `--ui-space-*` | 4, 8, 12, 16, 24, 32, 48px |
| Content width | `--ui-page-max` | `1280px` |

## Type hierarchy

- Brand: bold system sans, compact tracking; it stays the reliable Home link.
- Page title: 30–40px desktop, 26–32px mobile; reserved for one screen title.
- Shelf title: 18–24px, semibold.
- Card title: 15–18px, semibold, at most two lines.
- Body/control text: 14–16px.
- System, state, file size, count, and technical metadata: 11–13px monospace.

## Shared components

### App header

- Desktop: brand, primary destinations, account/auth, language.
- Mobile: brand plus Offline destination and an explicit text Menu control; opening the menu must retain Account/Favorites for signed-in non-admin users.
- “Online/Offline” is phrased as a destination. It must never imply live connectivity or verified offline readiness.

### Search and system filters

- Search has a durable visible label and a native search input with a strong focus ring.
- Clear is explicit when a query is present.
- Filters are native buttons with `aria-pressed`; the count is supporting metadata.
- The rail may scroll internally if necessary, but the page itself must not overflow at 360/390px.
- Result count/no-result feedback is announced through a live status region.

### Game card

- One semantic article with 3:4 art, title, system/status metadata, rating, and Play.
- Artwork link has a meaningful accessible name; title is the second clear route to details.
- Card actions never depend on glyph-only controls.
- Existing `.game-card`, `.cover`, `.game-card-body`, `.card-actions`, and data hooks remain stable across Home and Account. Offline card hooks remain stable in `offline.js` until its dedicated batch.

### Button and input

- Minimum 40px consumer control height; 44px where space permits.
- Primary lime fill, secondary dark surface, danger outline/text.
- Focus uses a visible 2px lime/cyan outline with offset; it is not removed.
- Disabled states change contrast and cursor while retaining native semantics.

### Empty, loading, status, and error

- Every state explains what happened and offers one sensible recovery action.
- Loading/progress uses native `<progress>` where practical under CSP, with adjacent text status.
- Connectivity, app-shell cache, emulator core cache, and local ROM are represented as separate facts.

## Responsive layout

| Width | Header | Browse grid | Page gutter |
| --- | --- | --- | --- |
| 360–479 | compact brand/destination/menu; menu expands below | two columns | 12px |
| 480–767 | compact header; expanded search | two to three columns by available width | 16px |
| 768–1023 | desktop-like header with wrapping prohibited | three to four columns | 24px |
| 1024+ | single-row header | four to six columns within max width | 32px |

## Protected player boundary

The design layer must not alter the player grid rows, stage/canvas geometry, transforms, pointer rules, z-index ordering, virtual-control dimensions, coordinates, or hitboxes. Generic element selectors are scoped away from `.player-page`. Any visual requirement that needs NDS input changes is `BLOCKED_FOR_SEPARATE_TOUCH_TASK`.

## Component verification contract

Each implementation batch must:

1. run unit/invariant tests and syntax checks;
2. capture candidate views at 1440, 1280, 768, 390, and 360 where the surface applies;
3. compare the same viewport/state to the baseline or selected concept;
4. check mobile page overflow, keyboard focus, labels, semantic state, and contrast;
5. preserve a small logical commit;
6. avoid production deployment.
