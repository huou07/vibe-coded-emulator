# P2.4 — CPU temperature

## Finding

The old helper selected the first alphabetically ordered thermal zone. On the staging host that was `INT3400 Thermal` (20°C), which is not the CPU package sensor.

## Change

Temperature discovery now prioritizes deterministic CPU-package candidates: `x86_pkg_temp`, a CPU package zone, coretemp `Package id 0`, then coretemp core temperatures. It returns the same public metrics schema and reports unavailable only when no suitable readable CPU sensor exists.

## Staging evidence

The host exposes `x86_pkg_temp` as thermal zone 4; it reported approximately 32–37°C during the sample window. The endpoint now selected that temperature rather than the unrelated INT3400 reading. A regression test uses a synthetic sysfs tree to assert this priority order.

## Acceptance status

Passes staging telemetry verification.
