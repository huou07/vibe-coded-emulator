# P2.5 — Power telemetry

## Finding

The staging service account has no readable RAPL `energy_uj` values and no readable hwmon `power*_input` values. Fabricating a wattage would be misleading.

## Result

The established safe schema is retained: `power.watts` is `null` and `power.status` is `unavailable`. The monitor renders this as an explicit verified-unavailable state rather than a zero reading.

## Acceptance status

Passes the planner’s accepted `VERIFIED_UNAVAILABLE` outcome. A privileged future deployment can expose a safe read-only power source if real consumption becomes required.
