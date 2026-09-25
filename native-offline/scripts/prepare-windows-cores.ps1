Param([string]$WorkRoot = '')
$ErrorActionPreference = 'Stop'
$nativeRoot = Split-Path -Parent $PSScriptRoot
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitProcess) { throw 'Windows x64 PowerShell is required.' }
if (-not $WorkRoot) { $WorkRoot = Join-Path $nativeRoot 'work/windows-cores' }
$destination = Join-Path $nativeRoot 'vendor/libretro/windows-x64'
$revision = 'e31759b24e7a4e3899285ff720d7b573ac328ae7'
$source = Join-Path $WorkRoot 'mgba-source'
$build = Join-Path $WorkRoot 'mgba-build'
New-Item -ItemType Directory -Force $WorkRoot, $destination | Out-Null
if (-not (Test-Path "$source/.git")) {
  & git init $source
  if ($LASTEXITCODE) { throw 'Cannot initialize isolated mGBA source.' }
  & git -C $source fetch --depth 1 https://github.com/mgba-emu/mgba.git $revision
  if ($LASTEXITCODE) { throw 'Pinned official mGBA source fetch failed.' }
  & git -C $source checkout --detach FETCH_HEAD
  if ($LASTEXITCODE) { throw 'Pinned source checkout failed.' }
}
if ((& git -C $source rev-parse HEAD) -ne $revision) { throw 'mGBA source differs from the pinned revision.' }
$patch = Join-Path $nativeRoot 'patches/mgba-msvc-dma-log.patch'
$status = @(& git -C $source status --porcelain)
if ($status.Count -eq 0) {
  & git -C $source apply --check $patch
  if ($LASTEXITCODE) { throw 'Pinned MSVC compatibility patch no longer applies.' }
  & git -C $source apply $patch
  if ($LASTEXITCODE) { throw 'MSVC compatibility patch failed.' }
} elseif ($status.Count -ne 1 -or $status[0] -ne ' M src/gba/dma.c') { throw 'Unexpected changes in isolated mGBA source.' }
# Git for Windows may check out CRLF; verify the exact normalized source text.
$patchedText = (Get-Content "$source/src/gba/dma.c" -Raw).Replace("`r`n", "`n")
$patchedHash = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($patchedText))).Replace('-', '').ToLowerInvariant()
if ($patchedHash -ne '04c314e609c18b315e1405f8d345188a8bb70884082434941ebf7e0e5ed764b7') { throw 'MSVC patched source hash mismatch.' }
& cmake -S $source -B $build -G 'Visual Studio 17 2022' -A x64 -DLIBMGBA_ONLY=ON -DBUILD_LIBRETRO=ON -DUSE_FFMPEG=OFF -DUSE_LIBZIP=OFF -DUSE_MINIZIP=OFF -DUSE_EPOXY=OFF -DENABLE_SCRIPTING=OFF
if ($LASTEXITCODE) { throw 'mGBA CMake configuration failed.' }
& cmake --build $build --config Release --target mgba_libretro --parallel 4
if ($LASTEXITCODE) { throw 'Pinned mGBA Windows x64 build failed.' }
Copy-Item "$build/Release/mgba_libretro.dll" "$destination/mgba_libretro.dll" -Force
Copy-Item "$source/LICENSE" "$destination/mGBA-MPL-2.0.txt" -Force

$archive = Join-Path $WorkRoot 'melondsds-v1.3.1-win64.zip'
$url = 'https://github.com/JesseTG/melonds-ds/releases/download/v1.3.1/melondsds_libretro-win32-x86_64-Release.zip'
$expected = 'ec7ff94ae5be3a6308859ea33ec63ac9d9b12d940b2c93d012e9502f71e57681'
if (-not (Test-Path $archive)) {
  & curl.exe -fL --retry 3 -o $archive $url
  if ($LASTEXITCODE) { throw 'Official melonDS DS release download failed.' }
}
if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'melonDS DS official release SHA-256 mismatch.' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archive)
try {
  $coreEntries = @($zip.Entries | Where-Object { $_.Name -eq 'melondsds_libretro.dll' })
  if ($coreEntries.Count -ne 1) { throw 'Expected exactly one Windows melonDS core.' }
  [IO.Compression.ZipFileExtensions]::ExtractToFile($coreEntries[0], "$destination/melondsds_libretro.dll", $true)
} finally { $zip.Dispose() }
# The public source snapshot intentionally excludes platform vendor folders;
# fetch the license from the pinned upstream source revision instead.
$licenseUrl = 'https://raw.githubusercontent.com/JesseTG/melonds-ds/bc4e4b67d2d470d7c682810a1e892cafd6f9082b/LICENSE'
$license = Join-Path $WorkRoot 'melonDS-DS-GPL-3.0-or-later.txt'
if (-not (Test-Path $license)) {
  Invoke-WebRequest -Uri $licenseUrl -OutFile $license
}
if ((Get-FileHash $license -Algorithm SHA256).Hash.ToLowerInvariant() -ne '3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986') { throw 'melonDS license hash mismatch.' }
Copy-Item $license "$destination/melonDS-DS-GPL-3.0-or-later.txt" -Force
$cores = @(
  @{system='gba';engine='mGBA libretro';version='0.11-1-e31759b-dirty';upstreamVersion='0.11-219-e31759b';coreName='mgba_libretro.dll';sourceUrl="https://github.com/mgba-emu/mgba/tree/$revision";sourceRevision=$revision;sourcePatch='patches/mgba-msvc-dma-log.patch';sourcePatchSha256=(Get-FileHash $patch -Algorithm SHA256).Hash.ToLowerInvariant();provenance='Built from pinned source with MSVC x64; logging-only preprocessing compatibility patch';licenseName='mGBA-MPL-2.0.txt'},
  @{system='nds';engine='melonDS DS libretro';version='1.3.1';coreName='melondsds_libretro.dll';sourceUrl='https://github.com/JesseTG/melonds-ds/tree/bc4e4b67d2d470d7c682810a1e892cafd6f9082b';sourceRevision='bc4e4b67d2d470d7c682810a1e892cafd6f9082b';archiveUrl=$url;archiveSha256=$expected;provenance='Official v1.3.1 Windows x64 release; GitHub API digest verified';licenseName='melonDS-DS-GPL-3.0-or-later.txt'}
)
foreach ($core in $cores) {
  $path = Join-Path $destination $core.coreName
  $bytes = [IO.File]::ReadAllBytes($path)
  $offset = [BitConverter]::ToInt32($bytes, 0x3c)
  if ([BitConverter]::ToUInt32($bytes, $offset) -ne 0x4550 -or [BitConverter]::ToUInt16($bytes, $offset + 4) -ne 0x8664) { throw "Not a Windows x64 PE core: $path" }
  $core.coreSha256 = (Get-FileHash $path -Algorithm SHA256).Hash.ToLowerInvariant()
  $core.size = $bytes.Length
  $core.licenseSha256 = (Get-FileHash (Join-Path $destination $core.licenseName) -Algorithm SHA256).Hash.ToLowerInvariant()
}
@{platform='Windows x64';cores=$cores} | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 "$destination/manifest.json"
Write-Output "WINDOWS_CORES=$destination"
