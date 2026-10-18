# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Builds a source-matched, test-only Windows shell executable for UI acceptance.
# The distribution installer is built and uploaded first; this helper writes
# only into the ignored work directory and never replaces that package.
$ErrorActionPreference = 'Stop'
$nativeRoot = Split-Path -Parent $PSScriptRoot
$target = 'x86_64-pc-windows-msvc'
$output = Join-Path $nativeRoot 'work/windows-ui-control-test-shell'
$binary = Join-Path $nativeRoot "src-tauri/target/$target/release/an3-offline-native.exe"
$testBinary = Join-Path $output 'an3-offline-native.exe'

if ($env:OS -ne 'Windows_NT') { throw 'The Windows automation shell must be built on Windows.' }
foreach ($command in @('node', 'cargo')) {
  if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
    throw "Windows automation shell build is missing $command."
  }
}

Push-Location $nativeRoot
try {
  & node scripts/prepare-web.mjs
  if ($LASTEXITCODE -ne 0) { throw 'Could not prepare current-source WebView assets.' }

  # Match the source app while separating its test library and save-data path.
  $env:TAURI_CONFIG = '{"identifier":"space.an3tocom.offline.automation"}'
  & cargo build --release --features ui-control --target $target --manifest-path src-tauri/Cargo.toml
  if ($LASTEXITCODE -ne 0) { throw 'The test-only Windows shell build failed.' }
  if (-not (Test-Path $binary)) { throw "The test-only Windows shell is missing: $binary" }

  $bytes = [IO.File]::ReadAllBytes($binary)
  $marker = [Text.Encoding]::ASCII.GetString($bytes)
  if (-not $marker.Contains('AN3_UI_CONTROL_FILE')) {
    throw 'The Windows automation shell does not contain the test-only ui-control feature.'
  }

  New-Item -ItemType Directory -Force -Path $output | Out-Null
  Copy-Item -LiteralPath $binary -Destination $testBinary -Force
  $version = (Get-Content src-tauri/tauri.conf.json -Raw | ConvertFrom-Json).version
  $hash = (Get-FileHash $testBinary -Algorithm SHA256).Hash.ToLowerInvariant()
  @(
    "Source revision: $env:GITHUB_SHA"
    "App version: $version"
    "Binary SHA-256: $hash"
    'Kind: test-only-ui-control-shell'
  ) | Set-Content -Encoding ascii (Join-Path $output 'BUILD_LABELS.txt')
  "$hash  an3-offline-native.exe" | Set-Content -NoNewline -Encoding ascii (Join-Path $output 'an3-offline-native.exe.sha256')
  Write-Output "WINDOWS_AUTOMATION_SHELL=$testBinary"
} finally {
  Remove-Item Env:TAURI_CONFIG -ErrorAction SilentlyContinue
  Pop-Location
}
