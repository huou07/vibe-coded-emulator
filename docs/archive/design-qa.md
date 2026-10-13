<!--
Status: archival.

This is a design-QA record for a 2026 UI iteration. Its screenshots were
per-run captures that were never committed, its source evidence lived on a
retired workstation, and its target host no longer exists. It is kept only as a
record of what was reviewed and found acceptable then. It carries no current
claim about the product.
-->

# Design QA — Reference-matched game library

> **Historical.** This record cites macOS design-source images
> (`/Users/meomeo/Downloads/...`) and screenshot paths from the 2026-08 work on
> the former macOS host. Those files are not present on the current Debian
> host; the paths are kept unchanged as evidence of what was reviewed.

## Result

**final result: passed**

The homepage/library now matches the selected reference's composition, typography, icon language, card hierarchy, spacing, and responsive behavior closely enough for staging review. No unresolved P0, P1, or P2 design-QA finding remains. Production has not been changed.

## Source and implementation

- Source: `reports/ui-ux/candidates/batch-12-reference-library/reference-source-853x1844.png`, 853 × 1844 pixels.
- Normalized source: `reports/ui-ux/candidates/batch-12-reference-library/reference-normalized-390x844.png`, 390 × 844 pixels.
- Browser-rendered staging implementation: `reports/ui-ux/candidates/batch-12-reference-library/candidate-staging-390x844.png`.
- CSS viewport: 390 × 844; capture: 390 × 844; device scale factor: 1.
- State: Vietnamese, guest, dark theme, real sparse staging data, staging asset `861033db66b8`.
- Staging URL: `http://192.168.1.11:8092/?qa=batch-12-reference-library-4`.

## Full-view evidence

![Normalized reference beside staging](reports/ui-ux/candidates/batch-12-reference-library/reference-vs-candidate-staging-780x844.png)

The real staging fixture has two games, so content density differs honestly from the four fictional recommendation cards and three collection covers in the generated source. The populated local comparison verifies the intended two-row card rhythm without modifying staging data:

![Normalized reference beside populated local candidate](reports/ui-ux/candidates/batch-12-reference-library/reference-vs-candidate-local-780x844.png)

## Focused evidence

![Header, search, and filter comparison](reports/ui-ux/candidates/batch-12-reference-library/focus-header-search-filters-780x200.png)

![Recommendation comparison](reports/ui-ux/candidates/batch-12-reference-library/focus-recommendations-780x560.png)

## Findings and fix history

| Iteration | Finding | Resolution |
| --- | --- | --- |
| Existing staging | P1 visual mismatch: dense multi-line intro, text-like menu treatment, small search field, long horizontally scrolling filters, oversized default cards, and weak artwork/action hierarchy. | Added a library-scoped shell matching the reference's compact header, large search, equal filters, two-column recommendations, shelf collection, and explicit actions. |
| First reference pass | P2 typography/icon mismatch: the system stack and text glyphs did not reproduce the reference's pixel brand and compact game-library language. | Bundled CSP/offline-safe Pixelify Sans, Roboto Condensed Vietnamese subsets, and official local Lucide icons. |
| Responsive pass | P1 implementation gate: narrow layouts needed exact two-column sizing and no page-level overflow. | Tuned 16 px mobile gutters, fixed filter tracks, card min-width behavior, and the horizontal shelf; 360/390/768/1280 widths now match their viewport scroll width. |
| Real staging pass | Sparse content makes the staging page shorter than the illustrative source. | Accepted as a data-state difference; no fake game, cover, genre, or offline state was introduced. |

## Required fidelity surfaces

| Surface | Assessment |
| --- | --- |
| Fonts and typography | Pixelify Sans gives the brand the reference's blocky game identity; Roboto Condensed supplies the compact Vietnamese interface hierarchy. Both are local, licensed, CSP-safe, and offline-cached. |
| Spacing and layout | The header, 44 px search field, equal mobile filters, section headers, two-column recommendation grid, card proportions, and three-item shelf follow the normalized reference closely. |
| Icons | Offline, menu, search, star, gamepad, play, download, and chevrons use locally bundled Lucide SVGs with accessible names where interactive. No emoji or external icon CDN is used. |
| Color and hierarchy | Near-black surfaces, charcoal card bodies, amber offline, lime primary action, cyan collection link, and white headings reproduce the reference's restrained arcade palette. |
| Data truth | Titles, system tags, covers, routes, recommendation ranking, and downloads remain sourced from the current application. Illustrative reference assets were not treated as production content. |

## Functional, responsive, and accessibility checks

- Search for `PMD` and the `NDS` filter each return exactly `pmd-eos` and update the polite live result count.
- The menu opens/closes and synchronizes `aria-expanded`.
- Required widths 360, 390, 768, and 1280 have no horizontal overflow; 1440 also passed locally.
- Search, filter, section, link, and icon-only control names are exposed in the browser semantic snapshot.
- Browser page logs were empty after load and primary interactions.
- The library style scope does not target `.player-page`, `#game`, `.player-stage`, `#tvPad`, or EmulatorJS controls.

## Performance and regression gates

- CSS: 80,410 B raw / 15,543 B gzip; site JS: 24,572 B raw / 6,070 B gzip; service worker: 3,544 B raw / 1,186 B gzip.
- No external runtime font/icon request was added. The new local fonts and icons are included in PWA shell `v20`.
- Runtime request count, LCP, CLS, and INP were unavailable and are not fabricated.
- 12/12 Python regression tests pass. Python, all JavaScript files, deployment/backup shell scripts, and `git diff --check` pass.
- Staging health passes on asset `861033db66b8`; production remains unchanged on `e64eb1cce843`.

## Accepted deviations and remaining gates

- Source art and genre chips are illustrative and are not present in the current database schema.
- Staging has two games; production density must be visually confirmed after approval in the normal release workflow, not by adding staging-only content.
- Physical mobile review is still recommended for font rasterization and touch comfort.
- HTTPS installed-PWA restart/offline verification remains a separate secure-origin gate.
- Production deployment requires explicit user approval.

Full manifest and responsive evidence: `reports/ui-ux/candidates/batch-12-reference-library/README.md`.

Previous gameplay and fullscreen QA remains archived under `reports/ui-ux/candidates/batch-09-player-option1/`, `batch-10-default-nds-layout/`, and `batch-11-fullscreen-toolbar/`.

---

# UI synchronization addendum — 2026-08-23

## Scope and result

**final result: passed**

This addendum verifies the current source candidate locally and on isolated staging. It synchronizes the non-player shell around the supplied Dashboard, Login, and Offline references without inventing their illustrative features or changing application behavior. Staging promotion passed after the owner-provisioned key-only access path became available; production was not touched.

## Comparison evidence

- Visual truth: `/Users/meomeo/Downloads/- generated image #1.png` (Dashboard), `/Users/meomeo/Downloads/- generated image #6.png` (Login), and `/Users/meomeo/Downloads/- generated image #8.png` (Offline/library).
- Browser-rendered candidate: `/Users/meomeo/Documents/Codex/2026-08-23/ss/work/ui-sync-evidence/home-1440x1080.png`, `/Users/meomeo/Documents/Codex/2026-08-23/ss/work/ui-sync-evidence/home-390x843-final.png`, and `/Users/meomeo/Documents/Codex/2026-08-23/ss/work/ui-sync-evidence/offline-1440x1080-final.png`.
- Viewports: 1440 × 1080 desktop and 390 × 843 mobile at device scale factor 1. Browser captures exclude the vertical scrollbar, so scrollable pages render at 1425 × 1069 and 375 × 811 pixels respectively.
- State: guest, Vietnamese unless the URL explicitly selected English, dark theme, local disposable test data. Reference-only cards, hero art, social sign-in, and fabricated readiness states were deliberately not copied into the product.

The supplied reference and the final browser captures were opened together for visual comparison. The check focused on the shared visual language rather than attempting to claim identical information architecture where that would require a new feature.

## Findings and fixes

| Priority | Finding | Fix |
| --- | --- | --- |
| P1 | The library shell used a distinct 84 px header, a denser font stack, and a horizontal desktop collection shelf that made the page feel unrelated to the Login, Offline, and Admin surfaces. | Unified the 72 px desktop / 60 px mobile header rhythm, Roboto Condensed interface face, shared radii, 44 px controls, and the desktop collection grid. |
| P2 | The mobile collection exposed three narrow, clipped cards despite the two-cover mobile contract. | Switched the collection to two mobile columns; tablet uses three columns and full navigation; desktop uses four columns. |
| P2 | Offline utility controls did not share the desktop composition of the device-library reference. | Used a safe CSS-only two-column desktop shell: local games remain left while the existing private-ROM and core-manager controls form a right utility rail. It collapses to the original single-column flow below 981 px. |
| P3 | Login did not share the same panel boundary token as the rest of the arcade shell. | Applied the restrained lime-tinted boundary used by primary-ready surfaces; no login behavior or extra provider UI was added. |

## Required fidelity surfaces

| Surface | Assessment |
| --- | --- |
| Fonts and typography | Local Pixelify Sans remains reserved for the brand/display treatment; local Roboto Condensed is the common readable UI face. Vietnamese and English both rendered without browser errors. |
| Spacing and layout | Page gutters, 72/60 px header rhythm, 44 px controls, shared 8/12/16 px radii, and 2/3/4 cover grids now follow the same responsive scale. |
| Colors and tokens | Near-black, lime primary, cyan information, amber mode, and low-contrast boundaries continue to use the AN3 token set rather than a generic dashboard palette. |
| Image quality and assets | Existing cover art and bundled icon assets remain untouched. The supplied reference imagery is not used as site content, so no screenshot crop, placeholder, or fabricated visual asset was introduced. |
| Copy and content | Existing Vietnamese/English copy, device facts, game data, and authentication fields remain authoritative. No generated reference-only CTA, OAuth, sync, or status claim appears in the app. |

## Final local smoke evidence

- Public home, offline, login, register, game detail, 404, and Vietnamese/English variants were checked at 390, 768, and 1440 CSS-pixel widths.
- Every checked route had `scrollWidth <= innerWidth`; the 390 px menu remains a functioning disclosure, while 768 px shows the one-row navigation and three cover columns.
- Search reset/no-result state and the Offline core-manager disclosure remain functional; browser console errors were empty.
- The protected player selectors and player JavaScript were not changed.

## Staging release and visual verification

- Key-only preflight passed with strict host-key checking; no SSH password was used.
- Isolated staging release passed its health check with asset `8287c607602d`. Its rollback target remains `/opt/an3-arcade-staging/releases/20260823-154343-46a5125abb00`.
- Direct staging inspection loaded `/static/site.css?v=8287c607602d` on the public library, Offline library, and an already-authenticated Admin dashboard. No browser console errors were reported.
- The public library at a 1280 px browser viewport has a 72 px header, four cover columns, no horizontal overflow, and the expected static navigation. Offline renders its two-column desktop composition without horizontal overflow. The authenticated dashboard in the user browser uses Pixelify Sans for its display title and a 72 px header.
- The release's `app.py` and `static/site.js` SHA-256 values match the locally tested candidate; the deployed `static/site.css` is the exact file used for the checked 390/768/1440 local responsive captures. Those captures passed the no-overflow, 2/3/4-column, and mobile-menu checks recorded above.
- Production changed: **no**.

---

# Fidelity correction — 2026-08-23 (supersedes the synchronization addendum above)

## Result

**final result: passed for staging review**

The non-player UI was rebuilt against the three supplied reference frames after the first synchronization pass was judged too generic. The current staging asset is `586710e73b8e`; production remains untouched.

## Source / state / review evidence

- Dashboard source: `/Users/meomeo/Downloads/- generated image #1.png` (1448 × 1086).
- Sign-in source: `/Users/meomeo/Downloads/- generated image #6.png` (941 × 1706).
- Offline source: `/Users/meomeo/Downloads/- generated image #8.png` (1440 × 1080).
- Reviewed staging routes: `/admin` while authenticated as the existing staging administrator, `/offline`, and `/login`; Vietnamese state was checked for every route.
- The source frames and fresh in-app-browser screenshots were visually compared in the same review session. No reference screenshot was copied into the product UI.

## Corrections verified

| Surface | Verified implementation |
| --- | --- |
| Vietnamese display font | Added the local `AN3 Pixel` face from complete Vietnamese Pixelify Sans font files. Accented strings such as `Kho ngoại tuyến`, `Tổng quan`, `Khách riêng biệt`, `Thêm hoặc sửa game`, and `Chào mừng trở lại!` render as glyphs rather than fallback or broken characters. |
| Header and dashboard | Uses the reference’s compact black header, lime pixel brand, cyan admin eyebrow, uppercase pixel `DASHBOARD`, thin lime task tabs, dark-green metric cards, and dense two-panel analytics / monitoring rhythm. Application analytics remain truthful; fabricated line series or game counts were not introduced. |
| Sign-in | Uses the source’s centered gamepad marker, large welcome message outside the lime-outlined form, wide rounded fields, and lime primary action. The 941 px reference breakpoint switches to the two-line mobile brand / mode / menu header rather than compressing desktop navigation. |
| Offline | Uses a purpose-generated, no-text pixel-art hero (cabinet left; player, slime, and temple right), plus the reference’s short wide hero, lime readiness strip, dark local-library panel, and violet private-ROM utility rail. Existing device-local behavior is unchanged. |

## QA and release gates

- `python3 -m unittest discover -s tests`: **22/22 passed**.
- `python3 -m py_compile app.py`, `node --check static/site.js`, `bash -n deploy-stage.sh`, and `git diff --check`: passed.
- Key-only staging preflight passed with strict known-host validation. Staging health reported asset `586710e73b8e` after release.
- Verified staging returns the new Vietnamese Pixelify font files and generated hero with HTTP 200; the authenticated dashboard, public Offline page, and public sign-in page rendered without visible font corruption.
- Player selectors, player JavaScript, game data, login behavior, offline storage behavior, and production were not changed.

## Deliberate data differences

The references contain illustrative metrics, chart lines, ROM covers, social providers, and status claims. Those were not added or falsified: the release keeps real staging analytics, existing authentication inputs, real local-ROM handling, and the current game inventory while matching the source’s visual language and geometry.

---

# Exact-reference presentation — 2026-08-23 (supersedes prior fidelity notes)

## Result

**final result: passed**

The current staging presentation follows the supplied Dashboard, Login, and Offline frames as the authoritative visual source. This pass intentionally uses their layout, Vietnamese copy, pixel-display typography, icon language, chart treatment, spacing, borders, and static reference values on the non-player surfaces. It adds no Google or Discord authentication capability, and it does not alter player, backend, database, or PWA behavior.

## Source / comparison evidence

- Dashboard reference: `/Users/meomeo/Downloads/- generated image #1.png` (1448 × 1086).
- Login reference: `/Users/meomeo/Downloads/- generated image #6.png` (941 × 1706).
- Offline reference: `/Users/meomeo/Downloads/- generated image #8.png` (1440 × 1080).
- The three source frames were reopened for the review. Fresh browser-rendered staging screenshots were emitted in the same in-app-browser review session for `/admin`, `/login`, and `/offline`.
- Mobile comparison state: 930 × 1321 CSS pixels on staging against the 941 × 1706 login source. Final key positions were heading `y=261`, first input `y=551`, second input `y=718`, CTA `y=902`, social visual controls `y=1079`, and panel `y=458–1215`; each is within a few pixels of the matching source geometry.
- Desktop comparison state: the authenticated `/offline` view was checked at 1280 px with no horizontal overflow; the dashboard was checked in the user’s 930 px side-panel state with its reference metric layout, two canvas charts, target top-game list, and no duplicate runtime list.

## Implementation and boundaries

- `app.py` changes are presentation-only render changes for shared non-player shell, Login/Register, Offline, Admin dashboard, and the static reference cards. Existing endpoints, auth submission fields, APIs, admin operations, database calls, and ROM/core handlers remain in place.
- `static/site.css` supplies the scoped reference layout. `static/reference-charts.js` draws the two displayed dashboard line charts only; it does not fetch, persist, or modify data.
- The dashboard reference totals and line series are rendered presentation data, not written to staging data or the database.
- Google and Discord marks are on `disabled type="button"` visual controls only. They have no event handlers, routes, OAuth configuration, or account-provider implementation.
- Local complete Vietnamese Pixelify Sans files are used for the block display face, so accents such as `Chào mừng trở lại!`, `Khách riêng biệt`, and `Kho ngoại tuyến` render without fallback corruption.
- The no-text pixel offline hero is the purpose-generated local asset `static/offline-hero-pixel-v2.png`; reference screenshots were not cropped or embedded as product assets.

## Final gates

- Final staging asset: `de179e094a4f`, release `/opt/an3-arcade-staging/releases/20260823-191334-de179e094a4f`.
- Direct staging checks: font status `loaded`, all inspected images loaded, no horizontal overflow on `/`, `/account`, `/status`, `/login`, `/register`, `/offline`, `/admin`, and `/game/pokemon-emerald`; all were explicitly confirmed outside the player surface.
- `/admin` rendered two canvas charts and zero visible duplicate runtime top-game lists. `/offline` rendered zero visible duplicate runtime fact values. `/login` rendered two disabled provider visuals and no provider behavior.
- `python3 -m unittest discover -s tests -v`: **22/22 passed**. `py_compile`, both JavaScript syntax checks, and `git diff --check` also passed after the final presentation CSS adjustment.
- Protected hashes after the final check: `static/player.js` `f9e55c92dbc49e0668b4601159c3c55ff321ed651c934305a00132762ee0d8e6`; `static/service-worker.js` `7b3904fceac056775d38cf48d4cc2bf0ac9ca3df254fc8b52a7324a6370cabb8`.
- `PLAYER_INTERNALS_CHANGED=NO`; `BACKEND_CHANGED=NO`; `DB_SCHEMA_CHANGED=NO`; `PWA_LOGIC_CHANGED=NO`; production changed: **no**.
