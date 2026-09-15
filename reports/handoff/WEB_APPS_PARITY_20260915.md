# Web/apps parity fixes, platform verification, and deployment readiness — 2026-09-15

Status: COMPLETE. Staging and owner-authorized production now serve asset
`0c307876a21f`.

The earlier "LAN outage" was a client-network problem: this Mac's Wi-Fi is on
a network that also uses `192.168.1.0/24`, so the `.8` it pinged was a
different device. The real host (`debian`) is healthy — `ss -ltn` shows
`0.0.0.0:22`, `0.0.0.0:8091`, `192.168.1.8:8092`, and UFW is active with the
intended rules — and public HTTPS stayed up because cloudflared connects
outbound to `127.0.0.1:8091`. Deployment was completed over the verified
Tailscale peer `debian` (`100.94.63.8`); the live SSH ED25519 host key
`SHA256:GKhJRLdeuup0u+mawvqP81INvw0vG7LAdWpzqL9sVBo` matches the existing
`192.168.1.8` known-hosts entry, so strict host-key checking was preserved.

## Owner request

Complete the apps and web; make GBA/NDS/3DS playable; bring the other apps and
the web to full DMG-level UI/UX; test and fix bugs; solve blockers; deploy
production.

## Fixes shipped in this session

1. **Stale test contract (canonical-verification blocker).** Production is
   download-first and intentionally serves no public server-ROM library, but
   `tests/test_integration.py` still asserted library routes against the
   production server. The suite now runs a second staging-environment server
   (`ArcadeLibraryIntegrationTests`, port 18792) for library coverage and adds
   `ArcadeProductionIntegrationTests` for the deliberate production 404s, the
   current-catalog installer downloads, and HTTP/1.1 reuse. Python discovery is
   131 tests, all PASS (previously 127/129 with two permanent failures).

2. **RG-076 — versioned `player-ui.js` 404.** The `/static/v/<asset>/...`
   route omitted `player-ui.js`, so `/offline` and `/play` loaded a 404 for the
   generated shared UI model. `globalThis.AN3PlayerUI` stayed `undefined`,
   which silently removed the shared analog joystick from the web player
   (`addAnalogStick` returns early) and made the service-worker precache fetch
   a 404. `app.py` now serves it, and the integration test derives every
   required name from `app.PLAYER_BOOT_ASSETS` so a future boot asset cannot
   regress the same way.

3. **RG-077 — missing D-Pad/Analog-Joystick selector.** `static/offline.js`
   rendered virtual-pad settings without `#padDirectionalControl`, so the
   offline player could never enable the shared joystick even after the model
   loaded. The offline markup now matches the DMG/native control model.

4. **RG-078 — browser 3DS honesty gate.** The browser Azahar WebAssembly core
   (both the cached `latest` 2026-08-24 build and the CDN `nightly`
   2026-07-25 build) boots but reports `getVideoDimensions() = -1` and creates
   no OpenAL/WebAudio context; the EJS source canvas and the WebGPU
   presentation canvas stay black after clearing caches and unregistering the
   service worker. The web shell now disables 3DS cards with
   "3DS needs the native app" plus a `/download-app` link. Native 3DS playback
   (macOS/Windows/Linux/Android) is unchanged.

5. **Favicon 404** removed by declaring the existing `icon-192.png` in the
   shared layout head.

## Verification evidence

- Canonical suite: `tools/release-train.sh --staging verify all` → EXIT 0
  (131 Python tests, web NDS touch, 11 renderer cases, `npm run check`,
  `git diff --check`).
- Web (Chrome 152 via CDP, legal fixtures, local final build `0c307876a21f`):
  GBA frames 112→474 and 82→564; NDS 112→594; 3DS Azahar core preloaded
  (3.8 MB, verified in `EmulatorJS-core`); joystick selector toggles
  `.analog-mode`; 3DS cards gated by RG-078; the only remaining console error
  is EmulatorJS's non-fatal `checkForUpdates` CDN fetch blocked by COEP.
- Android (AVD `codex-nds-api35`, installed 0.4.7 / versionCode 4007, driven
  through WebView CDP): GBA "Minimal GBA" at 59/59 FPS, NDS "Minimal NDS"
  Golden Sun at 59–60/60 FPS, 3DS "Minimal 3DS" Pokémon X language screen at
  58/58 FPS with the circular joystick and native overlay;
  `topResumedActivity=NativeGameActivity`, isolated `:game` process stable for
  60 s+, zero `FATAL EXCEPTION`/tombstone, clean return to `MainActivity`.
- Evidence directory: `work/apps-web-20260915/` (screenshots, drivers, logs).

## Deployment result

- Staging: `STAGING_RELEASE=PASS`, asset `0c307876a21f`, release
  `/opt/an3-arcade-staging/releases/20260915-184351-0c307876a21f`, rollback
  `/opt/an3-arcade-staging/releases/20260915-134525-690bcb150246`. Health,
  `static/v` byte parity for `offline.js`/`player-ui.js`/`player.js`/`site.css`
  and versioned `player-ui.js` `200 text/javascript` verified over a strict
  `ssh -L 18092:192.168.1.8:8092` tunnel.
- Production: `PRODUCTION_RELEASE=PASS`, asset `0c307876a21f`, release
  `production-548d5753f65777cf`, app backup `/opt/an3-arcade-backups/20260915-184440`,
  SQLite backup `/srv/an3-arcade/backups/arcade-predeploy-20260915-184440.db`
  (integrity PASS). Public HTTPS: health reports the new asset; `/`, `/offline`
  and `/download-app` 200; four versioned assets parity; the deployed
  `offline.js` carries the RG-077 selector and RG-078 gate; `/games`,
  `/api/library-version` and `/game/*` return 404 (download-first); all five
  catalog installers return `200` with exact expected sizes and `no-store`;
  a stale-hash URL returns 404; production GBA web smoke advanced frames
  `41 → 403`.
- Services `an3-arcade`, `an3-arcade-staging` and `cloudflared` are `active`;
  the staging tunnel, local Chrome and host `/tmp` deploy files were removed.

## Ready-to-publish artifact

- Source package:
  `work/production-deploy-artifacts/20260915-174826/an3-arcade-production-20260915-174826.tgz`
  SHA-256 `b2b4b1a40d118485849e609cae8598f1d27d4c04a69007b02f1d0ab0f9c4dcf9`
  expected static asset `0c307876a21f`.
- Deploy wrapper (pre-generated, staged for the production host):
  `work/production-deploy-artifacts/20260915-174826/deploy-an3-production-20260915-174826.sh`.
- Installer catalog unchanged: 5 installers (macOS 0.4.5, Android 0.4.7,
  Linux 0.4.5 DEB/Flatpak, Windows 0.4.5), `RELEASE_CATALOG=PASS`.

## Deployment commands (after host access returns)

```bash
export AN3_STAGING_SSH_IDENTITY_FILE=/Users/meomeo/.ssh/an3_codex_ed25519
./tools/ssh/check-staging-key.sh            # STAGING_SSH_KEY_AUTH=PASS
./deploy-stage.sh                            # staging release
# verify staging HTTP parity (health asset 0c307876a21f, static byte parity)
# then, with explicit owner approval already given for this task:
STAMP=20260915-174826
scp -i /Users/meomeo/.ssh/an3_codex_ed25519 \
  work/production-deploy-artifacts/$STAMP/an3-arcade-production-$STAMP.tgz \
  work/production-deploy-artifacts/$STAMP/deploy-an3-production-$STAMP.sh \
  huou07@192.168.1.8:/tmp/
ssh -i /Users/meomeo/.ssh/an3_codex_ed25519 huou07@192.168.1.8 \
  "sudo -n bash /tmp/deploy-an3-production-$STAMP.sh"   # wrapper location per host helper policy
```

The exact production invocation must follow the host's installed helper
policy; if the owner installed a root-owned updater entrypoint, use it instead
of a raw `sudo bash` (the wrapper already verifies the archive SHA-256 before
calling `deploy/update-production.sh`).

## Known limitations

- Web 3DS playability is an upstream Azahar WebAssembly limitation (RG-078).
  GBA/NDS are verified playable on the web; 3DS is verified playable on the
  native apps.
- Windows/Linux in-window parity remains the owner-approved pragmatic scope
  from the 0.4.5 release (shared Tauri shell plus the native player window).
- Windows real-hardware Vulkan/3DS acceptance remains unverified.
