# Batch 02 — shared navigation and homepage

Captured: 2026-08-13 against an isolated eight-game local fixture. The fixture uses the real application fallback cover for every synthetic game; it tests layout density without introducing fabricated production artwork.

## Scope

- Rebuilt the shared header around a compact mobile Offline destination and explicit Menu control.
- Restored all signed-in navigation, including Account/Favorites, inside the mobile menu.
- Reworked the homepage into the selected cover-first artwork deck: compact title, full-width labeled search, system chips, two-column mobile cards, dense desktop shelves, and full-width Play.
- Added meaningful cover-link/image names, semantic filter state, live result count, explicit search Clear, and a recoverable no-results state.
- Eager-loaded only the true leading Recommended image and kept remaining artwork lazy.
- Removed the ambiguous card `i` control; artwork and title remain clear routes to details.
- Repaired the guide dialog: no five-second time limit, initial focus, focus loop, Escape/backdrop close, and trigger-focus restoration.

No player DOM/CSS, NDS touch/input, `player.js`, offline storage, service-worker caching, auth/session, database schema, or deployment behavior changed.

## Verification

- Unit/integration/invariant tests: 6/6 pass, 0.58s real.
- Python binary compile: pass.
- JavaScript syntax: pass for all four frontend scripts.
- Deployment shell syntax and `git diff --check`: pass.
- Browser console warnings/errors on the tested home flow: none.
- Mobile menu: opens, exposes the authenticated Account route, closes with Escape, and restores focus to Menu.
- Search: no-match reports `0 matching games`, reveals Clear and recovery, then restores all eight unique games.
- Guide: opens focused on Close, closes with Escape, and restores focus to How it works.

## Responsive results

| Requested viewport | Drawable client | Document width | Grid | First artwork top |
| --- | ---: | ---: | --- | ---: |
| 1440×900 | 1425px | 1425px | 5 columns | 504px |
| 1280×800 | 1265px | 1265px | 5 columns | 504px |
| 768×1024 | 753px | 753px | 2 columns | 484px |
| 390×844 | 375px | 375px | 2 columns | 414px |
| 360×800 | 345px | 345px | 2 columns | 414px |

The previous page-level mobile overflow is resolved at both required narrow widths. At 390px the first artwork now begins within the first half of the requested viewport.

Interactive border contrast is 3.04:1 against the input surface. Muted text is 8.90:1 and the primary lime is 15.00:1 against the page background.

## Visual comparison

The candidate follows the selected option’s hierarchy: lime brand/action, compact Offline/Menu header, wide search, segmented system filters, artwork-led two-column cards, and minimal surface decoration. Real product covers remain data-owned, so the synthetic fixture intentionally does not reproduce the concept’s fictional game art.

## Evidence

- Responsive full-page: `home-1440.png`, `home-1280.png`, `home-768.png`, `home-390.png`, `home-360.png`
- Viewport: `home-1440-viewport.png`, `home-390-viewport.png`
- States: `home-menu-390.png`, `home-no-results-390.png`, `home-guide-390.png`
