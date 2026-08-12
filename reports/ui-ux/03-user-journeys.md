# AN3 Arcade priority user journeys

The ordering favors the most common route to play while treating player and offline correctness as higher-risk gates than their visual scope suggests. Homepage browse and search/filter are one user outcome even though they remain separate implementation batches.

## Decision order

1. Browse/find (`J1` + `J2`) → detail → Play.
2. Mobile player start (`J3`) → NDS touch/controls → save/fullscreen regression gate.
3. Prepare offline (`J4`) → verify app shell/core/local ROM → disconnect/restart → Play.
4. Admin add/find/edit/upload (`J6`) because it supplies the library and progress feedback is currently unreliable under CSP.
5. Login (`J5`) → return to intended game → favorite/rate/comment.
6. Account, secondary settings, and recovery-state polish.

## J1 — Homepage → game → play

Priority: **1 — highest user value**

Current friction:

- mobile header and intro push first artwork to roughly 77% of a 360×800 viewport;
- Recommended duplicates games already shown by system and can become mostly empty space;
- identical fallback covers reduce scanability on staging;
- cards expose an ambiguous `i` action and an unnamed cover link.
- the sparse detail fixture makes the CTA hierarchy look healthier than a populated page, where description/media render before actions.

Desired behavior:

- artwork and Play appear in the first mobile viewport;
- featured content is compact and does not duplicate awkwardly;
- title, system, status, and Play are scannable with a clear focus state;
- detail remains available without competing with Play.

Screens: home populated, card focus/hover, game detail, player loading/ready.

Success criteria:

- no body horizontal overflow at 360, 390, 768, 1280, or 1440;
- first useful cover is visible by approximately the first half of a 390×844 viewport;
- Play is reachable by keyboard and has a clear accessible name;
- missing/broken covers keep layout and meaningful naming;
- navigation to player does not change runtime configuration.

Risk: consumer UI medium; player transition critical.

## J2 — Search/filter → game → play

Priority: **1 — same browse/find outcome as J1**

Current friction:

- search accessible name is a glyph;
- active system is visual only and query/filter state is not represented in the URL;
- no-match hides all content without explanation or reset;
- every card is rescanned on each keystroke as an implementation observation; no input lag has been measured at the expected ~29-game scale.

Desired behavior:

- prominent labeled search with explicit Clear;
- semantic system chips and visible result count;
- useful no-result state that preserves query and offers reset;
- query/filter URL state only if it can be added without changing data behavior.

Screens: home search idle, active query, active system filter, no results, game detail, player.

Success criteria:

- search has a localized accessible name and visible focus;
- filter state exposes `aria-pressed` or an equivalent selected state;
- results/no-results are announced without a page reload;
- clearing restores all sections and Recommended rules correctly;
- input remains responsive at the expected production library size.

Risk: low runtime risk; medium regression risk because Recommended and system sections share duplicated cards.

## J3 — Mobile → player → controls

Priority: **2 — mandatory regression gate**

Current friction:

- seven compact glyph buttons are 34×36px and the title is hidden;
- icon meanings depend on title/tooltips that are weak on touch;
- loading presentation is utilitarian.

Desired behavior:

- a calm, legible toolbar with the same controls and DOM hooks;
- critical actions remain reachable without covering the stage;
- loading, notice, slots, and virtual-pad panels share the visual system;
- no new overlay enters the NDS touchscreen path.

Screens: player loading, ready, EmulatorJS menu, fullscreen, save slots, pad settings, notice/error, portrait/landscape.

Success criteria:

- melonDS starts automatically and reports game start;
- first tap, mapped drag in all directions, hold/release, fullscreen, virtual pad, and save state pass on staging;
- `.player-stage`, `#game`, canvas geometry, pointer rules, and overlay stack remain unchanged;
- toolbar fits 360/390 without body overflow or stage obstruction;
- physical Android validation is requested only after the candidate passes automated/staging gates.

Risk: **critical**. If visual requirements need input changes, record `BLOCKED_FOR_SEPARATE_TOUCH_TASK`.

## J4 — Offline → verified core/ROM → play

Priority: **3 — differentiated product capability**

Current friction:

- local games sit after a 25-core wall, beginning more than four mobile viewports down;
- disabled Delete buttons look active;
- the initial screen does not summarize HTTP LAN versus HTTPS/PWA capability;
- HTML5 can be selected before submission rejects it.
- destination (“Online/Offline”), local ROM, cached core, cached app shell, network reachability, and secure context are not yet presented as separate facts.

Desired behavior:

- local games and Add ROM are primary;
- a concise readiness area explains device-local storage and current browser capability;
- relevant system core state sits with the game or in a compact manager;
- advanced all-core management is expandable;
- stored, downloading, ready, unavailable, and limited states are visually distinct and factually proven.

Screens: empty local library, populated library, ROM detection, core missing/downloading/ready/delete, HTTP limitation, offline player, fatal unavailable.

Success criteria:

- local games appear in the first one to two mobile viewports;
- no UI claims full offline readiness without verified IndexedDB/cache and secure-context capability;
- downloading a server ROM is never presented as proof that it is stored in the device-local offline library;
- ROM stays browser-local and never uploads;
- exact EmulatorJS core records, report-first selection, persistent cache, script order, and offline player markup contract pass regression tests;
- installed PWA survives real network loss and restart in manual staging QA.

Risk: critical storage/PWA behavior; visual restructuring can be medium risk if IDs and event wiring remain stable.

## J5 — Login → favorite/rating/comment

Priority: **5 — account value and community**

Current friction:

- auth progress appears while idle;
- password help/error association is minimal;
- guest rating controls look actionable before the sign-in explanation;
- contribution textareas lack persistent visible labels.
- successful normal login returns to `/`, losing the originating favorite/rating/comment task;
- signed-in non-admin users have no Account/Favorites header route at ≤820px.

Desired behavior:

- calm auth states with clear pending, success, error, and retry feedback;
- game detail explains the benefit of sign-in before contribution controls;
- favorite, rating, comment, and report results are announced and visually stable;
- account favorites reuse the same card system.

Screens: login/register, auth pending/error, game guest/authenticated, favorite toggled, rating selected, comment/report submission, account favorites.

Success criteria:

- no progress UI at idle;
- errors are announced and tied to relevant inputs;
- login redirects retain the intended product journey where architecture safely permits;
- contribution controls work by keyboard and expose selected/pressed state;
- CSRF, rate limits, session cookies, and auth behavior do not change.

Risk: medium; authentication behavior is explicitly out of scope for refactor.

## J6 — Admin → find/edit/manage game

Priority: **4 — library-supply and operational integrity**

Current friction:

- analytics, uploads, editor, library, users, reports, and settings form one very long page;
- mobile page overflows and the chart is false under CSP;
- direct and bulk upload bars also set inline widths, so progress feedback may appear frozen under the same normal CSP;
- edit context is not strongly separated from New game;
- missing edit IDs silently show the create state.

Desired behavior:

- task navigation separates Overview, Library, Add/Edit, Reports, Accounts, and Settings without changing endpoints unnecessarily;
- working textual analytics remain useful even if the visual chart fails;
- library search/filter and edit state are obvious;
- upload progress/errors remain visible during long files.

Screens: overview, library empty/populated, add game, edit game, chunked upload, users, reports, settings, 403/not found.

Success criteria:

- no page-level horizontal overflow at 360/390;
- chart values and upload progress accurately represent state under the existing CSP without weakening `style-src`;
- common edit action is reachable without scanning the entire dashboard;
- destructive actions remain explicit and confirmed;
- production/staging paths, upload behavior, and database/file relationships do not change.

Risk: high data-management impact despite mostly presentational scope.

## Shared measurement gates

Each implementation batch must run syntax/tests, capture 1440/768/390/360 candidates, compare against the matching baseline, check keyboard/focus and contrast, and make one logical commit. Performance reporting must distinguish measured values from unavailable values. All final visual review happens on staging; production remains approval-only.
