# Windows 11 build VM

Updated 2026-09-13. This documents the persistent `an3-win11-build` guest on
the Debian `huou07` host. The host was not rebooted, its physical LAN was not
bridged, and the staging/production services were not reconfigured.

## Fixed configuration

- `qemu:///system`, Q35 (`pc-q35-10.0`), 8 vCPU, 6 GiB RAM, host-passthrough CPU.
- Windows 11 x64 on the existing sparse 100 GiB qcow2. The installed system
  disk remains SATA; a VirtIO-storage cold-boot experiment was rolled back
  after the guest did not return its display or SSH. The qcow2 was not rebuilt.
- UEFI uses the matching Microsoft OVMF 4M pair:
  `/usr/share/OVMF/OVMF_CODE_4M.ms.fd` and
  `/usr/share/OVMF/OVMF_VARS_4M.ms.fd`, with Secure Boot enabled and a fresh
  matching VARS copy at `/var/lib/libvirt/qemu/nvram/an3-win11-build_VARS.fd`.
- TPM 2.0 is the existing `swtpm`/`tpm-crb` device.
- NIC is VirtIO with the preserved MAC reservation and libvirt NAT network
  `an3-build-nat`: `192.168.251.50`, gateway `192.168.251.1`.
- SPICE listens only on `127.0.0.1`; no VNC/SPICE/RDP endpoint is public.
- Autostart is disabled. Temporary installation CDs are detached and normal
  boot is from the qcow2 disk.

## Boot/media finding

The verified Microsoft ISO is
`Windows11EnterpriseEval-x64.iso` (7,092,807,680 bytes), SHA-256
`a61adeab895ef5a4db436e0a7011c92a2ff17bb0357f58b13bbc4062e535e7b9`, label
`CENA_X64FREE_EN-US_DV9`. It contains `EFI/BOOT/BOOTX64.EFI` as PE32+ x86-64.

The bare-QEMU control run displayed **“Press any key to boot from CD or DVD”**.
That proved the Microsoft EFI optical path was functional; the earlier PXE
timeout was only because no key was delivered before the prompt expired.
The persistent VM was then installed by injecting a space/enter with libvirt
QEMU monitor input. No ISO replacement or activation bypass was used.

## VirtIO media and driver evidence

The official Fedora/Red Hat virtio-win archive ISO already prepared for this VM
is `virtio-win-0.1.302.iso`, SHA-256
`303f7ae40dad495d6ae474fdc571df58958a4dbc5c37a522d80f9a203867949d`, from
`https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/archive-virtio/virtio-win-0.1.302-1/virtio-win-0.1.302.iso`.
The media reports driver version `07/22/2026,100.103.104.30200`.

The separate guest-tools MSI is `virtio-win-gt-x64.msi`, SHA-256
`4f4388468a7ac5286bd1f1924ef02e7281a60a600390a7cfcfd55809efc0889f`, and
reports `NotSigned`. That wrapper result was **not** treated as proof that its
contained drivers were unsigned. The required packages were installed directly
from the official ISO with `pnputil /add-driver ... /install`.

For each installed Windows 11 amd64 package, `Get-AuthenticodeSignature` was
`Valid` and identified the Microsoft Windows Hardware Compatibility Publisher
for the INF, CAT, and SYS files:

| package | result |
| --- | --- |
| NetKVM | Valid; installed and bound to the VirtIO NIC |
| vioscsi | Valid; package staged |
| viostor | Valid; package staged |
| Balloon | Valid; installed on the VirtIO balloon device |
| vioserial | Valid; installed on the VirtIO serial device |
| fwcfg | CAT/SYS Valid; `pnputil` installed `fwcfg.inf` for `ACPI\\QEMU0002` |

`viorng` was not installed because no viorng device is exposed. Secure Boot
remained on throughout. After installing fwcfg and removing the unused LSI
SCSI controller from the VM XML, the final Device Manager/PnP check reports no
non-OK devices relevant to the VM.

## SSH access

The Mac keeps the private key. Only its public key is installed for
`an3builder`; the private key was never copied to Debian or Windows.

`~/.ssh/config` contains:

```sshconfig
Host an3-win11-build
    HostName 192.168.251.50
    User an3builder
    IdentityFile ~/.ssh/an3_codex_ed25519
    IdentitiesOnly yes
    ProxyJump an3-dell
```

The verified path is `ssh an3-win11-build` (Mac -> Dell -> libvirt NAT ->
Windows). OpenSSH Server is running automatically, key authentication works,
and password authentication is disabled in `sshd_config`.

## Toolchain verification

Installed and verified:

- Git for Windows `2.55.0.windows.5`.
- Visual Studio 2022 Build Tools `17.14.40`, C++ x64 tools, and Windows SDK
  `10.0.26100.0` (the SDK directory also retains older SDKs).
- CMake `4.4.3`, Ninja `1.13.2`.
- Rust stable MSVC `rustc/cargo 1.98.1`.
- Node.js `v24.21.0` LTS and npm `11.19.0`.

Trivial x64 MSVC, Rust, CMake/Ninja, Node, npm, and Git checks all passed.
Rustup's bootstrap executable was not Authenticode-signed, so it was accepted
only after matching the official rustup SHA-256; the result is recorded in
`C:\AN3\toolchain-install.txt`. The Build Tools bootstrapper was Authenticode
`Valid`.

## Repository check

The current project source was copied to a lean Windows check tree without the
Mac build cache or release artifacts. `npm ci` completed and the existing Tauri
command built an x64 NSIS installer:

`C:\AN3\repo-check\native-offline\src-tauri\target\release\bundle\nsis\VibeCodedEmulator_0.4.4_x64-setup.exe`

Size was 31,912,290 bytes and SHA-256 was
`55b9eb56b342362868ae2bcd28e1904b6a422fdb0b30daba3a06cb1b44e835d2`.
The installer was run silently and then removed after a GUI launch smoke
attempt. The current repository's own `build-windows-staging.ps1 -VerifyOnly`
still correctly reports `WINDOWS_EXE=BLOCKED`: `VULKAN_SDK` and verified
Windows-native runtime/core assets are not staged. The NSIS check therefore is
packaging evidence only, not a release-valid Windows runtime: the checked-in
bundle configuration still points at Mac arm64 runtime resources, and no real
Vulkan/3DS acceleration was claimed or tested on this integrated-GPU VM.

## Snapshots and operations

Only these useful external disk-only snapshots exist (pflash NVRAM is raw, so
libvirt internal snapshots are unsupported):

- `baseline-clean`: Windows install, signed VirtIO drivers, networking, and
  OpenSSH/key access.
- `an3-dev-ready`: the complete toolchain and repository build check.

The current active disk is the `an3-dev-ready` qcow2 overlay backed by the
original sparse qcow2. Do not delete the backing disk or the OVMF VARS/TPM
state. At the end of the setup run, the guest was shut down through Windows and
`virsh domstate an3-win11-build` was verified as `shut off`; autostart remains
disabled.

## Staging release continuation — 2026-09-13

Official LunarG Vulkan SDK 1.4.357.0 is installed at `C:\VulkanSDK\1.4.357.0`; machine VULKAN_SDK is set and build scripts refresh it into their environment. Installer Authenticode Valid (LunarG), SHA-256 `81f474711e9042f4cd22b31b2f7a8870db2e428b21586fb43dd80150be97310d`. SDK headers and x64 import library verified.

Windows-native x64 mGBA is built from existing source commit e31759b with the documented logging-only MSVC patch; melonDS DS uses official v1.3.1 release archive pinned to its GitHub SHA-256. Both installed core DLLs load and report libretro ABI 1. Native runtime/launch integration is still absent from the source. The VM itself reports no Vulkan ICD (`vkCreateInstance: Found no drivers`, exit 1), GDI Generic OpenGL 1.1.0, Microsoft Basic Display Adapter. It cannot establish real Vulkan/3DS performance.

Frozen-source diagnostic NSIS (`C:\AN3\release-20260913`): 25,264,627 bytes, SHA-256 `e9396f43a75263b457c729ab670b7893840c9729fc8e02f5c2d2ad08f7f9c237`. Clean installed at `C:\AN3\candidate-install-20260913`; actual application PE x64 and Windows-only resources verified. Not staging-download eligible. No interactive desktop user is logged in; a session-0 launch did not create a GUI window, so GUI/settings/save acceptance is unverified. Existing snapshots and VM configuration retained.

## Software Vulkan ICD for 3DS/Vulkan verification — 2026-09-17

The VM exposes only QEMU's emulated standard VGA (`<model type='vga'/>`) with no
GPU passthrough, so Windows binds the inbox "Microsoft Basic Display Adapter"
and registers **no Vulkan ICD**: `HKLM\SOFTWARE\Khronos\Vulkan\Drivers` and its
`WOW6432Node` twin were both absent, and `vulkaninfo` (LunarG SDK 1.4.357.0,
which ships only the loader) failed with
`windows_read_data_files_in_registry: Registry lookup failed` /
`vkCreateInstance: Found no drivers!` / `ERROR_INCOMPATIBLE_DRIVER`.

For 3DS/Vulkan regression testing this is worked around with the **SwiftShader**
software ICD that already ships with Edge/WebView2 — no third-party download:

1. Verify provenance: the `vk_swiftshader.dll` next to the EdgeWebView ICD JSON
   is Authenticode **Valid, signed by Microsoft Corporation**.
2. Stage a stable copy (Edge updates move its own copy):

   ```powershell
   New-Item -ItemType Directory -Force -Path C:\AN3\swiftshader
   $src = "C:\Program Files (x86)\Microsoft\EdgeWebView\Application\<ver>"
   Copy-Item "$src\vk_swiftshader.dll","$src\vk_swiftshader_icd.json" C:\AN3\swiftshader\ -Force
   reg add "HKLM\SOFTWARE\Khronos\Vulkan\Drivers" /v "C:\AN3\swiftshader\vk_swiftshader_icd.json" /t REG_DWORD /d 0 /f
   reg add "HKLM\SOFTWARE\WOW6432Node\Khronos\Vulkan\Drivers" /v "C:\AN3\swiftshader\vk_swiftshader_icd.json" /t REG_DWORD /d 0 /f
   ```

3. Verify: `vulkaninfo --summary` now reports one device —
   `SwiftShader Device (Subzero)`, `driverName = SwiftShader driver`,
   `apiVersion = 1.3.0`, `deviceType = PHYSICAL_DEVICE_TYPE_CPU`.

This is a **software** device: it is sufficient to prove the Vulkan presentation
and 3DS core path, but it establishes nothing about hardware performance. The
registry keys persist across reboots, so the ICD stays installed.

### Session-0 caveat

The VM has no interactive desktop user (session 0 services only; the console
session has no logon). GUI click-through cannot be performed over SSH, and
`PrintWindow` returns blank for the composited Vulkan surface. Input could still
be verified by posting real `WM_KEYDOWN`/`WM_KEYUP` messages (with scancodes) to
the SDL game window, which drives the same `SDL_PollEvent` path as a physical
keyboard. See RG-113.

