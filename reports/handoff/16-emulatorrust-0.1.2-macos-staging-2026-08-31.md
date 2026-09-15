# Handoff: EmulatorRust 0.1.2 macOS — deployed to staging

Date: 2026-08-31

## Outcome

EmulatorRust 0.1.2 is deployed to the isolated staging environment. The Apple
Silicon macOS build imports local GBA, NDS, and 3DS ROMs into the app-private
store, detects the supported system, and preserves the packaged player's menu,
virtual controls, touch surface, and physical-keyboard contract. Large 3DS
images deliberately launch native Azahar for reliable performance.

## macOS 0.1.2 changes

- Native ROM stream URLs retain a safe content extension. This fixes the
  EmulatorJS case where a UUID-only URL started a core without loading the
  selected ROM.
- Native import identifies GBA, NDS, and 3DS from safe suffixes, a ZIP central
  directory, or a ROM header. 3DS aliases include `.3ds`, `.3dsx`, `.cci`,
  `.cia`, and `.cxi`.
- Existing UUID-only native records migrate at launch without moving or
  duplicating a ROM.
- 3DS cards use **Open Azahar** as the performance path and expose the
  EmulatorRust control route only for small 3DS images. Large images route to
  native Azahar instead of exhausting the WebKit WebAssembly process.
- The missing Tauri `allow-launch-native-3ds` capability is enabled.
- The native runtime revalidates app HTML/JS/CSS and version-tags shell assets,
  preventing WebKit from retaining an older player UI.

## Local validation

- `python3 -m unittest discover -s tests -v`: **41 passed**.
- `cargo test --manifest-path native-offline/src-tauri/Cargo.toml`: **3 passed**.
- JavaScript syntax, native packaging check, Python compile, and
  `git diff --check`: passed.
- GBA actual-ROM smoke test: rendered with virtual controls at approximately
  60 FPS.
- NDS actual-ROM smoke test: reached the dual-screen game UI at approximately
  59 FPS.
- 3DS actual-ROM smoke test through the card's **Open Azahar** action: reached
  the game language screen at **100% / 60 FPS**.
- The in-app Azahar/WebAssembly route showed the menu, 3DS virtual controls,
  touch surface, and keyboard-capable core, but a large retail image consumed
  about 2.5 GB WebKit memory and did not render reliably. The final UI blocks
  that unsafe route for images over 768 MiB and explains the native fallback.

## Final macOS artifact

- File: `native-offline/releases/emulatorrust-0.1.2-macos-aarch64.dmg`
- SHA-256:
  `f1b78b40f7c9acd9759be66c42a58ee3c85a5f884df4c47421da1e634de66b42`
- Signature check: `codesign --verify --deep --strict` passed.
- Disk-image verification: `hdiutil verify` passed.
- The signature is ad-hoc for staging only; the DMG is not notarized for a
  public macOS release.

## Staging deployment verification

- Deployment result: `STAGING_RELEASE=PASS`.
- Current staging asset: `ffd93d702d50`.
- Health endpoint: `http://192.168.1.8:8092/health` returned `ok` with
  `environment: staging` and the current asset.
- macOS download endpoint returned HTTP 200:
  `http://192.168.1.8:8092/download-app/release/emulatorrust-0.1.2-macos-aarch64.dmg`.
- Source download endpoint returned HTTP 200:
  `http://192.168.1.8:8092/download-app/source`.
- Rollback target:
  `/opt/an3-arcade-staging/releases/20260830-204018-39259ec705bd`.

## Scope

Production was not deployed or changed. The deployment workflow prepared a
production archive for a separately authorized release path, but it did not
execute that path.
