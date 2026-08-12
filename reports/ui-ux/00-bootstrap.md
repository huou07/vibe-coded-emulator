# AN3 Arcade UI/UX bootstrap

Recorded: 2026-08-12 (Asia/Ho_Chi_Minh)

## Scope and authority

- Active repository: `/Users/meomeo/Documents/Codex/2026-08-11/an3-arcade`
- Read-only legacy reference: `/Users/meomeo/Documents/Codex/2026-08-08/v/outputs/an3-arcade`
- Base branch and SHA: `main` at `c6a5273837bea31db5d768315f2c8d1fc18e1234`
- UI branch: `ui/production-ux-refresh`
- Repository had no configured Git remote at bootstrap.
- The working tree was clean before the branch was created. No reset, clean, restore, or production mutation was performed.

The following sources were read completely before UI work:

- `AN3-PRODUCTION-UI-UX-CODEX-PLANNER.md` (499 lines)
- `AN3-ARCADE-FULL-SESSION-HANDOFF-2026-08-09.md` (338 lines)
- `AN3-ARCADE-SESSION-HANDOFF-2026-08-12.md` (131 lines; treated as sensitive and not copied into reports)
- repository `AGENTS.md`
- `.codex/invariants.md`, `.codex/session-state.md`, `.codex/current-phase.md`
- repository handoff `HANDOFF-AN3-ARCADE-2026-08-11.md`

The 2026-08-12 handoff supersedes older player notes. The protected NDS default is geometry-mapped touch with melonDS auto-start; `hybrid-root` remains query-selectable only for rollback diagnostics.

## Protected invariants

UI work must preserve all of the following:

- client-side emulation; the server only stores and serves data;
- NDS to melonDS with `EJS_startOnLoaded = true`;
- geometry-mapped NDS touch, its canvas observer, pointer/mouse dispatch contract, and custom virtual pad;
- the EmulatorJS core IndexedDB contract `EmulatorJS-core` / `core` / `?EJS_KEYS!`;
- report-first core selection and the persistent `an3-arcade-cores-v1` cache;
- NDS original-ZIP delivery, HTTP Range, and chunked upload behavior;
- browser-local offline ROMs and save slots;
- cross-origin isolation for player/offline/preload pages;
- production/staging data and service separation.

Any desired visual change that requires NDS input changes is out of scope and must be recorded as `BLOCKED_FOR_SEPARATE_TOUCH_TASK`.

## Runtime URLs

| Environment | URL | Current evidence |
| --- | --- | --- |
| Production | `https://an3tocom.space` | Read-only `/health` returned `environment=production`, asset `6f8484897b66`. No production design screenshots or writes were made. |
| Staging | `http://192.168.1.11:8092` | Root, library, game detail, auth, and player routes loaded during this audit and served asset `def955887c68`. Baseline screenshots use staging content. |
| Isolated local fixture | `http://127.0.0.1:18793` | Uses ignored data under `work/ui-baseline-data`; used only for empty, auth, account, admin, modal, and error states. |

The source-tree database has no representative games, ROMs, covers, or screenshots. Staging currently contains two smoke-test games, so it is useful for route and responsive evidence but not a complete production-density or artwork-quality review.

## Baseline quality gate

Before any UI source change:

- Python unit/integration suite: **PASS 6/6**
- Python syntax/AST parse: **PASS**
- JavaScript syntax for `site.js`, `player.js`, `offline.js`, and `service-worker.js`: **PASS**
- shell syntax for deployment and backup scripts: **PASS**
- `git diff --check`: **PASS**
- current tracked UI source changes: **none**

The suite strongly protects emulator, core-storage, PWA-cache, NDS ZIP, Range, and debug-gating invariants. It does not cover browser-rendered JavaScript behavior, visual regression, accessibility, or performance timing.

## Frontend baseline

The product uses server-rendered Python f-strings plus global vanilla CSS/JavaScript. There is no framework, bundler, package manifest, component library, Storybook, or design-token package.

| Asset | Raw bytes | Gzip bytes |
| --- | ---: | ---: |
| `static/site.css` | 24,661 | 6,082 |
| `static/site.js` | 19,875 | 5,160 |
| `static/player.js` | 44,625 | 11,670 |
| `static/offline.js` | 26,891 | 8,703 |
| `static/service-worker.js` | 2,755 | 1,006 |
| `static/default-cover.png` | 1,103,173 | n/a |

The tracked `static/` directory totals 1,553,087 bytes. The PWA app shell names eight URLs and contains at least 1,219,607 bytes of local static content before cached HTML; the default cover dominates this cost.

The staging homepage exposed four observable page assets after load: one stylesheet, one script, one image, and the library-version poll. Browser timing APIs were not exposed through the available read-only inspection surface, so LCP, CLS, INP, and a complete request count are intentionally not reported.

## Screenshot baseline

Accepted screenshots live in `reports/ui-ux/baseline/`. The required homepage widths were captured before UI edits:

- 1440: `01-home-staging-1440.png`
- 1280: `01-home-staging-1280.png`
- 768: `01-home-staging-768.png`
- 390: `01-home-staging-390.png`
- 360: `01-home-staging-360.png`

Additional accepted states cover login, registration, game detail, player loading, offline/core state, account/favorites, admin, guide modal, no search results, empty library, and 404.

The in-app browser originally returned JPEG-encoded screenshot bytes; the accepted files were converted losslessly into real PNG containers after capture. Where a vertical browser scrollbar is present, the bitmap's drawable content is 15px narrower than the requested CSS viewport (for example, the requested 390px capture is 375px wide). Candidate comparison must use the same capture method/state or normalize the scrollbar before pixel-level comparison. The two player captures document the loading shell only; a stable ready/canvas state still requires runtime evidence and will be recaptured before any player-shell implementation batch.

## Safety decision

Phase 0 is read-only except for the dedicated branch, reports, ignored screenshot/fixture files, and the isolated localhost session. No production deployment is authorized. UI implementation remains blocked on selection of a reviewed visual direction.
