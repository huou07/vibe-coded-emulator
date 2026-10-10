param(
  [Parameter(Mandatory = $true)][string]$ArtifactDirectory,
  [Parameter(Mandatory = $true)][string]$FixtureDirectory
)

$ErrorActionPreference = 'Stop'
$evidence = Join-Path $env:RUNNER_TEMP 'vce-windows-nds-smoke'
$installDir = Join-Path $evidence 'installed-app'
New-Item -ItemType Directory -Force -Path $evidence, $installDir | Out-Null

if ($env:EXPECTED_SOURCE_SHA -notmatch '^[0-9a-fA-F]{40}$') { throw 'Expected Windows package source SHA is missing or invalid.' }
$labelsPath = Join-Path $ArtifactDirectory 'BUILD_LABELS.txt'
$installer = Get-ChildItem $ArtifactDirectory -File -Filter '*.exe' | Select-Object -First 1
if (!(Test-Path $labelsPath) -or !$installer) { throw 'Exact Windows installer or build labels are missing.' }
if ((Get-Content $labelsPath -Raw) -notmatch "Source revision:\s*$([regex]::Escape($env:EXPECTED_SOURCE_SHA))\b") {
  throw 'Windows package source revision does not match the requested SHA.'
}
$sidecarLine = (Get-Content "$($installer.FullName).sha256" -Raw).Trim()
if ($sidecarLine -notmatch '^([0-9a-fA-F]{64})\s+(.+)$') { throw 'Windows installer checksum sidecar is malformed.' }
$expectedInstallerHash = $Matches[1].ToLowerInvariant()
if ([IO.Path]::GetFileName($Matches[2].TrimStart('*', ' ')) -ne $installer.Name) { throw 'Windows installer sidecar names a different file.' }
$installerHash = (Get-FileHash $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($installerHash -ne $expectedInstallerHash) { throw 'Windows installer checksum mismatch.' }

$install = Start-Process -FilePath $installer.FullName -ArgumentList @('/S', "/D=$installDir") -Wait -PassThru
if ($install.ExitCode -ne 0) { throw "Silent Windows package install exited $($install.ExitCode)." }
foreach ($runningApp in @(Get-CimInstance Win32_Process -Filter "Name = 'an3-offline-native.exe'" |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($installDir, [StringComparison]::OrdinalIgnoreCase) })) {
  $app = Get-Process -Id $runningApp.ProcessId -ErrorAction SilentlyContinue
  if ($app -and $app.MainWindowHandle -ne 0) {
    $null = $app.CloseMainWindow()
    if (!$app.WaitForExit(10000)) {
      & taskkill.exe /PID $app.Id /T /F | Out-Null
      $null = $app.WaitForExit(5000)
    }
  } elseif ($app) {
    & taskkill.exe /PID $app.Id /T /F | Out-Null
    $null = $app.WaitForExit(5000)
  }
}
$portOwner = Get-NetTCPConnection -State Listen -LocalPort 38471 -ErrorAction SilentlyContinue
if ($portOwner) { throw 'The installed shell left the Windows runtime port occupied.' }
$playerDir = Join-Path $installDir 'runtime/windows-x64'
$coreDir = Join-Path $playerDir 'libretro'
$player = Join-Path $playerDir 'an3-native-runtime.exe'
$fixture = Join-Path $FixtureDirectory 'Picking.nds'
if (!(Test-Path $player) -or !(Test-Path (Join-Path $coreDir 'melondsds_libretro.dll'))) {
  throw 'Installed Windows package is missing its player or melonDS DS core.'
}
if (!(Test-Path $fixture)) { throw 'Pinned NDS test fixture is missing.' }
$fixtureHash = (Get-FileHash $fixture -Algorithm SHA256).Hash.ToLowerInvariant()
if ($fixtureHash -ne '3cbd04760c71e49ca2617604515abc7d26aeadd583418f28557d1a9ee7a95544') {
  throw 'NDS test fixture SHA-256 does not match its pinned lawful build.'
}

$env:AN3_OFFLINE_LIBDIR = $coreDir
$env:SDL_AUDIODRIVER = 'dummy'
$storage = Join-Path $evidence 'storage'
$arguments = @(
  'tools/an3ctl/an3ctl.mjs', 'emulator', 'snapshot', '--rom', $fixture,
  '--system', 'nds', '--frames', '120', '--player', $player,
  '--libdir', $coreDir, '--storage', $storage, '--json'
)
$outputLog = Join-Path $evidence 'an3ctl-output.txt'
$output = & node @arguments 2>&1
$output | Set-Content -Encoding utf8 $outputLog
if ($LASTEXITCODE -ne 0) { throw "an3ctl NDS snapshot failed; see $outputLog`n$($output -join "`n")" }
$payload = ($output -join "`n") | ConvertFrom-Json
if (!$payload.ok) { throw "an3ctl returned an error: $($payload | ConvertTo-Json -Compress -Depth 8)" }
$data = $payload.data
$status = $data.status
if ($status.system -ne 'nds' -or $status.frames -ne 120 -or $status.coreFrames -ne 120) {
  throw "Packaged Windows NDS runtime did not complete 120 frames: $($status | ConvertTo-Json -Compress -Depth 5)"
}
if ($status.width -ne 512 -or $status.height -ne 192) { throw "Unexpected NDS output dimensions: $($status.width)x$($status.height)." }
$raw = [IO.File]::ReadAllBytes($data.rawPath)
if ($raw.Length -ne ($status.width * $status.height * 4)) { throw 'NDS raw frame byte length does not match its dimensions.' }
$colors = [Collections.Generic.HashSet[string]]::new()
for ($offset = 0; $offset -lt $raw.Length; $offset += 4) {
  $null = $colors.Add("$($raw[$offset]),$($raw[$offset + 1]),$($raw[$offset + 2])")
}
if ($colors.Count -le 16) { throw "NDS output was blank or nearly uniform ($($colors.Count) RGB colors)." }

$png = Join-Path $evidence 'windows-nds-picking.png'
$rawEvidence = Join-Path $evidence 'windows-nds-picking.rgba'
Copy-Item $data.pngPath $png
Copy-Item $data.rawPath $rawEvidence
$record = [ordered]@{
  artifactRunId = $env:ARTIFACT_RUN_ID
  sourceSha = $env:EXPECTED_SOURCE_SHA
  installerName = $installer.Name
  installerSha256 = $installerHash
  playerSha256 = (Get-FileHash $player -Algorithm SHA256).Hash.ToLowerInvariant()
  coreSha256 = (Get-FileHash (Join-Path $coreDir 'melondsds_libretro.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
  core = 'melonDS DS'
  fixtureSource = 'https://github.com/devkitPro/nds-examples'
  fixtureCommit = 'f1ba715a451c6407f8b0f805999d0153062ff552'
  fixtureSha256 = $fixtureHash
  system = $status.system
  frames = $status.frames
  coreFrames = $status.coreFrames
  width = $status.width
  height = $status.height
  distinctRgbColors = $colors.Count
  pngSha256 = $data.pngHash
  rawSha256 = $data.rawHash
  png = [IO.Path]::GetFileName($png)
  raw = [IO.Path]::GetFileName($rawEvidence)
  audio = 'SDL dummy driver; audible output UNVERIFIED'
  validation = 'Exact installed Windows package; physical display/audio/input and long-session behavior UNVERIFIED'
}
$record | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $evidence 'windows-nds-smoke.json')
