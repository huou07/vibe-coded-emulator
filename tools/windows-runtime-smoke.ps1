param(
  [Parameter(Mandatory = $true)][string]$ArtifactDirectory,
  [Parameter(Mandatory = $true)][string]$AutomationDirectory,
  [Parameter(Mandatory = $true)][string]$ExpectedSourceSha,
  [Parameter(Mandatory = $true)][string]$ArtifactRunId
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$evidence = Join-Path $env:RUNNER_TEMP 'vce-windows-runtime-smoke'
$installRoot = Join-Path $env:RUNNER_TEMP 'vce-windows-runtime-smoke-install'
$installDir = Join-Path $installRoot 'app'
$mainProcess = $null
$mainExe = $null
$automationBackup = $null
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

function Get-WindowsPageDiagnostics {
  $script = @'
const tabs = await fetch("http://127.0.0.1:9222/json/list").then(response => response.json());
const page = tabs.find(tab => tab.type === "page" && tab.webSocketDebuggerUrl && new URL(tab.url).origin === "http://127.0.0.1:38471");
if (!page) throw new Error("No WebView2 page is available through local CDP.");
const endpoint = new URL(page.webSocketDebuggerUrl);
if (endpoint.hostname !== "127.0.0.1" && endpoint.hostname !== "localhost" && endpoint.hostname !== "::1") {
  throw new Error("The WebView2 CDP endpoint is not loopback.");
}
const socket = new WebSocket(endpoint);
const value = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => { socket.close(); reject(new Error("Timed out reading the game card ROM id.")); }, 5000);
  socket.addEventListener("error", () => { clearTimeout(timer); reject(new Error("Could not connect to WebView2 CDP.")); }, { once: true });
  socket.addEventListener("open", () => socket.send(JSON.stringify({
    id: 1,
    method: "Runtime.evaluate",
    params: {
      expression: "JSON.stringify({romId: document.querySelector('[data-testid=\\\"game-card\\\"]')?.dataset.romId || null, toastText: (() => { const toast = document.getElementById('toast'); return toast?.classList.contains('show') ? toast.textContent : null; })()})",
      returnByValue: true
    }
  })));
  socket.addEventListener("message", event => {
    const message = JSON.parse(String(event.data));
    if (message.id !== 1) return;
    clearTimeout(timer);
    socket.close();
    if (message.error) reject(new Error(message.error.message || "CDP evaluation failed."));
    else resolve(message.result?.result?.value ?? null);
  });
});
if (typeof value !== "string") throw new Error("Could not read the native page diagnostics.");
const diagnostic = JSON.parse(value);
if (typeof diagnostic.romId !== "string" || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(diagnostic.romId)) {
  throw new Error("The imported game card has no valid native ROM id.");
}
process.stdout.write(JSON.stringify(diagnostic));
'@
  $output = & node --input-type=module -e $script
  if ($LASTEXITCODE -ne 0) { throw "Could not read native page diagnostics through CDP: $($output -join "`n")" }
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

  $automationLabelsPath = Join-Path $AutomationDirectory 'BUILD_LABELS.txt'
  $automationExe = Join-Path $AutomationDirectory 'an3-offline-native.exe'
  $automationSidecar = "$automationExe.sha256"
  if (!(Test-Path $automationLabelsPath) -or !(Test-Path $automationExe) -or !(Test-Path $automationSidecar)) {
    throw 'Source-matched Windows UI-control test shell or its labels/checksum are missing.'
  }
  $automationLabels = Get-Content $automationLabelsPath -Raw
  if ($automationLabels -notmatch "Source revision:\s*$([regex]::Escape($ExpectedSourceSha))\b") {
    throw 'Windows UI-control test shell source revision does not match the requested SHA.'
  }
  $automationVersionMatch = [regex]::Match($automationLabels, 'App version:\s*([^\r\n]+)')
  if (-not $automationVersionMatch.Success) { throw 'Windows UI-control test shell version label is missing.' }
  if ($automationLabels -notmatch 'Kind:\s*test-only-ui-control-shell') {
    throw 'Windows UI-control executable is not labeled as a test-only shell.'
  }
  $automationHash = (Get-FileHash $automationExe -Algorithm SHA256).Hash.ToLowerInvariant()
  $automationSidecarLine = (Get-Content $automationSidecar -Raw).Trim()
  $automationSidecarMatch = [regex]::Match($automationSidecarLine, '^([0-9a-fA-F]{64})\s+(.+)$')
  if (-not $automationSidecarMatch.Success -or $automationSidecarMatch.Groups[1].Value.ToLowerInvariant() -ne $automationHash -or [IO.Path]::GetFileName($automationSidecarMatch.Groups[2].Value.TrimStart('*', ' ')) -ne [IO.Path]::GetFileName($automationExe)) {
    throw 'Windows UI-control shell checksum sidecar does not match its executable.'
  }

  $buildRecord = [ordered]@{
    sourceSha = $ExpectedSourceSha
    artifactRunId = $ArtifactRunId
    installerName = $installer.Name
    installerSha256 = $actualHash
    automationShellSha256 = $automationHash
    appVersion = $automationVersionMatch.Groups[1].Value.Trim()
    runnerOS = $env:RUNNER_OS
    osVersion = (Get-CimInstance Win32_OperatingSystem).Caption
  }
  Write-Evidence 'build.json' $buildRecord

  $portOwner = Get-NetTCPConnection -State Listen -LocalPort 38471 -ErrorAction SilentlyContinue
  if ($portOwner) { throw 'Default VCE runtime port 38471 is unexpectedly occupied on the clean runner.' }
  $debugPortOwner = Get-NetTCPConnection -State Listen -LocalPort 9222 -ErrorAction SilentlyContinue
  if ($debugPortOwner) { throw 'WebView2 test debug port 9222 is unexpectedly occupied on the clean runner.' }
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

  $distributionShellSha = (Get-FileHash $mainExe -Algorithm SHA256).Hash.ToLowerInvariant()
  $distributionShellBytes = [IO.File]::ReadAllBytes($mainExe)
  if ([Text.Encoding]::ASCII.GetString($distributionShellBytes).Contains('AN3_UI_CONTROL_FILE')) {
    throw 'The shipped Windows app unexpectedly includes the test-only ui-control feature.'
  }
  $automationBackup = "$mainExe.distribution-backup"
  Copy-Item -LiteralPath $mainExe -Destination $automationBackup
  Copy-Item -LiteralPath $automationExe -Destination $mainExe -Force
  if ((Get-FileHash $mainExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $automationHash) {
    throw 'The source-matched Windows UI-control shell was not installed into the isolated package copy.'
  }

  $fixture = Join-Path $evidence 'AN3TAPTEST.gba'
  & python tools/testrom/gba_homebrew_test.py $fixture AN3TAPTEST --latch-input
  if ($LASTEXITCODE -ne 0) { throw 'Could not generate the lawful GBA UI-import fixture.' }
  $fixtureHash = (Get-FileHash $fixture -Algorithm SHA256).Hash.ToLowerInvariant()
  $env:AN3_UI_TEST_ROM = $fixture

  $env:AN3_NATIVE_RUNTIME_PORT = '38471'
  $env:AN3_WINDOWS_CDP_LOCAL = '1'
  $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-address=127.0.0.1 --remote-debugging-port=9222'
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

  $uiTree = $null
  $deadline = [DateTime]::UtcNow.AddSeconds(60)
  while ([DateTime]::UtcNow -lt $deadline) {
    $mainProcess.Refresh()
    if ($mainProcess.HasExited) { throw "Installed VCE shell exited before UI control became ready (code $($mainProcess.ExitCode))." }
    try {
      $uiTree = Invoke-An3ctl @('ui', 'tree', '--target', 'windows', '--limit', '120', '--json')
      if ($uiTree.data.section -eq 'play') { break }
    } catch { Start-Sleep -Milliseconds 500 }
    Start-Sleep -Milliseconds 500
  }
  if (!$uiTree -or $uiTree.data.section -ne 'play') { throw 'an3ctl could not attach to the installed Windows shell through local WebView2 CDP.' }
  $debugListener = Get-NetTCPConnection -State Listen -LocalPort 9222 -ErrorAction SilentlyContinue
  if (!$debugListener -or @($debugListener | Where-Object { $_.LocalAddress -notin @('127.0.0.1', '::1') }).Count -gt 0) {
    throw 'WebView2 CDP did not remain bound exclusively to a loopback address.'
  }

  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--testid', 'nav-library', '--json')
  $library = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'game-grid', '--json')
  if (!$library.data.node.visible -or $library.data.node.name -notmatch 'No games on this device') {
    throw 'The installed shell Library did not show its fresh empty state.'
  }
  $librarySection = (Invoke-An3ctl @('ui', 'tree', '--target', 'windows', '--limit', '120', '--json')).data.section
  if ($librarySection -ne 'library') { throw "Library navigation ended on '$librarySection'." }

  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--testid', 'nav-settings', '--json')
  $settings = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'game-settings', '--json')
  if (!$settings.data.node.visible) { throw 'The installed shell Settings page did not show Game Settings.' }
  $settingsSection = (Invoke-An3ctl @('ui', 'tree', '--target', 'windows', '--limit', '120', '--json')).data.section
  if ($settingsSection -ne 'settings') { throw "Settings navigation ended on '$settingsSection'." }

  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--testid', 'nav-about', '--json')
  $aboutVersion = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--css', '[data-app-version]', '--json')
  if (!$aboutVersion.data.node.visible -or !$aboutVersion.data.node.name -or $aboutVersion.data.node.name -match '__AN3_VERSION__') {
    throw 'The installed shell About page did not show a substituted app version.'
  }
  if ($aboutVersion.data.node.name.Trim() -ne $automationVersionMatch.Groups[1].Value.Trim()) {
    throw 'The installed package About version does not match the source-matched test shell.'
  }
  $aboutSection = (Invoke-An3ctl @('ui', 'tree', '--target', 'windows', '--limit', '120', '--json')).data.section
  if ($aboutSection -ne 'about') { throw "About navigation ended on '$aboutSection'." }
  Write-Evidence 'ui.json' ([ordered]@{
    cdpAddress = '127.0.0.1:9222'
    sections = @('play', $librarySection, $settingsSection, $aboutSection)
    emptyLibraryVisible = $true
    gameSettingsVisible = $true
    appVersion = $aboutVersion.data.node.name
  })

  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--testid', 'nav-play', '--json')
  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--testid', 'open-rom', '--json')
  $gameCard = $null
  $deadline = [DateTime]::UtcNow.AddSeconds(30)
  while ([DateTime]::UtcNow -lt $deadline) {
    try {
      $gameCard = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'game-card', '--json')
      if ($gameCard.data.node.visible) { break }
    } catch { Start-Sleep -Milliseconds 400 }
    Start-Sleep -Milliseconds 400
  }
  if (!$gameCard -or !$gameCard.data.node.visible -or $gameCard.data.node.name -notmatch 'AN3TAPTEST') {
    throw 'The real Windows shell import flow did not add the generated GBA fixture to Library.'
  }
  $nativeRomDirectory = Join-Path (Join-Path $env:APPDATA 'space.an3tocom.offline.automation') 'an3-roms'
  $nativeRomFiles = @(
    Get-ChildItem -LiteralPath $nativeRomDirectory -File -ErrorAction SilentlyContinue |
      ForEach-Object { [ordered]@{
        name = $_.Name
        bytes = $_.Length
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
      }}
  )
  Write-Evidence 'native-rom-storage.json' ([ordered]@{
    directory = '%APPDATA%\space.an3tocom.offline.automation\an3-roms'
    fixtureSha256 = (Get-FileHash $fixture -Algorithm SHA256).Hash.ToLowerInvariant()
    files = $nativeRomFiles
  })
  $pageDiagnostics = Get-WindowsPageDiagnostics
  $gameCardRomId = $pageDiagnostics.romId
  Write-Evidence 'game-card-rom-id.json' ([ordered]@{
    romId = $gameCardRomId
    storedRomIds = @($nativeRomFiles | Where-Object { $_.name -match '^[0-9a-fA-F-]{36}\.' } | ForEach-Object { $_.name.Substring(0, 36) })
  })
  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--testid', 'game-launch', '--json')
  $nativeStatus = $null
  $nativeStatusQueryError = $null
  $deadline = [DateTime]::UtcNow.AddSeconds(50)
  while ([DateTime]::UtcNow -lt $deadline) {
    try {
      $nativeStatus = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'native-status', '--json')
      $nativeStatusQueryError = $null
      if ($nativeStatus.data.node.state -in @('running', 'error')) { break }
    } catch {
      $nativeStatusQueryError = $_.Exception.Message
      Start-Sleep -Milliseconds 500
    }
    Start-Sleep -Milliseconds 500
  }
  $nativeLaunchState = if ($nativeStatus) { $nativeStatus.data.node.state } else { 'unavailable' }
  $nativeLaunchDetail = if ($nativeStatus) { $nativeStatus.data.node.name } else { '' }
  $launchToastDetail = (Get-WindowsPageDiagnostics).toastText
  Write-Evidence 'launch.json' ([ordered]@{
    sourceSha = $ExpectedSourceSha
    appVersion = $automationVersionMatch.Groups[1].Value.Trim()
    launchStatus = $nativeLaunchState
    launchDetail = $nativeLaunchDetail
    launchToastDetail = $launchToastDetail
    lastStatusQueryError = $nativeStatusQueryError
  })
  if (!$nativeStatus -or $nativeStatus.data.node.state -ne 'running') {
    throw "The shell game card did not start the bundled Windows runtime (state=$nativeLaunchState; detail=$nativeLaunchDetail; queryError=$nativeStatusQueryError)."
  }
  $runtimeProcess = $null
  $runtimeWindow = $null
  $deadline = [DateTime]::UtcNow.AddSeconds(20)
  while ([DateTime]::UtcNow -lt $deadline) {
    $runtimeProcess = Get-CimInstance Win32_Process -Filter "Name = 'an3-native-runtime.exe'" |
      Where-Object { $_.ParentProcessId -eq $mainProcess.Id } | Select-Object -First 1
    if ($runtimeProcess) {
      $runtimeWindow = Get-Process -Id $runtimeProcess.ProcessId -ErrorAction SilentlyContinue
      if ($runtimeWindow -and $runtimeWindow.MainWindowHandle -ne 0) { break }
    }
    Start-Sleep -Milliseconds 500
  }
  if (!$runtimeProcess -or !$runtimeWindow -or $runtimeWindow.MainWindowHandle -eq 0) {
    throw 'The shell did not retain a live bundled player process with its native game window.'
  }
  Write-Evidence 'shell-game.json' ([ordered]@{
    sourceSha = $ExpectedSourceSha
    appVersion = $automationVersionMatch.Groups[1].Value.Trim()
    installerSha256 = $actualHash
    distributionShellSha256 = $distributionShellSha
    automationShellSha256 = $automationHash
    fixtureSha256 = $fixtureHash
    fixtureBytes = (Get-Item $fixture).Length
    importedGameCard = $gameCard.data.node.name
    importHandler = 'real pick_and_import_native_rom handler with test-only AN3_UI_TEST_ROM pre-answer'
    launchStatus = $nativeStatus.data.node.state
    playerImage = $runtimeProcess.Name
    playerParentProcessId = $runtimeProcess.ParentProcessId
    playerWindowHandle = [string]$runtimeWindow.MainWindowHandle
    playerWindowTitle = $runtimeWindow.MainWindowTitle
    videoFrameContent = 'Not captured in this shell-launch check; direct-player frame/input/save-state probe follows separately.'
  })

  $playerProcessId = [int]$runtimeProcess.ProcessId
  $null = $mainProcess.CloseMainWindow()
  if (!$mainProcess.WaitForExit(10000)) {
    & taskkill.exe /PID $mainProcess.Id /T /F | Out-Null
    $mainProcess.WaitForExit(5000) | Out-Null
    throw 'The installed Windows shell did not close cleanly after the game launch check.'
  }
  $mainProcess.Refresh()
  if (!$mainProcess.HasExited) { throw 'The installed Windows shell remained open after its close request.' }
  $deadline = [DateTime]::UtcNow.AddSeconds(10)
  do {
    $childStillRunning = Get-Process -Id $playerProcessId -ErrorAction SilentlyContinue
    if (-not $childStillRunning) { break }
    Start-Sleep -Milliseconds 250
  } while ([DateTime]::UtcNow -lt $deadline)
  if ($childStillRunning) {
    & taskkill.exe /PID $playerProcessId /T /F | Out-Null
    throw 'Closing the installed Windows shell left its native game process running.'
  }
  Write-Evidence 'shell-shutdown.json' ([ordered]@{
    shellClosedCleanly = $true
    nativePlayerExited = $true
    sourceSha = $ExpectedSourceSha
  })
  $mainProcess = $null
  Remove-Item Env:AN3_UI_TEST_ROM -ErrorAction SilentlyContinue
  Move-Item -LiteralPath $automationBackup -Destination $mainExe -Force

  $env:PATH = "$playerDir;$env:PATH"
  $env:AN3_PLAYER = $playerExe
  $env:SDL_VIDEODRIVER = 'dummy'
  $env:SDL_AUDIODRIVER = 'dummy'
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
  Write-Host 'WINDOWS_INSTALL_SHELL_IMPORT_LAUNCH_AND_DIRECT_PLAYER_INPUT_SAVE_LOAD=GOOD'
} catch {
  Write-Evidence 'failure.json' ([ordered]@{ message = $_.Exception.Message; sourceSha = $ExpectedSourceSha; artifactRunId = $ArtifactRunId })
  throw
} finally {
  if ($mainProcess) {
    $mainProcess.Refresh()
    if (!$mainProcess.HasExited) {
      $null = $mainProcess.CloseMainWindow()
      if (!$mainProcess.WaitForExit(10000)) {
        & taskkill.exe /PID $mainProcess.Id /T /F | Out-Null
        $mainProcess.WaitForExit(5000)
      }
    }
  }
  Remove-Item Env:AN3_UI_TEST_ROM -ErrorAction SilentlyContinue
  if ($automationBackup -and $mainExe -and (Test-Path $automationBackup)) {
    Move-Item -LiteralPath $automationBackup -Destination $mainExe -Force
  }
}
