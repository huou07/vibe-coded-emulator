# P2.1b validation

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Passed

| Check | Evidence |
| --- | --- |
| Service / LAN URL | service active; a separate LAN client reached `http://192.168.1.8:8092/health` with HTTP 200 |
| Asset | health reports `9cf7de4b8d0b`; static `site.js` returns HTTP 200 |
| Data isolation | staging DB integrity `ok`; 12 games, 2 ROM rows, 10 fixtures, 0 users, 0 sessions |
| Public pages | home, login, offline return HTTP 200; guest `/admin` redirects to login |
| Admin API boundary | guest metrics route returns HTTP 401 with `Cache-Control: no-store` |
| Responsive library | 360, 390, 768, 1280, and 1440px render 12 cards without horizontal overflow; empty search state renders |
| GBA smoke | Pokémon Emerald reaches an EmulatorJS canvas; a desktop-keyboard smoke event was sent without browser warnings |
| NDS smoke | Explorers of Sky reaches `ejs_canvas`, `data-an3-nds-touch=1`, `pointer-events:auto`, and `touch-action:none`; no browser warnings |
| Local gate | 21 tests pass; Python, JavaScript, and staging-shell syntax checks plus `git diff --check` pass |
| Production boundary | production service remains active and reports unchanged asset `ef1c8a3df6b8` |

The local monitoring tests also verify the no-unsolicited-reload source
contract, safe API cache bypass, temperature selection, and unavailable-power
rendering contract.

## Still required for full acceptance

- Create/use a staging-only admin account, then observe ten consecutive
  authenticated dashboard metric samples. Confirm live temperature and the
  real/unavailable power state.
- Exercise NDS direct touch, fullscreen, and save-state behavior on an actual
  touch device. Browser automation confirmed the touch-ready surface but is
  not a physical-touch acceptance test.
- Exercise a real staging-only authenticated favorite state and the admin
  dashboard/table flow after that account exists.

These open manual checks do not authorize production deployment. Production
remains unmodified.
