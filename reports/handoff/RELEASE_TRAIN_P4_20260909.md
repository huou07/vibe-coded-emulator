# P4 — artifact publication infrastructure

Status: COMPLETE, 2026-09-09. Production was not accessed, including health or read checks.

The staging-only `/download-app/artifacts.json` manifest publishes all required fields for five categories: version, asset version, build timestamp, platform, architecture, format, filename, size, SHA-256, signature status and runtime status. Each entry also has an explicit availability status and a download URL only when the artifact is eligible.

Publication is fail closed. A filename in `native-offline/releases/` is insufficient: it must be allowlisted with recorded evidence and match its immutable size and SHA-256 at request time. The download route uses the same decision, so byte drift removes both the link and access. Unlisted historical files return 404.

## Published staging artifacts

| Status | Platform / format | Version | Size | SHA-256 | Evidence |
| --- | --- | --- | ---: | --- | --- |
| Available | macOS arm64 DMG | 0.4.4 | 42282987 | `37e24bf1d1d6c44ff3267c5649b16010f8bce076cc0bac632cddf17d431b975c` | Ad-hoc staging signature verified, not notarized; mounted Settings Escape/Save and GBA/NDS launch smoke passed; full native matrix unverified. |
| Available | Android arm64 APK | 0.1.1 | 37867772 | `e47634b0f72564a6bb4d1a89ad0769aaaa23d197980dab315999b44bbb60c3f3` | APK v2/v3 staging signature verified; GBA, NDS and 3DS launch smoke passed on ARM64 Android AVD; physical-device performance unverified. |
| Blocked | Linux amd64 DEB | — | — | — | No verified Linux build/test host evidence. |
| Blocked | Linux amd64 Flatpak | — | — | — | No verified Linux build/test host evidence. |
| Blocked | Windows x64 EXE | — | — | — | No verified Windows build/signing host evidence. |

The Release Center renders exactly these five categories. Available artifacts have download links. Blocked entries state the evidence gap and contain no placeholder link. No platform port or new binary was created.

The service worker includes the Release Center and its required icon assets in the shell. Installer and source downloads bypass Cache Storage; the manifest is fetched network-only. This prevents large immutable installers or live status data from entering the offline cache.

## Validation

- `python3 -m unittest discover -s tests -q`: 94 passed.
- Renderer/touch Node suite: 12 passed.
- Python compilation and diff whitespace checks passed.
- A focused integrity test proves that altered bytes change an available item to blocked and remove its URL.
- Local staging-mode route smoke produced 2 available and 3 blocked entries, with exactly 2 page links.
- Visible staging browser smoke showed macOS and Android links plus truthful link-free DEB, Flatpak and EXE cards.
- Both live staging downloads were fetched fully and matched recorded sizes and SHA-256 values. Unlisted historical DMG and Linux DEB requests returned 404.

## Staging

- Asset: `8ecb7b06ad8c`
- Release: `/opt/an3-arcade-staging/releases/20260909-195906-8ecb7b06ad8c`
- Rollback: `/opt/an3-arcade-staging/releases/20260909-194251-e9cca6502858`

P4 is complete. P5 should use Astra Medium to produce and validate the next Android staging APK against the finalized publication contract.
