# AN3 Arcade UI inventory

Recorded from repository routing, current staging, and an isolated local fixture on 2026-08-12. All game rows—including Draft and Testing—are intentionally public under the current product rules.

## Primary screens and states

| Route / state | Access | Purpose | Primary action | Desktop issues | Mobile issues | Accessibility / performance | Risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/` populated | Public | Browse the shared game library, Recommended, and systems | Play now | Recommended repeats the same game in its system shelf and leaves large unused grid space when sparse | Header wraps to 178px at 360px; first artwork begins around y=616 in an 800px viewport; page-level horizontal overflow blocks the mobile-first quality gate | Cover-only links have no accessible name; filters do not expose selected state; default cover is 1.10 MB and reused three times on staging; the first visible artwork is still lazy-loaded | High / mobile gate |
| `/` empty | Public | Explain that no shared games exist | Admin uploads a game (copy only) | Empty state is clear but offers no direct recovery action | Reflows without clipping | Strong text contrast; no action link even for an authenticated admin | Low |
| `/` search/filter | Public | Narrow the library client-side | Open or play a matching game | Every rendered card is scanned on each input; filter selection is local only | Filter rail and negative margin contribute to body overflow | Search accessible name is the glyph `⌕`; active filter has no `aria-pressed`; no-match state has no message or reset action | High |
| First-visit / guide modal | Public, non-player pages | Explain Online, Offline, player, and account basics | Close / continue | Large but readable | Fits at 390px but consumes most of the viewport | Focus remains on the background trigger; Escape does not close; no focus trap; automatic first-run version disappears after five seconds | High |
| `/login` idle/loading/error | Public | Authenticate an existing user | Log in | Form is clear and focused | Fits in one viewport | Hidden loading progress is visibly rendered at idle because author CSS overrides `[hidden]`; search-style focus pattern is inconsistent; error paragraph is not an alert | High |
| `/register` idle/loading/error | Public | Create an account and session | Create account | Clear field sequence | Long but usable at 390px | Same always-visible idle progress defect; password requirements are not explained beyond minimum length | High |
| `/account` favorites empty/populated | Authenticated; guest redirects to login | Change nickname and open favorites | Save nickname / play a favorite | Simple, readable in the captured empty state | Empty state reflows, but the signed-in non-admin Account/Favorites header link is hidden at ≤820px | Empty state is understandable; populated favorites were not captured | Medium |
| `/game/:slug` | Public; session unlocks contributions | Understand a game, then play/download/favorite/rate/comment/report | Play now | Sparse capture makes Play look prominent, but populated description and screenshots render before the action group and can push it down | No body overflow in the sparse capture; cover becomes only 105×140px | Guest sees interactive-looking rating stars before the login explanation; populated media/comments were not captured | High evidence gap |
| `/game/:slug` with media/updates/comments | Public / authenticated | Review screenshots, history, community content | Play / contribute | Requires real production-density review | Grid reflows 3→2→1 columns | Comment/report textareas rely on placeholders rather than durable visible labels | Medium |
| `/play/:slug` emulator | Public | Run EmulatorJS and expose essential player controls | Play; fullscreen | Only a 92% loading state was captured; ready/menu/save/error/fullscreen states remain unbaselined | Title disappears; controls are 34×36px; glyphs are terse; portrait/landscape touch states were not captured | High-risk DOM/input surface; no implementation gate may pass without ready NDS/GBA and touch-safe evidence | Critical runtime / P0 evidence gate |
| `/play/:slug` HTML5 | Public | Run a sandboxed custom web game | Play / fullscreen | Separate iframe branch | Same shell constraints | Sandbox, fullscreen/gamepad allowance, and branch-specific control removal are invariants | Critical runtime |
| `/offline` add-ROM form | Public | Store a private ROM locally in the browser | Add to this device | Form is direct | Form stacks cleanly | File detection gives status feedback; HTML5 remains selectable but submission rejects it later | Medium |
| `/offline` core manager | Public | Inspect, preload, re-download, or delete emulator cores | Download core | Twenty-five core cards dominate the page | Core block is 3,212px tall; local games begin around y=3,790 (4.5 viewports) | Disabled Delete controls still look active; initial HTTP/LAN state does not summarize the PWA limitation; inspection work scales with every cached core | High |
| `/offline` local-game library | Public | Browse, play, export, or remove private local ROMs | Play now | Appears after core manager | Buried far below core management | State is backed by actual IndexedDB; icon-only export/remove controls rely on title text | High |
| `/offline?play=…` | Public | Run an IndexedDB ROM in the shared emulator shell | Play / fullscreen | Same protected player | Same protected player | Offline markup must stay synchronized with server player markup; script order `offline.js` then `player.js` is a contract | Critical runtime |
| `/core-preload/:system` | Public internal iframe | Download and verify a core | Automatic | Hidden support state | Hidden support state | Must preserve report-first selection, exact IndexedDB records, byte verification, and postMessage result | Critical runtime |
| `/admin` analytics | Admin; guest redirects; non-admin gets 403 | Monitor visits/plays and top games | Review activity | Three summary stats read clearly | Page overflows horizontally to 400px in a 375px client width; chart labels become tiny | Inline bar heights are blocked by CSP: both `height:4%` and `height:100%` render as 3px, so the chart misrepresents data | High |
| `/admin` batch upload / new game | Admin | Upload or create public test/release games | Upload / Save game | Functional but shares one very long dashboard | Important actions are several screens deep | `site.js` sets upload-progress width through inline styles blocked by normal CSP, so direct and bulk feedback may appear frozen; do not weaken CSP | High |
| `/admin` library table | Admin | Find, play, edit, or delete a game | Edit | Table wrapper supports horizontal scrolling | Dense action text and delete target | Destructive action uses confirmation; route and delete behavior are data-sensitive | High |
| `/admin/game/:id` | Admin | Edit a selected game | Save / Delete | Same dashboard with populated form | Selected form is still embedded in the long page | Missing or nonnumeric IDs silently render New game rather than a not-found state | High |
| `/admin` users / reports / settings | Admin | Create admins, rename users, resolve reports, edit contact links | Save / resolve | Three different jobs share one continuous screen | Very long and difficult to scan | Tables and form labels are mostly semantic; no task-level navigation | Medium |
| Missing `/game/:slug` or `/play/:slug` | Public | Explain that a game was not found | None | Branded but extremely bare | Reflows | No return-to-library or search action | Medium |
| Admin 403 | Authenticated non-admin | Explain forbidden access | None | Bare | Bare | No recovery action | Medium |
| Other unknown GET route | Public | Generic HTTP error | None | Plain text, outside product chrome | Plain text | Inconsistent with branded errors | Low |

## Shared layout and transient states

| Surface | States | Notes |
| --- | --- | --- |
| Header | guest, user, admin, staging, language, Online/Offline destination | Sticky; wraps rather than collapsing on mobile. The green Online/Offline label names the destination page, not live connectivity or offline-readiness. Signed-in non-admin users lose the Account/Favorites link at ≤820px. |
| Footer | maintainer contacts, open-source credits | Useful provenance, but dense at mobile widths and visually competes with empty/error states. |
| Toast | success, error | `role=status` is polite; errors may need assertive announcement when they block a task. |
| Auth | idle, pending, success redirect, inline error | Pending indicator currently leaks into idle state. Successful normal login always redirects to `/`, losing the originating game journey. |
| Upload | idle, progress, error, completion | Admin direct and chunked paths share visual progress bars whose JavaScript width updates conflict with the normal CSP. |
| Player | preparing, ROM/core progress, ready, paused/menu, notice, fatal error, save slots, virtual-pad editor | Screen capture cannot prove accelerated canvas rendering or real NDS finger behavior. |
| Offline | detection, uncertain detection, stored ROM, core missing/downloading/ready/delete, HTTP limitation, PWA-ready | UI may only claim success after storage verification; browser-local data must never imply account/server sync. |

## User-visible resource routes

These are not standalone product screens but affect UI behavior and performance:

- `/download/:slug` — public attachment of the original ROM/archive.
- `/game-file/:slug/*` — public Range-capable player stream; NDS retains original ZIP bytes.
- `/custom/:game_id/*` — sandboxed HTML5 assets.
- `/cover/:game_id` and `/screenshot/:id` — artwork/media, with default-cover fallback.
- `/emulatorjs/(stable|latest)/data/*` — same-origin persistent runtime proxy.
- `/static/*`, `/service-worker.js`, `/health`, `/api/library-version`.

## Discovery limits

- The staging fixture has only one GBA and one NDS game, both using the default cover.
- Production density, artwork diversity, long localized titles, screenshot galleries, and active community content were not used as design-review data.
- Uploaded HTML5 games may contain arbitrary internal screens that cannot be inventoried from the repository.
- EmulatorJS injects third-party runtime menus and dialogs that are not statically enumerable.
- PWA navigation output depends on each browser's installed worker and cache history.
