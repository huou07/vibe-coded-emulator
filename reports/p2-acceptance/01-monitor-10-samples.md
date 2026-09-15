# P2.15 realtime monitor evidence

Date: 2026-08-23 (Asia/Ho_Chi_Minh)

## Authorization boundary

Two temporary identities were created only in the isolated staging database through the application bootstrap/register flows. Their credentials are retained only in private task-local temporary files and are not present in this report, Git, or the handoff.

| Request context | Expected | Observed |
| --- | --- | --- |
| Guest metrics request | 401 | 401 |
| Normal staging user metrics request | 403 | 403 |
| Staging administrator metrics request | 200 | 200 |
| Administrator response cache policy | `no-store` | `Cache-Control: no-store` |

## Ten consecutive live samples

The dashboard implementation currently schedules successful polls at a seven-second cadence. Ten authenticated requests were made to the staging endpoint at that cadence with cache-busting query values. Every request reached the backend, returned HTTP 200 and `Cache-Control: no-store`, and had a distinct `updated_at` value.

| Sample | `updated_at` | CPU % | RAM % | Disk % | Temperature °C | Power |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 1787451290 | 0.1 | 5.8 | 2.0 | 32.0 | unavailable |
| 2 | 1787451297 | 0.1 | 5.8 | 2.0 | 31.0 | unavailable |
| 3 | 1787451304 | 0.1 | 5.8 | 2.0 | 31.0 | unavailable |
| 4 | 1787451311 | 0.0 | 5.8 | 2.0 | 31.0 | unavailable |
| 5 | 1787451318 | 0.1 | 5.8 | 2.0 | 32.0 | unavailable |
| 6 | 1787451325 | 0.1 | 5.8 | 2.0 | 33.0 | unavailable |
| 7 | 1787451332 | 0.0 | 5.8 | 2.0 | 32.0 | unavailable |
| 8 | 1787451339 | 0.1 | 5.8 | 2.0 | 32.0 | unavailable |
| 9 | 1787451346 | 0.0 | 5.8 | 2.0 | 32.0 | unavailable |
| 10 | 1787451353 | 0.1 | 5.8 | 2.0 | 32.0 | unavailable |

The first request after application startup can legitimately have unavailable CPU data while the two `/proc/stat` snapshots warm up. All ten acceptance samples above had live bounded CPU values.

## Temperature and power validation

A near-simultaneous authenticated response reported 32.0°C. The host's selected `x86_pkg_temp` sysfs sensor reported 32000 millidegrees (32.0°C), an exact match. Power reported `unavailable` with a null wattage; it was not represented as `0 W`.

## Dashboard UI evidence

The staging-only administrator `admin1` successfully signed in to the staging dashboard. The password is intentionally not recorded in this report or any handoff.

- The live dashboard loaded CPU, RAM, storage, temperature, power, uptime and application cards from the authenticated monitor endpoint.
- A normal live refresh was observed: the freshness text changed from `Vừa cập nhật` to `Cập nhật 5 giây trước` after an additional eight-second observation window, consistent with the seven-second successful-poll cadence. Values also updated (RAM 6.0% to 6.1%; temperature 32.0°C to 33.0°C).
- The unavailable power source is visibly distinct: value and status both render `Không khả dụng`, rather than a misleading 0 W.
- At 360, 390, 768, 1280, 1440 and 1920px, the dashboard had no document-level horizontal overflow. Monitor cards adapted one/two/four columns at their expected breakpoints; charts and popular-game content stayed in bounds. English monitor layout also passed at 390px.

Hidden-tab pause/resume and an injected monitor-failure state were not simulated in this browser surface. They remain a narrow runtime-observation limitation, not a backend authorization or live-sampling failure.
