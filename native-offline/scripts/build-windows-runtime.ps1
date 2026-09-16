Param([string]$MsysRoot = 'C:\AN3\msys64')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$nativeRoot = Split-Path -Parent $PSScriptRoot
if ($env:OS -ne 'Windows_NT') { throw 'Windows x64 runtime requires a Windows builder.' }
if (!(Test-Path "$MsysRoot/ucrt64/bin/g++.exe")) { throw 'Install the official MSYS2 UCRT64 SDL2, GTK3, Vulkan and GCC packages first.' }
& node (Join-Path $PSScriptRoot 'generate-player-ui.mjs') --check
if ($LASTEXITCODE) { throw 'Shared player model has generated drift.' }
$env:MSYSTEM = 'UCRT64'
# The MSYS2 toolchain writes compiler warnings to stderr; validate the result
# through $LASTEXITCODE instead of PowerShell's terminating-error preference.
$ErrorActionPreference = 'Continue'
& "$MsysRoot/usr/bin/bash.exe" -l (Join-Path $PSScriptRoot 'build-windows-runtime.sh') $nativeRoot
if ($LASTEXITCODE) { throw 'Portable Windows native runtime compilation failed.' }
$ErrorActionPreference = 'Stop'
& node (Join-Path $PSScriptRoot 'bundle-windows-runtime.mjs') $MsysRoot
if ($LASTEXITCODE) { throw 'Windows native dependency closure verification failed.' }
