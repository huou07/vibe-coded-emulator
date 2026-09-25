# Vibe Coded Emulator

A cross-platform, offline-first emulator front-end. It runs GBA, Nintendo DS and
Nintendo 3DS games from your own local ROM files, with native clients for macOS,
Windows, Linux and Android and a browser player served by a small Python server.

## Highlights

- **Web app** (`app.py`): bilingual library, per-game pages, web player
  (EmulatorJS), local save slots and autosave, controller pairing, multiplayer
  rooms on a LAN relay, phone-as-controller, LAN save transfer.
- **Native desktop/Android apps** (`native-offline/`): Tauri shell plus a
  portable libretro player for GBA/NDS/3DS with per-platform renderers
  (Metal/Vulkan on macOS, Vulkan/OpenGL on Linux/Windows, Vulkan/OpenGL ES on
  Android), the shared layout chooser, 10 quick-save slots, Exit Game, autosave
  and the native phone-controller host.
- **Offline by design**: ROMs and saves stay on your device.

## Building

See `native-offline/scripts/` for the per-platform build scripts and
`deploy/` for staging packaging. The web app runs with the Python standard
library only:

```bash
python3 app.py            # serve the web app
python3 -m unittest discover -s tests
```

## Licensing

**Vibe Coded Emulator is free software licensed under the GNU General Public
License, version 3 or (at your option) any later version
(`SPDX-License-Identifier: GPL-3.0-or-later`).**

Copyright (C) 2026 Vibe Coded Emulator contributors.

Under that license you may:

- use the software for any purpose, including **commercial** use;
- study and **modify** it;
- **redistribute** it and distribute **modified versions / forks**.

If you distribute the software or a modified version, the GPL requires you to:

- keep the applicable **copyright notices, license notices and attributions**;
- license your modified version under the GPL and make its **complete
  corresponding source code** available;
- mark modified files and record relevant modification dates.

There is no additional advertising, splash-screen, branding or non-commercial
restriction. **Forks do not have to keep the Vibe Coded Emulator name, logo,
branding or original UI.**

The full license text is in [`LICENSE`](LICENSE).

### Source

- Source repository: `https://github.com/huou07/vibe-coded-emulator`
  <!-- TODO(owner): replace with the real public repository URL. -->
- The exact source revision for a released binary is the tagged commit listed in
  the release notes and `native-offline/releases/catalog.json`.

## Third-party components

The distributed binaries bundle or serve third-party components, each under its
own license and copyright; they are **not** relicensed by this project. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and
[`docs/licensing/license-audit.md`](docs/licensing/license-audit.md) for the full
list, exact versions, copyright holders and corresponding-source links.

Notable components:

- Emulator cores: **Azahar** (GPL-2.0-or-later), **melonDS DS**
  (GPL-3.0-or-later), **mGBA** (MPL-2.0).
- **EmulatorJS** web player and its netplay relay (GPL-3.0 / Apache-2.0).
- **MoltenVK** (Apache-2.0), **Tauri** (Apache-2.0 OR MIT), Rust/Android
  dependencies (MIT/Apache-2.0/BSD), **Lucide** icons (ISC), **Pixelify Sans**
  and **Roboto Condensed** fonts (SIL OFL 1.1).

No proprietary firmware, encryption keys, or commercial ROMs are bundled.
Users supply their own legally obtained game files.

## Contributing and attribution

Contributions are accepted under `GPL-3.0-or-later`. Keep existing copyright and
license notices, and add your own copyright notice to files you create. See
`docs/licensing/distribution-compliance.md` for the release checklist.
