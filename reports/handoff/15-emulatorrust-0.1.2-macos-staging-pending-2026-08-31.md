# Handoff: EmulatorRust 0.1.2 macOS — staging pending

Date: 2026-08-31

## Outcome

The Apple Silicon macOS build is complete locally. It imports local GBA, NDS,
and 3DS ROMs into the app-private store, identifies the supported system, and
keeps the player/input contract for the packaged player. The staging release
is **not deployed** because the required verified staging SSH key is not
available to this session.

## macOS 0.1.2 changes

- Native ROM stream URLs retain a safe content extension. This fixes the
  EmulatorJS case where a UUID-only URL started a core without loading the
  selected ROM.
- Native import now identifies GBA, NDS, and 3DS from safe suffixes, a ZIP
  central directory, or a ROM header; 3DS aliases include `.3ds`, `.3dsx`,
  `.cci`, `.cia`, and `.cxi`.
- Existing UUID-only native records are migrated at launch without moving or
  duplicating the ROM.
- 3DS cards use **Open Azahar** as the performance path and expose the
  EmulatorRust control route only for small 3DS images. Large images are
  deliberately routed to native Azahar instead of exhausting the WebKit
  WebAssembly process.
- The missing Tauri `allow-launch-native-3ds` capability is enabled.
- The native runtime now revalidates app HTML/JS/CSS and version-tags the
  shell assets, preventing a WebKit cache from retaining an older player UI.

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

## Final artifact

- File: `native-offline/releases/emulatorrust-0.1.2-macos-aarch64.dmg`
- SHA-256:
  `f1b78b40f7c9acd9759be66c42a58ee3c85a5f884df4c47421da1e634de66b42`
- Signature check: `codesign --verify --deep --strict` passed.
- Disk-image verification: `hdiutil verify` passed.
- Signature is ad-hoc for staging only; the DMG is not notarized for a public
  macOS release.

## Staging status

- Current staging health: `ok`, asset `39259ec705bd`.
- The new macOS release route currently returns 404 because it has not been
  copied to staging.
- Required preflight failed:

  ```text
  huou07@192.168.1.8: Permission denied (publickey,password).
  ```

Do not use a password or bypass the strict staging SSH helper. After the owner
loads the approved staging key into the SSH agent, rerun `./deploy-stage.sh`
from the repository root, then verify `/health` and the 0.1.2 DMG download
route on staging.

## Remaining manual check

The Mac auto-locked after the completed runtime tests. When it is unlocked,
open the final DMG or final app bundle once and confirm that a large 3DS card
shows **Open Azahar** plus the native-performance note rather than the
WebAssembly controls button. The source, tests, and final packaged runtime
already contain that guard.
