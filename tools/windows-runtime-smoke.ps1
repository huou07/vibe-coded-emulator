param(
  [Parameter(Mandatory = $true)][string]$ArtifactDirectory,
  [Parameter(Mandatory = $true)][string]$ExpectedSourceSha,
  [Parameter(Mandatory = $true)][string]$ArtifactRunId
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$evidence = Join-Path $env:RUNNER_TEMP 'vce-windows-runtime-smoke'
$installRoot = Join-Path $env:RUNNER_TEMP 'vce-windows-runtime-smoke-install'
$installDir = Join-Path $installRoot 'app'
$mainProcess = $null
New-Item -ItemType Directory -Force -Path $evidence, $installRoot | Out-Null

function Write-Evidence([string]$Name, $Value) {
  $Value | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $evidence $Name)
}

function Invoke-An3ctl([string[]]$Arguments) {
  $output = & node tools/an3ctl/an3ctl.mjs @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "an3ctl exited $LASTEXITCODE for: $($Arguments -join ' ')`n$($output -join "`n")"
  }
  return (($output -join "`n") | ConvertFrom-Json)
}

try {
  if ($ExpectedSourceSha -notmatch '^[0-9a-fA-F]{40}$') {
    throw 'Expected source SHA must be a full 40-character Git commit.'
  }
  $labelsPath = Join-Path $ArtifactDirectory 'BUILD_LABELS.txt'
  if (!(Test-Path $labelsPath)) { throw 'Windows package build labels are missing.' }
  $labels = Get-Content $labelsPath -Raw
  if ($labels -notmatch "Source revision:\s*$([regex]::Escape($ExpectedSourceSha))\b") {
    throw 'Windows package source revision does not match the requested SHA.'
  }

  $installer = Get-ChildItem $ArtifactDirectory -File -Filter '*.exe' | Select-Object -First 1
  if (!$installer) { throw 'Windows installer artifact is missing.' }
  $sidecar = "$($installer.FullName).sha256"
  if (!(Test-Path $sidecar)) { throw 'Windows installer SHA-256 sidecar is missing.' }
  $sidecarLine = (Get-Content $sidecar -Raw).Trim()
  if ($sidecarLine -notmatch '^([0-9a-fA-F]{64})\s+(.+)$') {
    throw 'Windows installer sidecar has an unexpected format.'
  }
  $expectedHash = $Matches[1].ToLowerInvariant()
  $sidecarName = [IO.Path]::GetFileName($Matches[2].TrimStart('*', ' '))
  if ($sidecarName -ne $installer.Name) { throw 'Windows installer sidecar names a different file.' }
  $actualHash = (Get-FileHash $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actualHash -ne $expectedHash) { throw 'Windows installer checksum mismatch.' }

  $buildRecord = [ordered]@{
    sourceSha = $ExpectedSourceSha
    artifactRunId = $ArtifactRunId
    installerName = $installer.Name
    installerSha256 = $actualHash
    runnerOS = $env:RUNNER_OS
    osVersion = (Get-CimInstance Win32_OperatingSystem).Caption
  }
  Write-Evidence 'build.json' $buildRecord

  $portOwner = Get-NetTCPConnection -State Listen -LocalPort 38471 -ErrorAction SilentlyContinue
  if ($portOwner) { throw 'Default VCE runtime port 38471 is unexpectedly occupied on the clean runner.' }
  $install = Start-Process -FilePath $installer.FullName `
    -ArgumentList @('/S', "/D=$installDir") -Wait -PassThru
  if ($install.ExitCode -ne 0) { throw "Silent NSIS install exited $($install.ExitCode)." }

  $mainExe = Join-Path $installDir 'an3-offline-native.exe'
  $playerDir = Join-Path $installDir 'runtime/windows-x64'
  $coreDir = Join-Path $playerDir 'libretro'
  $playerExe = Join-Path $playerDir 'an3-native-runtime.exe'
  if (!(Test-Path $mainExe)) { throw "Installed VCE shell is missing: $mainExe" }
  if (!(Test-Path $playerExe)) { throw "Installed Windows GBA/NDS runtime is missing: $playerExe" }
  if (!(Test-Path (Join-Path $coreDir 'mgba_libretro.dll'))) {
    throw 'Installed mGBA core is missing from the bundled libretro directory.'
  }

  $env:AN3_NATIVE_RUNTIME_PORT = '38471'
  $mainProcess = Start-Process -FilePath $mainExe -WorkingDirectory $installDir -PassThru
  $startup = $null
  $deadline = [DateTime]::UtcNow.AddSeconds(60)
  while ([DateTime]::UtcNow -lt $deadline) {
    $mainProcess.Refresh()
    if ($mainProcess.HasExited) { throw "Installed VCE shell exited early with code $($mainProcess.ExitCode)." }
    try {
      $response = Invoke-WebRequest -Uri 'http://127.0.0.1:38471/' -TimeoutSec 3 -UseBasicParsing
      if ($response.StatusCode -eq 200 -and $response.Content -match 'Vibe Coded Emulator') {
        $startup = [ordered]@{
          httpStatus = $response.StatusCode
          expectedTitlePresent = $true
          processId = $mainProcess.Id
          mainWindowHandle = [string]$mainProcess.MainWindowHandle
        }
        break
      }
    } catch { Start-Sleep -Milliseconds 500 }
    Start-Sleep -Milliseconds 500
  }
  if (!$startup) { throw 'Installed VCE shell did not serve the expected UI within 60 seconds.' }
  Write-Evidence 'startup.json' $startup

  $env:PATH = "$playerDir;$env:PATH"
  $env:AN3_PLAYER = $playerExe
  $env:SDL_VIDEODRIVER = 'dummy'
  $env:SDL_AUDIODRIVER = 'dummy'
  $fixture = Join-Path $evidence 'AN3TAPTEST.gba'
  & python tools/testrom/gba_homebrew_test.py $fixture AN3TAPTEST --latch-input
  if ($LASTEXITCODE -ne 0) { throw 'Could not generate the lawful GBA input fixture.' }

  $statePath = Join-Path $evidence 'gba-slot.state'
  $base = @('emulator', 'snapshot', '--rom', $fixture, '--system', 'gba', '--frames', '120', '--player', $playerExe, '--libdir', $coreDir, '--json')
  $baseline = Invoke-An3ctl ($base + @('--save-state', $statePath))
  if (!$baseline.ok -or !$baseline.data.status.stateSaved) { throw 'Installed Windows player failed the baseline Quick Save state export.' }
  $changed = Invoke-An3ctl ($base + @('--seq', 'A@0-1'))
  if (!$changed.ok -or $changed.data.rawHash -eq $baseline.data.rawHash) {
    throw 'Installed Windows player did not change the fixture frame after A input.'
  }
  $restored = Invoke-An3ctl ($base + @('--load-state', $statePath))
  if (!$restored.ok -or !$restored.data.status.stateLoaded -or $restored.data.rawHash -ne $baseline.data.rawHash) {
    throw 'Installed Windows player did not restore the exact saved baseline frame.'
  }

  Write-Evidence 'gameplay.json' ([ordered]@{
    fixtureSha256 = (Get-FileHash $fixture -Algorithm SHA256).Hash.ToLowerInvariant()
    fixtureBytes = (Get-Item $fixture).Length
    playerSha256 = (Get-FileHash $playerExe -Algorithm SHA256).Hash.ToLowerInvariant()
    stateSha256 = (Get-FileHash $statePath -Algorithm SHA256).Hash.ToLowerInvariant()
    stateBytes = (Get-Item $statePath).Length
    system = $baseline.data.status.system
    frames = $baseline.data.status.frames
    baselineRawHash = $baseline.data.rawHash
    changedRawHash = $changed.data.rawHash
    restoredRawHash = $restored.data.rawHash
    stateSaved = $baseline.data.status.stateSaved
    stateLoaded = $restored.data.status.stateLoaded
    audio = 'SDL dummy driver; physical audio UNVERIFIED'
    display = 'SDL dummy driver; physical display/GPU UNVERIFIED'
  })
  Write-Host 'WINDOWS_INSTALL_STARTUP_GBA_INPUT_SAVE_LOAD=GOOD'
} catch {
  Write-Evidence 'failure.json' ([ordered]@{ message = $_.Exception.Message; sourceSha = $ExpectedSourceSha; artifactRunId = $ArtifactRunId })
  throw
} finally {
  if ($mainProcess) {
    $mainProcess.Refresh()
    if (!$mainProcess.HasExited) {
      Stop-Process -Id $mainProcess.Id -Force -ErrorAction SilentlyContinue
      $mainProcess.WaitForExit(5000)
    }
  }
}
