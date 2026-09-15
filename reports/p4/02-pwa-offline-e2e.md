# P4 Android PWA offline E2E

Date: 2026-08-23 (Asia/Ho_Chi_Minh)  
Environment: one authorized physical Android device; private staging topology only.

## Topology and safety

- A loopback-only SSH forward (`127.0.0.1:18092`) plus temporary `adb reverse` opened `http://localhost:18092/offline` in Android Chrome.
- The visible AN3 Offline page reported secure context **Yes** and an app shell cached for the localhost origin.
- The owner selected the authorized 16 MiB GBA test fixture through Android's real Files picker. No CDP file injection was used for the import.
- CDP network emulation was used only for the selected AN3 localhost tab. No device-wide network setting changed.
- No unrelated personal files were enumerated or read.

## Completed E2E evidence

- The real picker selection had one file, the expected GBA type, and the expected fixture size before the AN3 form was submitted.
- The form persisted one local-library record in `an3-arcade-offline`; its GBA file blob retained the expected size after reload.
- The GBA core persisted in `EmulatorJS-core` as a non-empty `mgba` WASM data record.
- With CDP offline emulation active, a service-worker-bypassed uncached health request failed, proving the selected tab's network path was offline.
- Reload while offline restored the cached AN3 shell and the persisted local-library record.
- The local game launched while offline: the offline player reached a ready stage with an EmulatorJS game manager and completed loading state.
- After CDP network restoration, a no-store `/health` request succeeded.

## Cleanup

- Deleted only the verified authorized test fixture from the AN3 offline library; the library was then empty.
- Deleted the temporary Android and Mac fixture files, `adb reverse`, CDP forward, and loopback SSH tunnel.
- The verified cached GBA core remains in browser storage as the offline runtime.

`PWA_SECURE_CONTEXT=PASS`  
`PWA_SHELL_CACHE=PASS`  
`PWA_LOCAL_ROM=PASS`  
`PWA_LIBRARY_PERSISTENCE=PASS`  
`PWA_CORE_CACHE=PASS`  
`PWA_OFFLINE_TRANSITION=PASS`  
`PWA_OFFLINE_RELOAD=PASS`  
`PWA_OFFLINE_GAME_START=PASS`  
`PWA_NETWORK_RECOVERY=PASS`  
`PWA_OFFLINE_E2E=PASS`
