# AN3 Arcade — P1.7 Mobile Follow-up

Date: 2026-08-20 (Asia/Ho_Chi_Minh)

## Scope and release

Staging-only follow-up for the owner-reported mobile issue. Commit `af6cca9`:

- keeps the existing virtual pad visible when the current viewport fails a size/collision measurement;
- retains the measurement guard for enlargement and move operations, rather than disabling safety checks;
- sets EmulatorJS native `fps` to `show` as a default. Existing non-NDS EmulatorJS preferences still take precedence; NDS remains isolated from EmulatorJS local storage.

Active staging release: `20260820-215934-p1-mobile-fix`.

- Health asset: `49eeea612e77`
- Immediate rollback release: `20260820-211604-p1`
- Production: unchanged

The first activation attempt rolled back automatically because the staging service takes roughly seven seconds to listen and the readiness window was only two seconds. The successful activation uses a 30-second health-readiness window; it completed with health PASS.

## Evidence

The owner reported before this fix:

| Area | Result |
| --- | --- |
| Save/load, physical keyboard, remapping, PWA | PASS |
| Weak-device performance, speed changes | PASS |
| GBA and NDS virtual pads on phone before fullscreen | FAIL — pad only appeared in fullscreen |
| NDS audio on phone | FAIL — crackling |

After deployment, responsive staging checks at 390×844 and not fullscreen found GBA and NDS pad roots `display:block`, `visibility:visible`, and stage overlay active. For NDS this required explicitly showing the pad because the browser test surface advertises a fine pointer; a real phone should default to NDS auto visibility. A fresh GBA and NDS EmulatorJS menu both rendered `FPS → hiện` (`show`). These are browser checks, not a substitute for physical-device validation.

## NDS audio assessment

No audio latency setting was added. The verified EmulatorJS 4.2.3 runtime hard-codes RetroArch `audio_latency = 64` and exposes no documented loader key or `GameManager` audio-latency method. Changing it speculatively could destabilize save state or audio on other cores, so this remains an observed device issue rather than an unverified profile knob.

The native melonDS menu offers core options such as audio bitrate and interpolation, but neither has been validated as a safe AN3 default. Do not alter them globally without a reproducible Android test.

### Device evidence received after the release

The owner tested Redmi 15 5G on Firefox, Mi Browser, and Chrome using both the built-in speaker and Bluetooth headphones:

- the FPS HUD varies around 30–50;
- Firefox crackles frequently;
- Chrome and Mi Browser crackle chiefly while scenes change;
- both audio outputs show the same failure.

This is consistent with an emulation/WebAudio underrun rather than a Bluetooth or phone-speaker fault. The verified deployed melonDS core is the unthreaded 2025-06 build. Its current core values are `melonds_audio_bitrate = Automatic` and `melonds_audio_interpolation = None`; `None` already avoids interpolation work. The core offers `10-bit` and `16-bit` bitrate choices, but those are fidelity choices, not a proven buffer/throughput remedy, so they remain unchanged.

### Controlled physical experiment (no deployment)

Use Chrome, keep speed at 1×, and select **Low-end / Battery** in the player Performance panel, then apply/restart. This chooses the already-audited melonDS compatibility renderer for the next launch. During the same test, open EmulatorJS **Settings → Graphics Settings → VSync → Disabled**. VSync is a runtime-supported, reversible setting; it is a device experiment only, not a new default.

Leave shaders disabled, audio bitrate on Automatic, and interpolation on None. Record the FPS range and sound through one normal scene transition. If Chrome remains below a stable game rate or still crackles, the next work is a separately scoped core/runtime upgrade or alternative-core feasibility assessment—not an unverified global audio tweak.

## Remaining physical gates

1. On the same phone/browser, start GBA and NDS in portrait before fullscreen: pad must be visible and usable.
2. Rotate, enter/exit fullscreen, open the NDS native menu, and confirm the pad becomes inert under that menu.
3. Confirm the FPS HUD is shown by default on both systems.
4. Re-test NDS sound at normal 1× speed. If crackling persists, record phone model, OS/browser version, whether wired/Bluetooth audio is used, profile, and reproducible game moment before proposing a core-specific experiment.

Production remains manually gated and must not be deployed until these physical checks pass and the owner explicitly approves it.
