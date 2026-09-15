# EmulatorRust 0.2.0 — integrated Azahar macOS staging handoff (2026-08-31)

## Scope and deployment

- Deployment was made only to the isolated staging service at `http://192.168.1.8:8092`.
- Active staging asset version: `5e6f06f4929b`.
- Active release: `/opt/an3-arcade-staging/releases/20260831-234716-5e6f06f4929b`.
- Staging rollback target: `/opt/an3-arcade-staging/releases/20260831-110501-ffd93d702d50`.
- Production was not contacted, switched, or restarted. `deploy-stage.sh` prepared its repository-policy production archive in staging `/tmp`, but no production updater was executed.

## Delivered macOS runtime

- Artifact: `emulatorrust-0.2.0-macos-aarch64.dmg` for Apple Silicon, minimum macOS 13.4.
- SHA-256: `089220087f5e6e9f0f93f177f2d74f893d17a592fb30d1acf46ce5dbbd64ecb7`.
- The app embeds the official Azahar macOS ARM64 libretro core and bundled MoltenVK. 3DS runs in-process as Azahar libretro -> Vulkan 1.1 -> MoltenVK -> Metal; it does not open an external Azahar application.
- Azahar's GPL notice, original source/core provenance, MoltenVK license/manifest, and third-party notices are packaged in the app. The staging source download is available from `/download-app/source`.
- mGBA and melonDS regular/legacy payloads are embedded and are selected for GBA and NDS respectively.

## Player behavior

- The native importer identifies GBA, NDS, and supported decrypted 3DS container formats before storage. ZIP archives and CIA install packages are rejected rather than importing a file that cannot be played in-process.
- The 3DS surface provides Menu and Pad toggles, D-pad, Circle Pad, ABXY, L/R, Start/Select, lower-screen touch, and physical-keyboard mapping. Option + arrow keys drive the Circle Pad; arrow keys, Z/X, A/S, L/J, Return, and Space map to the standard controls.
- The Vulkan presenter uses the MTKView drawable with `framebufferOnly=NO`, waits on core sync objects, preserves aspect ratio with black letterboxing, and rebuilds safely on resize or drawable changes.

## Verification evidence

- `npm run check`, Rust `cargo check`, Rust tests (4), and the full repository Python suite (41) passed.
- The finished DMG passed `codesign --verify --deep --strict` and `hdiutil verify`; the mounted app reports version `0.2.0` and `LSMinimumSystemVersion=13.4`.
- In a native macOS hardware harness using a valid local test ROM, the Vulkan/MoltenVK/Metal path created one hardware device, presented continuously through default and side-by-side layouts, survived two resizes, and completed minimize/restore testing without a crash (437--449 presented frames per eight-second test).
- GBA and NDS core payload URLs returned HTTP 200 from the running packaged app.
- The fresh staging download matched the local DMG byte-for-byte and passed `hdiutil verify`. Staging `/health` returns `environment: staging` with asset version `5e6f06f4929b`.

## Release constraints

- This is an ad-hoc-signed staging build, not a notarized public distribution. A Developer ID signature and notarization are required before a public macOS release.
- The macOS visual click-through pass could not be completed because the local Mac session was locked. Bundle launch, loopback serving, native host controls, and GPU presentation were verified programmatically.
- The build targets Apple Silicon macOS 13.4+ and accepts only decrypted, extracted 3DS images supported by the embedded core.
