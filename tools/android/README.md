# AN3 staging-first Android regression harness

All tools in this directory default to `http://192.0.2.8:8092`. Production is rejected unless `tools/android/open-staging.sh --production --allow-production` is typed intentionally; routine P3 testing must not use that override.

The tools use the default ADB target and never print, write, or select by device serial. They only query connection state, Android version, browser version, and logical screen size. They do not root the phone, install APKs, read accounts or personal files, use `run-as`, or inspect arbitrary browser tabs.

## First run

```bash
<LEGACY_CHECKOUT> --report <LEGACY_CHECKOUT>
<LEGACY_CHECKOUT>
```

Every screenshot is captured only after the approved browser is foreground and is stored under `<LEGACY_CHECKOUT> Use labels that identify only the staging test state, never a person or device identifier.

## Regression passes

```bash
# Homepage intent, host response, and visual evidence.
<LEGACY_CHECKOUT>

# Capture the current staging player layout first, then supply live coordinates.
<LEGACY_CHECKOUT> gba-layout
<LEGACY_CHECKOUT> --start X,Y
<LEGACY_CHECKOUT> --game-box X,Y,WIDTH,HEIGHT --pad X,Y --native-menu X,Y
<LEGACY_CHECKOUT> --enter-toggle X,Y --exit-toggle X,Y
```

The GBA/NDS/fullscreen tools intentionally require live coordinates rather than embedding old screenshot coordinates. ADB gesture injection plus host route status is runtime evidence of the device path; visual canvas/FPS, native-menu priority, save/load, and portrait/landscape remain explicit checks because a screenshot alone is not WebGL proof.

## Private PWA localhost preflight

Start the verified key-only private local forward from `<LEGACY_CHECKOUT> then run the script. Do not disable browser security, expose staging publicly, change Cloudflare, or leave the reverse mapping behind.

```bash
export AN3_STAGING_SSH_IDENTITY_FILE=~/<REDACTED_PATH>
export AN3_STAGING_SSH_KNOWN_HOSTS=~/<REDACTED_PATH>
<LEGACY_CHECKOUT> 18092
<LEGACY_CHECKOUT> 18092
```

`smoke-pwa.sh` removes only its own `adb reverse tcp:18092` mapping when it exits. The full PWA evidence record must be written under `<LEGACY_CHECKOUT> and must state `PWA_OFFLINE_E2E=DOCUMENTED_BLOCKER` if `isSecureContext`, Service Worker/install, or offline relaunch cannot be demonstrated truthfully.
