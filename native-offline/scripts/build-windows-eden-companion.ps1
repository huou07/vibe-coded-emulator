Param(
  [string]$EdenRoot = 'C:\AN3\eden',
  [string]$EdenBuild = 'C:\AN3\eden-build',
  [string]$BridgeRoot = 'C:\AN3\eden-bridge',
  [string]$MsysRoot = 'C:\AN3\msys64'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$commit = if ($env:AN3_EDEN_COMMIT) { $env:AN3_EDEN_COMMIT } else { '7bf95be2c29328a4cfeb8b2384ce34c6fb6d890c' }
$cmake = if (Get-Command cmake -ErrorAction SilentlyContinue) { (Get-Command cmake).Source } else { 'C:\Program Files\CMake\bin\cmake.exe' }
$ninja = if (Get-Command ninja -ErrorAction SilentlyContinue) { (Get-Command ninja).Source } else { 'C:\Program Files\Ninja\ninja.exe' }

if ($env:OS -ne 'Windows_NT') { throw 'WINDOWS_EDEN=BLOCKED: this path must run on the Windows VM.' }
foreach ($path in @($EdenRoot, $BridgeRoot, "$EdenRoot\.git")) {
  if (-not (Test-Path $path)) { throw "WINDOWS_EDEN=BLOCKED: missing $path" }
}
if (-not (Test-Path $cmake)) { throw "WINDOWS_EDEN=BLOCKED: missing CMake at $cmake" }
if (-not (Test-Path $ninja)) { throw "WINDOWS_EDEN=BLOCKED: missing Ninja at $ninja" }

$actualCommit = (& git -C $EdenRoot rev-parse HEAD).Trim()
if ($actualCommit -ne $commit) { throw "WINDOWS_EDEN=BLOCKED: Eden checkout is $actualCommit, expected $commit." }

$env:PATH = "$MsysRoot\ucrt64\bin;$MsysRoot\usr\bin;C:\Program Files\CMake\bin;C:\Program Files\Ninja;$env:PATH"
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
  "-DAN3_EDEN_BRIDGE_DIR=$BridgeRoot",
  '-DENABLE_QT=OFF', '-DYUZU_CMD=OFF', '-DENABLE_LIBUSB=OFF',
  '-DENABLE_WERROR=OFF', '-DENABLE_DEBUG_TOOLS=OFF', '-DENABLE_RESHade=OFF',
  '-DYUZU_USE_BUNDLED_SDL3=ON', '-DYUZU_USE_BUNDLED_FFMPEG=ON',
  '-DYUZU_USE_BUNDLED_OPENSSL=ON', '-DYUZU_DOWNLOAD_TIME_ZONE_DATA=OFF',
  "-DCMAKE_PREFIX_PATH=$MsysRoot/ucrt64",
  "-DCMAKE_INCLUDE_PATH=$MsysRoot/ucrt64/include",
  "-DCMAKE_LIBRARY_PATH=$MsysRoot/ucrt64/lib"
)
& $cmake @configureArgs
if ($LASTEXITCODE -ne 0) { throw 'WINDOWS_EDEN=BLOCKED: CMake configure failed.' }
& $cmake '--build' $EdenBuild '--target' 'an3_switch_companion' '-j' '8'
if ($LASTEXITCODE -ne 0) { throw 'WINDOWS_EDEN=BLOCKED: Eden companion build failed.' }

$binary = Join-Path $EdenBuild 'bin/an3_switch_companion.exe'
if (-not (Test-Path $binary)) { throw "WINDOWS_EDEN=BLOCKED: missing $binary" }
$hash = (Get-FileHash $binary -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "WINDOWS_EDEN_COMPANION=$binary"
Write-Output "WINDOWS_EDEN_SHA256=$hash"
