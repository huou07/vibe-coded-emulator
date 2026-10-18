# Screen layout and per-core display options

Read when: you change the layout chooser, per-system screen layouts, core options
that select a layout, or the persisted layout keys.

Skip when: the change is save-state content or a site-chrome-only edit.

## Status

| Piece | Status | Evidence |
| --- | --- | --- |
| Single-source layout schema (v2) with `id`/`label`/`coreOption`/`coreValue` | `GOOD` | `native-offline/shared/native-layout-schema.json` |
| Generator and its `--check` mode | `GOOD` | `native-offline/scripts/generate-player-ui.mjs` |
| Generated consumers (macOS `.mm`, Linux controls/runtime, Android model) | `GOOD` at source level | `native-offline/shared/generated/native_layouts.h` consumed by each platform |
| Layout persistence with legacy spellings resolving | `GOOD` at source level | Keys `an3.native-screen-layout.v1.<system>`; Android `screen-layout-<system>`/`nds-layout`; Linux file `screen-layout.txt` |
| Runtime layout verification on Linux and Android | `UNVERIFIED` | The recorded runtime smoke was a macOS 1.2.0 build; the Linux/Android runtimes were not re-run after the schema change |
| Layout toolbar behaviour (chooser instead of cycling) | `GOOD` | Shared player UI tests |

## Code map

- `native-offline/shared/native-layout-schema.json` — the only source of layouts.
- `native-offline/scripts/generate-player-ui.mjs` — generator; `--check` fails on
  drift.
- `native-offline/shared/generated/native_layouts.h` — generated header.
- `native-offline/src-tauri/src/azahar_host.mm`,
  `native-offline/native-runtime/platform/linux/linux_controls.cpp`,
  `native-offline/native-runtime/platform/linux/linux_runtime.cpp`, and the
  Android `NativeLayoutModel` consume the generated model.

## Invariants

- The schema is the single source; never hand-edit the generated header.
- Layout selection goes through the core option the schema names, not through an
  ad-hoc switch in a platform file.
- Persisted layout keys keep their legacy spellings resolving, so an existing
  user's choice survives an upgrade.
- The layout chooser replaces cycling; the toolbar Save actions remain quick
  save, quick load, auto save now, load auto save.

## How to verify

```sh
node native-offline/scripts/generate-player-ui.mjs --check
bash tools/verify-project.sh
```

`--check` is the cheap invariant. A layout claim for a platform additionally
needs that platform's runtime build to have consumed the regenerated header.

## Open work

1. Re-run the generated layout on the Linux runtime under Xvfb and record each
   layout's real geometry; today that row is `UNVERIFIED`.
2. When a dedicated Android AVD exists ([android](android.md)), record layout
   switching on device.

## Related

- [nds-touch](nds-touch.md), [native-app](native-app.md), [android](android.md),
  [ui-shell](ui-shell.md)
