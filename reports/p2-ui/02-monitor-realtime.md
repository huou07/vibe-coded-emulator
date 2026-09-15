# P2.3 — Realtime monitor

## Finding

The service worker used cache-first handling for every same-origin GET, including `/api/` requests. Therefore `fetch(..., {cache: "no-store"})` in the admin monitor could still receive a cached response from Cache Storage.

## Change

The service worker now passes `/api/` and `/admin/api/` requests straight to the network with `cache: "no-store"`. The monitor now has a visibility-aware scheduler, one in-flight request, an abort timeout, bounded backoff, and freshness/error presentation rather than overlapping fixed-interval polls.

## Staging evidence

Ten authenticated service-account samples, seven seconds apart, advanced `updated_at` on every request. CPU, RAM, uptime, temperature, and application status varied as expected. The endpoint returns `Cache-Control: no-store`; unauthenticated monitoring requests correctly return 401.

## Acceptance status

Passes. An existing signed-in staging browser session confirmed fresh values and correct status rendering. It also exposed and led to a correction for JavaScript’s `Number(null) === 0` coercion: unavailable power now displays as unavailable, never as `0.00 W`. No credentials were entered into the browser.
