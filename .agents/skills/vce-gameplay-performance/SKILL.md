---
name: vce-gameplay-performance
description: Use when measuring or diagnosing sustained real gameplay performance on a supported VCE platform, including frame pacing, input latency, audio glitches, memory, power or thermals. Do not use for packaging-only work, CI emulator frame counters, smoke boots or speculative optimization.
---

# VCE gameplay performance

Use this procedure when an observable gameplay complaint or an acceptance gap
needs real measurement. A green build, boot frame, UI FPS counter or software
renderer run is not gameplay acceptance.

## Preconditions

- Resolve the exact repository, branch, source SHA and current worktree.
- Select a supported platform, core and lawful fixture that can exercise rendering,
  input, audio and save behavior. Record the fixture identity and hash without
  copying the ROM into the repository or evidence.
- Use physical hardware or an authorized builder with the intended renderer. Do
  not start VMs, Android emulators, GPU builds or installers on the Debian worker.
- Record hardware model, CPU, GPU, OS, driver, renderer, display mode, power mode,
  core name/version/hash, package/artifact hash, settings and test duration.
- Read the applicable platform build and player regression procedures before
  changing runtime, renderer, input, audio or save code.

## Procedure

1. Define the user-visible workload and an acceptance threshold before comparing
   results. Derive the expected rate from the core/game and device capability;
   do not impose a universal FPS target.
2. Capture a bounded baseline on the selected hardware. Include game speed versus
   intended core rate, frame-time distribution and tail spikes, dropped/late
   frames, input-latency method and result, audio underruns/glitches, load time,
   memory and sustained CPU/GPU use. Measure power and temperature on physical
   devices when available.
3. Keep source/artifact, fixture, settings, workload, hardware and duration fixed
   for before/after comparison. Record raw output and tool versions in the
   existing checkpoint/evidence location; avoid committing large captures.
4. Identify the measured bottleneck before proposing a code change. State a
   falsifiable cause and the measurement that would distinguish it from nearby
   causes. Change only the smallest relevant layer.
5. Re-run the same workload. Check rendered correctness, input, audible output,
   and save/load persistence alongside performance. Run matching guards from
   `docs/REGRESSION_GUARDS.md`.
6. If the exact target, instrumentation, renderer or fixture is unavailable,
   prepare the repeatable probe and mark that platform/core result UNVERIFIED.
   A CI emulator or deterministic capture can isolate source regressions but
   cannot substitute for physical gameplay evidence.

## Authority and rollback

Run only on an authorized physical device or dedicated builder. Do not elevate,
read protected credentials, or start unsupported local emulators/builds. If a
comparison regresses rendering, input, audio or saves, stop the session and
preserve user data and raw evidence. Revert the isolated source change or restore
the prior accepted artifact, then rerun the relevant correctness guards before
resuming gameplay; never overwrite saves as a rollback shortcut.

## Evidence and completion

Record platform/core, hardware and OS/GPU/driver, renderer, core and fixture
hashes, source SHA, artifact hash, configuration, duration, raw before/after
measurements, measurement method, acceptance threshold, regressions checked,
and remaining gaps. Use GOOD only for results observed on the intended runtime;
label missing physical, audio, gamepad, thermal or power evidence UNVERIFIED.

Skip this procedure for packaging-only changes, isolated deterministic source
checks, or performance changes proposed without an observed user problem or
measurement. Report what the collected data establishes and what it cannot.
