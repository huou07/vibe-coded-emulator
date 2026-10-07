# Web download path acceptance — 2026-10-08

## Scope

Corrected stale calls to action that sent web visitors to `/offline` as though
it still hosted a browser ROM library. `/offline` is now an offline notice;
local ROM import and gameplay live in the installed app.

## Changes

- The download-page hero now says “Choose your platform” and links to the
  platform cards on the same page.
- The shared Offline control points to app downloads on online pages and uses
  the accessible name “Open app downloads”. The offline notice retains its
  development-only link to the online Games page.
- The empty Games library describes play through the AN3 offline app and links
  to its download page.
- Added regression guard RG-140 in
  `/Users/meomeo/Documents/edit an3tocom apps&web/docs/REGRESSION_GUARDS.md`.

## Local browser evidence

- Runtime: local web app at `http://127.0.0.1:8099`, development environment,
  isolated data directory `/tmp/vce-web-acceptance-data`, controlled through
  `an3ctl`'s Playwright-backed browser.
- `/` rendered the Download app page. Clicking “Choose your platform” changed
  the location to `/#platformTitle`; the platform card links were present.
- `/games` rendered the empty-library state with “Get the offline app”. Its
  shared Offline control was named “Open app downloads”; clicking it returned
  to `/` (the development download page).
- The route `/offline` itself remains the intended offline notice, not a web
  player. No ROM, save, account, staging, or production data was used.
- Staging, packaged apps, responsive widths, and browser console/runtime error
  review were not part of this narrow acceptance and remain **UNVERIFIED**.

## Verification status

The local user-facing navigation flow above is **GOOD**. This is not staging
acceptance and makes no claim about platform package completeness or emulator
gameplay.
