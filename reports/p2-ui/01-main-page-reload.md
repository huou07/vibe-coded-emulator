# P2.2 — Main-page unsolicited reload

## Finding

`static/site.js` polled `/api/library-version` every 15 seconds on the home page. If its fingerprint changed, it called `location.reload()`, interrupting active browsing, search state, and scroll position.

## Change

The poll remains lightweight but now presents an explicit “Làm mới khi sẵn sàng” control. It records the home query, system filter, and scroll position only when the visitor chooses to reload, then restores them after that intentional refresh.

## Staging evidence

On the isolated staging site, a stage-only game metadata change altered the library fingerprint while the browser was at `scrollY=640`. More than one poll interval later, the browser remained on `/` at the same scroll position and displayed the refresh notice. This also demonstrates that the library-version API was observed fresh by the browser.

## Acceptance status

Passes. The 15-minute active-browsing gate completed on isolated staging with the service remaining active and no error/restart evidence.
