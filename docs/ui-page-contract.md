# AN3 Arcade page contracts — P2

## Shared shell

`layout()` owns the header, footer, language choice, navigation/menu, staging badge, guide dialog, toast, and versioned site assets. A page may refine its content but must retain the existing IDs and data attributes that `site.js` uses.

## Page-specific rules

| Surface | Required continuity |
| --- | --- |
| Library | `#gameSearch`, `#systemFilters`, `#gameGrid`, `#libraryStatus`, and `#libraryNoResults` continue to drive client-side filtering and the P2 user-controlled update notice. |
| Authentication | Existing form IDs, `next` handling, CSRF requests, error alert, and loading state remain intact. No OAuth or password-reset behavior is implied by the visual reference. |
| Game detail / account | Existing card, favorite, rating, comment, report, and account API hooks remain unchanged. |
| Offline | `offline.js` IDs, browser-local IndexedDB data, core-cache verification, and player-markup/script ordering remain authoritative. UI must not imply server sync. |
| Admin | Existing endpoint forms, confirmation flows, native `<progress>`, and `data-metric-card` hooks remain intact. Metrics continue to be admin-only. |
| Player | The player layering document overrides all visual guidance. No P2 shared-shell rule may affect it. |

## Verification

Each visual batch requires local tests/syntax, `git diff --check`, staging health, 360/390/768/1440 responsive review where applicable, keyboard-visible focus, and an explicit check that the page does not overflow horizontally. Production is only an approval target.
