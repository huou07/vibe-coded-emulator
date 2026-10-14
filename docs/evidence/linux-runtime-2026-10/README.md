# Linux runtime acceptance evidence (2026-10)

Curated from operator-home acceptance runs that were archived out of the
operator's home directory on 2026-10-13. The full run trees are preserved as
zstd tarballs in the operator scratch archive; only the durable artifacts are
tracked here. The archive location is deliberately not recorded in this
repository.

## v342-ui-control — v3.4.2 Linux UI control acceptance

`vce-342-linux-ui-acceptance` (2026-10-08). Held/released screenshots for the
GBA input path plus the automation summaries and app logs.

| File | What it shows |
| --- | --- |
| `screen.png` | Player surface at capture time |
| `gba-x-held.png` / `gba-x-released.png` | X keypress transitions |
| `gba-z-held.png` / `gba-z-released.png` | Z keypress transitions |
| `isolated-x-held.png` / `isolated-x-released.png` | Same probe with other input isolated |
| `summary.json` | Overall pass/fail for the run |
| `input-summary.json` | Input-path probe result |
| `x-summary.json` / `isolated-x-summary.json` | Per-probe results |
| `ui-control*.json` | Redacted control-harness invocation metadata for the probes |
| `*-app.log` | Emulator process logs for each probe |

## v352-runtime-probes — v3.5.2 Linux runtime

`vce-352-linux-runtime-20261009` (2026-10-09). Package provenance and the
paused-control probes from that soak run.

| File | What it shows |
| --- | --- |
| `vibecodedemulator-3.5.2-linux-amd64.deb.sha256` | Checksum of the tested .deb |
| `deb-picker-diagnostic-current.txt` | File-picker diagnostic output |
| `paused-control-probe-20261009{b,c,d}.json` | Paused-state control probe results |

## Scope limits

- Screenshots are evidence of a specific run on this machine, not a
  cross-platform acceptance result. Android, Windows and macOS remain
  unverified from these artifacts.
- The soak directories from the same run (3DS/NDS/GBA soaks, isolated profiles,
  the extracted `root/` tree and the `source/` snapshot) were not curated here
  because they duplicate build output and repository source. They remain
  available in the full tarball.
- The only files tar could not read were root-owned Mesa shader caches, which
  carry no evidentiary value.

## Gameplay performance acceptance audit (2026-10-14)

The retained v3.4.2 and v3.5.2 files are useful UI, input-transition, paused
control, and package-integrity probes. They do not establish sustained gameplay
performance: they lack a matched hardware/OS/GPU/driver/core identity and do not
record game-speed accuracy, frame-time distribution/tail spikes, measured input
latency, audio glitches, sustained CPU/GPU/memory use, or thermals/power. The
v3.5.2 pause probe's Vulkan-ready state and frame counts are not performance
metrics.

The `vce-gameplay-performance` procedure was loaded and used to assess this
archive. The target inventory was checked at source SHA
`df4c4ec116157f1b0be564823a41041bbbc885e4` on 2026-10-14. Refreshed
`an3ctl targets --json` reports: Web available without
`playwright-cli`; Android unavailable with no devices; the emulator adapter
available but no local player path (remote Linux/Windows targets are listed, but
no local player artifact is present); Switch unavailable without its bridge
harness; macOS unavailable without an active UI-control bridge; Linux desktop
unavailable without WebKitGTK WebDriver and a display; Windows builder
`an3-win11-build` unreachable. No intended runtime met the procedure's
preconditions, so no new gameplay baseline or performance metrics were collected.
The Linux/native cross-platform performance rows remain `UNVERIFIED`. The next
discriminating action is a bounded sustained run on an authorized supported
Linux Vulkan device with a lawful fixture, pinned core and exact artifact/source
identity, collecting the fields required by that procedure.

See `docs/archive/checkpoint-home-scratch-cleanup.md` for how this archive
was produced and how to restore from it.
