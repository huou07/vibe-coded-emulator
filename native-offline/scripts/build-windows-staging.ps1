Param(
  [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'
$nativeRoot = Split-Path -Parent $PSScriptRoot

$runningOnWindows = ($env:OS -eq 'Windows_NT')
if (Get-Variable -Name IsWindows -ErrorAction SilentlyContinue) {
  $runningOnWindows = $runningOnWindows -or [bool]$IsWindows
}
if (-not $runningOnWindows) { throw 'WINDOWS_EXE=BLOCKED: run this deterministic path on a real Windows builder.' }
foreach ($command in @('node', 'npm', 'cargo', 'cmake')) {
  if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
    throw "WINDOWS_EXE=BLOCKED: missing required builder command $command."
  }
}
$env:VULKAN_SDK = if ($env:VULKAN_SDK) { $env:VULKAN_SDK } else { [Environment]::GetEnvironmentVariable('VULKAN_SDK', 'Machine') }
if (-not $env:VULKAN_SDK -or -not (Test-Path "$env:VULKAN_SDK/Include/vulkan/vulkan.h") -or -not (Test-Path "$env:VULKAN_SDK/Lib/vulkan-1.lib")) { throw 'WINDOWS_EXE=BLOCKED: VULKAN_SDK headers and x64 import library are required for the portable Vulkan backend.' }
$coreRoot = Join-Path $nativeRoot 'vendor/libretro/windows-x64'
if (-not (Test-Path "$coreRoot/manifest.json")) {
  throw 'WINDOWS_EXE=BLOCKED: verified Windows GBA/NDS libretro cores have not been staged.'
}
$manifest = Get-Content "$coreRoot/manifest.json" -Raw | ConvertFrom-Json
if ($manifest.platform -ne 'Windows x64') { throw 'WINDOWS_EXE=BLOCKED: wrong native core platform.' }
foreach ($name in @('mgba_libretro.dll', 'melondsds_libretro.dll', 'azahar_libretro.dll')) {
  $entry = @($manifest.cores | Where-Object { $_.coreName -eq $name })
  $path = Join-Path $coreRoot $name
  if ($entry.Count -ne 1 -or -not (Test-Path $path)) { throw "WINDOWS_EXE=BLOCKED: missing unique core $name." }
  $bytes = [IO.File]::ReadAllBytes($path)
  if ($bytes.Length -lt 256 -or $bytes.Length -ne $entry[0].size -or (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry[0].coreSha256) { throw "WINDOWS_EXE=BLOCKED: core integrity failed for $name." }
  $offset = [BitConverter]::ToInt32($bytes, 0x3c)
  if ($offset -lt 0 -or $offset + 6 -gt $bytes.Length -or [BitConverter]::ToUInt32($bytes, $offset) -ne 0x4550 -or [BitConverter]::ToUInt16($bytes, $offset + 4) -ne 0x8664) { throw "WINDOWS_EXE=BLOCKED: $name is not a Windows x64 PE binary." }
}
Write-Output 'WINDOWS_SDK_AND_CORE_INTEGRITY=PASS'
$edenRoot = Join-Path $nativeRoot 'vendor/switch/windows-x64'
if (!(Test-Path "$edenRoot/manifest.json") -or !(Test-Path "$edenRoot/an3_switch_companion.exe")) {
  throw 'WINDOWS_EXE=BLOCKED: verified Eden Windows companion has not been staged.'
}
$edenManifest = Get-Content "$edenRoot/manifest.json" -Raw | ConvertFrom-Json
if ($edenManifest.platform -ne 'Windows x64' -or $edenManifest.bridgeAbi -ne 3) { throw 'WINDOWS_EXE=BLOCKED: wrong Eden Windows manifest.' }
$edenBinary = Join-Path $edenRoot 'an3_switch_companion.exe'
if ((Get-FileHash $edenBinary -Algorithm SHA256).Hash.ToLowerInvariant() -ne $edenManifest.sha256) { throw 'WINDOWS_EXE=BLOCKED: Eden Windows companion integrity failed.' }
Write-Output 'WINDOWS_EDEN_COMPANION_INTEGRITY=PASS'
# Core assets and a source branch alone cannot establish native integration.
# Verify the built player, its dependency closure, and the source it used.
$runtimeRoot = Join-Path $nativeRoot 'vendor/runtime/windows-x64'
if (!(Test-Path "$runtimeRoot/manifest.json")) { throw 'WINDOWS_EXE=BLOCKED: build the portable Windows native runtime first.' }
$runtimeManifest = Get-Content "$runtimeRoot/manifest.json" -Raw | ConvertFrom-Json
if ($runtimeManifest.platform -ne 'Windows x64') { throw 'WINDOWS_EXE=BLOCKED: wrong runtime platform.' }
foreach ($entry in $runtimeManifest.files) {
  $path = Join-Path $runtimeRoot $entry.name
  if (!(Test-Path $path) -or (Get-Item $path).Length -ne $entry.size -or (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) { throw "WINDOWS_EXE=BLOCKED: runtime dependency mismatch: $($entry.name)" }
}
foreach ($entry in $runtimeManifest.sources) {
  $path = Join-Path $nativeRoot $entry.path
  if (!(Test-Path $path) -or (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) { throw "WINDOWS_EXE=BLOCKED: rebuild runtime after source change: $($entry.path)" }
}
foreach ($entry in $manifest.cores) {
  $path = Join-Path "$runtimeRoot/libretro" $entry.coreName
  if (!(Test-Path $path) -or (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.coreSha256) { throw "WINDOWS_EXE=BLOCKED: bundled core differs: $($entry.coreName)" }
}
& "$runtimeRoot/an3-native-runtime.exe" --help
if ($LASTEXITCODE) { throw 'WINDOWS_EXE=BLOCKED: native executable/dependency launch failed.' }
$launcher = Get-Content (Join-Path $nativeRoot 'src-tauri/src/azahar.rs') -Raw
$nativeBuild = Get-Content (Join-Path $nativeRoot 'src-tauri/build.rs') -Raw
if ($launcher -notmatch 'target_os\s*=\s*"windows"' -or $nativeBuild -notmatch 'Ok\("windows"\)') {
  throw 'WINDOWS_EXE=BLOCKED: Windows native surface/audio/input and Rust launch integration are absent. SDK/core assets alone are not runtime acceptance.'
}
Write-Output 'WINDOWS_NATIVE_BUILD_INTEGRITY=PASS (gameplay acceptance is separate)'

# Native tools (node, npm, cargo, tauri) write progress to stderr. PowerShell's
# 'Stop' preference would treat that as a terminating error, so the build steps
# below run with 'Continue' and are validated through $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
Push-Location $nativeRoot
try {
  & npm run prepare-web
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  if ($VerifyOnly) { Write-Output 'WINDOWS_BUILD_PATH=READY'; exit 0 }
  & npm run tauri -- build --target x86_64-pc-windows-msvc --bundles nsis
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  # Derive the artefact name from the desktop version field so a version bump
  # can never publish a stale filename (or pick up a leftover installer).
  $version = (Get-Content (Join-Path $nativeRoot 'src-tauri/tauri.conf.json') -Raw | ConvertFrom-Json).version
  $installer = Join-Path $nativeRoot "src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/VibeCodedEmulator_${version}_x64-setup.exe"
  if (!(Test-Path $installer)) { throw "WINDOWS_EXE=FAILED: NSIS completed without VibeCodedEmulator_${version}_x64-setup.exe." }
  $releaseDir = if ($env:AN3_RELEASE_DIR) { $env:AN3_RELEASE_DIR } else { Join-Path $nativeRoot 'releases' }
  New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
  $candidateName = "vibecodedemulator-${version}-windows-x64-staging.exe"
  $candidate = Join-Path $releaseDir $candidateName
  Copy-Item -LiteralPath $installer -Destination $candidate -Force
  ((Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant() + '  ' + $candidateName) | Set-Content -NoNewline -Encoding ascii "$candidate.sha256"
  Write-Output "WINDOWS_STAGING_EXE=$candidate"
} finally {
  Pop-Location
}
