# Design QA — Reference-matched game library

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
