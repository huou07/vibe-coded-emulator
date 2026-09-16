# Windows 1.3.0 launch smoke — Windows 11 VM (2026-09-16)

Ordered-plan step 5 (Windows part). This is a **launch smoke only**; Windows
gameplay/GPU is still not verified.

## What was run

- VM `an3-win11-build` started on demand (`sudo virsh start`), reached over
  SSH via the Dell (`ProxyJump`).
- Copied the published installer
  `vibecodedemulator-1.3.0-windows-x64-staging.exe` (46,720,549 B — matches the
  catalog) to `C:\AN3\smoke\` and installed it silently (`/S`, exit code 0).
- NSIS installed to the remembered location `C:\AN3\app100`;
  `an3-offline-native.exe` reports **FileVersion 1.3.0** (written at the silent
  install time).
- Launched `C:\AN3\app100\an3-offline-native.exe`:

  ```
  alive_pid=3016 rss_mb=32.3 responding=True
  webview2_processes=6
  ```

  The app stayed alive for the 20 s observation window, reported `Responding`,
  and spawned 6 `msedgewebview2.exe` processes, so the WebView2 UI actually
  initialized. Empty stdout/stderr with redirected output.

- Stopped the app; no `an3-offline-native.exe` remained.
- Shut the VM down gracefully from inside Windows (`shutdown /s`); `virsh`
  reports `shut off`, `Autostart: disable`.

## VERIFIED

- The 1.3.0 Windows installer installs silently and the installed binary is
  version 1.3.0.
- The 1.3.0 Windows app launches, stays alive, is responsive, and initializes
  its WebView2 UI on the build VM.

## UNVERIFIED (explicitly)

- **Any Windows gameplay, rendering, audio, or input.** The VM runs the app over
  SSH in Session 0, has no Vulkan ICD and only GDI Generic OpenGL 1.1, so no
  core can be exercised meaningfully. No fps or visual claim is made.
- Interactive desktop navigation (library, player, Exit Game).
- The install overwrote the VM's previous `C:\AN3\app100` build; the VM is left
  with 1.3.0 installed for future runs.

## Commands (for reproducibility)

```
sudo -n virsh start an3-win11-build            # on the Dell
scp vibecodedemulator-1.3.0-windows-x64-staging.exe an3-win11-build:C:/AN3/smoke/
# install:  Start-Process <exe> -ArgumentList "/S" -Wait
# launch:   Start-Process C:\AN3\app100\an3-offline-native.exe -PassThru
# check:    Get-Process -Name an3-offline-native; Get-Process -Name msedgewebview2
# shutdown: (in Windows) shutdown /s /t 5
```
