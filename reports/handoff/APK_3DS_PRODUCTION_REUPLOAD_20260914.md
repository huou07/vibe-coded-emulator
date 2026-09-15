# APK 3DS production reupload — 2026-09-14

Status: COMPLETE. The owner explicitly requested reuploading the existing Android APK with 3DS enabled to production.

- APK: `vibecodedemulator-0.4.4-android-arm64-staging.apk`; version 0.4.4, versionCode 4004; 86,441,975 bytes.
- SHA-256: `4ee9e6399a4f08880a71c2c5f3955949cf4b252412883bd3f6151759efc6b3cb`.
- [Production APK download](https://an3tocom.space/download-app/release/vibecodedemulator-0.4.4-android-arm64-staging.apk?sha256=4ee9e6399a4f08880a71c2c5f3955949cf4b252412883bd3f6151759efc6b3cb).
- Completed: 2026-09-14T05:37:53.565741+00:00.

## Scope and validation

CodeGraph was used first to locate the 3DS launch path and release dependency boundary. The unchanged current APK was uploaded again over strict, key-only SSH. The APK and its sidecar were atomically replaced; the replacement inode changed. Production catalog, other installers, application source, service process and production data were preserved. The byte-identical reupload correctly retains release identity `production-ced9540547b280ab` and asset `baa8a060f571`.

Local APK Signature Scheme v2 verification passed. APK size/SHA-256 and sidecar matched the catalog. Its embedded Android bootstrap advertises GBA/NDS/3DS and accepts native 3DS launch. The bundled Azahar 2126.0 core matched its embedded manifest hash; ZIP integrity passed. The staging APK HTTP stream matched the same bytes before upload.

After upload, the public HTTPS download returned HTTP 200, exactly 86,441,975 bytes and the expected SHA-256. Headers included `Cache-Control: no-store` and `CF-Cache-Status: BYPASS`. The Release Center linked the exact SHA-bound URL, an invalid hash returned 404, and public production health passed. The production JSON manifest route intentionally remains staging/development-only; the production on-disk catalog and public download page were verified instead.

Gameplay was not rerun for this byte-identical reupload. Existing runtime evidence and its limitations remain as recorded in /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/docs/CODEX_PROGRESS.md: native Vulkan 3DS frames, input, layouts and save state; no new claim of human-audible sound or perceived smoothness.

## Rollback and evidence

Retained server backup: `/opt/an3-arcade-backups/apk-reupload-20260914T053753.244863Z`. It contains the previous APK, sidecar, catalog and reupload receipt. Uploaded temporary files were removed after successful replacement. No service restart was required.

- Local receipt: /Users/meomeo/Documents/Codex/2026-09-14/use-codegraph-first-to-narrow-symbols/work/apk-reupload/production-reupload-receipt.json
- Public HTTP verification: /Users/meomeo/Documents/Codex/2026-09-14/use-codegraph-first-to-narrow-symbols/work/apk-reupload/production-http-verification.json
- Staging verification: /Users/meomeo/Documents/Codex/2026-09-14/use-codegraph-first-to-narrow-symbols/work/apk-reupload/staging-before.json
- Repository handoff: /Users/meomeo/Documents/Codex/2026-08-12/an3-arcade-production-ui-ux-codex/an3-arcade/reports/handoff/APK_3DS_PRODUCTION_REUPLOAD_20260914.md
- User-facing report: /Users/meomeo/Documents/Codex/2026-09-14/use-codegraph-first-to-narrow-symbols/outputs/apk-3ds-production-reupload-20260914.md

No remaining work for this reupload.
