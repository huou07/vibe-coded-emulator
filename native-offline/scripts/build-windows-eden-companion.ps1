Param(
  [string]$EdenRoot = '',
  [string]$EdenBuild = '',
  [string]$BridgeRoot = '',
  [string]$MsysRoot = 'C:\msys64'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$nativeRoot = Split-Path -Parent $PSScriptRoot
$commit = if ($env:AN3_EDEN_COMMIT) { $env:AN3_EDEN_COMMIT } else { '7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c' }
$runnerTemp = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { 'C:\AN3' }
if (-not $EdenRoot) { $EdenRoot = Join-Path $runnerTemp "an3-eden-$commit" }
if (-not $EdenBuild) { $EdenBuild = Join-Path $runnerTemp "an3-eden-build-$commit" }
if (-not $BridgeRoot) { $BridgeRoot = [IO.Path]::GetFullPath((Join-Path $nativeRoot '..\native\eden-bridge')) }
$bridgeCmakeRoot = $BridgeRoot.Replace('\', '/')
$cmake = if (Get-Command cmake -ErrorAction SilentlyContinue) { (Get-Command cmake).Source } else { 'C:\Program Files\CMake\bin\cmake.exe' }
$ninja = if (Get-Command ninja -ErrorAction SilentlyContinue) { (Get-Command ninja).Source } else { 'C:\Program Files\Ninja\ninja.exe' }

if ($env:OS -ne 'Windows_NT') { throw 'WINDOWS_EDEN=BLOCKED: this path must run on the Windows VM.' }
if (-not (Test-Path $BridgeRoot)) { throw "WINDOWS_EDEN=BLOCKED: missing bridge source $BridgeRoot" }
if (-not (Test-Path "$EdenRoot\.git")) {
  if (Test-Path $EdenRoot) {
    $existing = Get-ChildItem -Force $EdenRoot | Select-Object -First 1
    if ($existing) { throw "WINDOWS_EDEN=BLOCKED: refusing nonempty source path without Git metadata: $EdenRoot" }
  } else {
    New-Item -ItemType Directory -Force -Path $EdenRoot | Out-Null
  }
  & git -C $EdenRoot init --quiet
  if ($LASTEXITCODE) { throw 'WINDOWS_EDEN=BLOCKED: cannot initialize isolated Eden source.' }
  & git -C $EdenRoot remote add origin 'https://git.eden-emu.dev/eden-emu/eden.git'
  if ($LASTEXITCODE) { throw 'WINDOWS_EDEN=BLOCKED: cannot configure the pinned Eden source remote.' }
  & git -C $EdenRoot fetch --depth=1 origin $commit
  if ($LASTEXITCODE) { throw 'WINDOWS_EDEN=BLOCKED: pinned Eden source fetch failed.' }
  & git -C $EdenRoot checkout --detach FETCH_HEAD
  if ($LASTEXITCODE) { throw 'WINDOWS_EDEN=BLOCKED: pinned Eden source checkout failed.' }
}
if (-not (Test-Path "$EdenRoot\CMakeLists.txt")) { throw "WINDOWS_EDEN=BLOCKED: missing pinned source at $EdenRoot" }
if (-not (Test-Path $cmake)) { throw "WINDOWS_EDEN=BLOCKED: missing CMake at $cmake" }
if (-not (Test-Path $ninja)) { throw "WINDOWS_EDEN=BLOCKED: missing Ninja at $ninja" }

$actualCommit = (& git -C $EdenRoot rev-parse HEAD).Trim()
if ($actualCommit -ne $commit) { throw "WINDOWS_EDEN=BLOCKED: Eden checkout is $actualCommit, expected $commit." }

$env:PATH = "$MsysRoot\ucrt64\bin;$MsysRoot\usr\bin;C:\Program Files\CMake\bin;C:\Program Files\Ninja;$env:PATH"
$iconvInclude = Join-Path $MsysRoot 'ucrt64\include'
$iconvHeader = Join-Path $iconvInclude 'iconv.h'
$iconvLibrary = Join-Path $MsysRoot 'ucrt64\lib\libiconv.dll.a'
if (-not (Test-Path $iconvHeader)) { throw "WINDOWS_EDEN=BLOCKED: missing MSYS2 UCRT64 iconv header $iconvHeader" }
if (-not (Test-Path $iconvLibrary)) { throw "WINDOWS_EDEN=BLOCKED: missing MSYS2 UCRT64 iconv import library $iconvLibrary" }
$rootCmakePath = Join-Path $EdenRoot 'CMakeLists.txt'
$rootCmake = ([IO.File]::ReadAllText($rootCmakePath)).Replace("`r`n", "`n")
if ($rootCmake -notmatch 'if\(DEFINED AN3_EDEN_BRIDGE_DIR\)') {
  $needle = "`nadd_subdirectory(src)`n"
  if (-not $rootCmake.Contains($needle)) { throw 'WINDOWS_EDEN=BLOCKED: Eden CMake source insertion point changed.' }
  $insert = @'
if(DEFINED AN3_EDEN_BRIDGE_DIR)
    add_subdirectory("${AN3_EDEN_BRIDGE_DIR}/integration" an3_eden_bridge)
endif()
'@
  $rootCmake = $rootCmake.Replace($needle, "$insert$needle")
  [IO.File]::WriteAllText($rootCmakePath, $rootCmake, [Text.UTF8Encoding]::new($false))
}

$configureArgs = @(
  '-S', $EdenRoot, '-B', $EdenBuild, '-G', 'Ninja',
  '-DCMAKE_BUILD_TYPE=Release',
  "-DAN3_EDEN_BRIDGE_DIR=$bridgeCmakeRoot",
  '-DENABLE_QT=OFF', '-DYUZU_CMD=OFF', '-DENABLE_LIBUSB=OFF',
  '-DENABLE_WERROR=OFF', '-DENABLE_DEBUG_TOOLS=OFF', '-DENABLE_RESHade=OFF',
  '-DYUZU_USE_BUNDLED_SDL3=ON', '-DYUZU_USE_BUNDLED_FFMPEG=ON',
  '-DYUZU_USE_BUNDLED_OPENSSL=ON', '-DYUZU_DOWNLOAD_TIME_ZONE_DATA=OFF',
  '-DVulkanHeaders_FORCE_BUNDLED=ON',
  "-DCMAKE_PREFIX_PATH=$MsysRoot/ucrt64",
  "-DCMAKE_INCLUDE_PATH=$iconvInclude",
  "-DCMAKE_LIBRARY_PATH=$MsysRoot/ucrt64/lib",
  "-DICONV_INCLUDE_DIR:PATH=$iconvInclude",
  "-DICONV_LIBRARY:FILEPATH=$iconvLibrary"
)
# CMake and Ninja can emit normal progress/warnings on stderr. Keep their
# output non-terminating and check each native process exit code explicitly.
$ErrorActionPreference = 'Continue'
& $cmake @configureArgs
if ($LASTEXITCODE -ne 0) { throw 'WINDOWS_EDEN=BLOCKED: CMake configure failed.' }
& $cmake '--build' $EdenBuild '--target' 'an3_switch_companion' '-j' '4'
if ($LASTEXITCODE -ne 0) { throw 'WINDOWS_EDEN=BLOCKED: Eden companion build failed.' }

$binary = Join-Path $EdenBuild 'bin/an3_switch_companion.exe'
if (-not (Test-Path $binary)) { throw "WINDOWS_EDEN=BLOCKED: missing $binary" }
$hash = (Get-FileHash $binary -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "WINDOWS_EDEN_COMPANION=$binary"
Write-Output "WINDOWS_EDEN_SHA256=$hash"
