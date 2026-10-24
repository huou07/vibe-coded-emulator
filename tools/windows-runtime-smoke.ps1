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
$distributionProcess = $null
$mainExe = $null
$automationTestExe = $null
$sramStorage = $null
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

function Capture-NativePlayerWindow([int]$ProcessId, [string]$ExpectedColor = 'blue') {
  Add-Type -AssemblyName System.Drawing
  if (-not ('An3WindowCapture' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class An3WindowCapture {
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  public class WindowInfo {
    public IntPtr Handle;
    public string Title;
    public int Left;
    public int Top;
    public int Right;
    public int Bottom;
  }
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int maxCount);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, IntPtr extraInfo);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int command);
  public static WindowInfo[] GetWindowsForProcess(int targetProcessId) {
    var result = new List<WindowInfo>();
    EnumWindows((hWnd, lParam) => {
      uint ownerProcessId;
      GetWindowThreadProcessId(hWnd, out ownerProcessId);
      if (ownerProcessId != (uint)targetProcessId || !IsWindowVisible(hWnd)) return true;
      RECT rect;
      if (!GetWindowRect(hWnd, out rect) || rect.Right <= rect.Left || rect.Bottom <= rect.Top) return true;
      var title = new StringBuilder(512);
      GetWindowText(hWnd, title, title.Capacity);
      result.Add(new WindowInfo { Handle=hWnd, Title=title.ToString(), Left=rect.Left, Top=rect.Top, Right=rect.Right, Bottom=rect.Bottom });
      return true;
    }, IntPtr.Zero);
    return result.ToArray();
  }
}
'@
  }
  $windows = @([An3WindowCapture]::GetWindowsForProcess($ProcessId))
  if ($windows.Count -eq 0) { throw 'The native player process has no visible top-level windows to capture.' }
  $null = [An3WindowCapture]::ShowWindow($windows[0].Handle, 9)
  $null = [An3WindowCapture]::SetForegroundWindow($windows[0].Handle)
  Start-Sleep -Milliseconds 750
  $candidates = @()
  $index = 0
  foreach ($window in $windows) {
    $width = $window.Right - $window.Left
    $height = $window.Bottom - $window.Top
    if ($width -lt 240 -or $height -lt 160) { continue }
    $null = [An3WindowCapture]::ShowWindow($window.Handle, 9)
    $null = [An3WindowCapture]::SetForegroundWindow($window.Handle)
    Start-Sleep -Milliseconds 300
    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $screenshot = "native-player-$ExpectedColor-window-$index.png"
    try {
      $graphics.CopyFromScreen($window.Left, $window.Top, 0, 0, $bitmap.Size, [System.Drawing.CopyPixelOperation]::SourceCopy)
      $bitmap.Save((Join-Path $evidence $screenshot), [System.Drawing.Imaging.ImageFormat]::Png)
      $pixel = $bitmap.GetPixel([int]($width / 2), [int]($height / 2))
    } finally {
      $graphics.Dispose()
      $bitmap.Dispose()
    }
    $candidate = [ordered]@{
      handle = [string]$window.Handle
      title = $window.Title
      width = $width
      height = $height
      centerPixel = [ordered]@{ red = $pixel.R; green = $pixel.G; blue = $pixel.B }
      screenshot = $screenshot
    }
    $candidates += $candidate
    $matchesExpectedColor = if ($ExpectedColor -eq 'red') {
      $pixel.R -gt 96 -and $pixel.R -gt ($pixel.G + 32) -and $pixel.R -gt ($pixel.B + 32)
    } else {
      $pixel.B -gt 96 -and $pixel.B -gt ($pixel.R + 32) -and $pixel.B -gt ($pixel.G + 32)
    }
    if ($matchesExpectedColor) {
      return [ordered]@{
        status = 'GOOD'
        expectedColor = $ExpectedColor
        width = $width
        height = $height
        centerPixel = $candidate.centerPixel
        screenshot = $screenshot
        candidateWindows = $candidates
      }
    }
    $index++
  }
  $diagnosticsScreenshot = Capture-RendererDiagnostics $windows
  throw "No visible native player window displayed the fixture's $ExpectedColor frame; renderer diagnostics screenshot=$diagnosticsScreenshot windows=$(ConvertTo-Json -InputObject $candidates -Compress -Depth 5)"
}

function Save-DesktopScreenshot([string]$Name) {
  Add-Type -AssemblyName System.Drawing
  Add-Type -AssemblyName System.Windows.Forms
  $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  try {
    $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $bitmap.Save((Join-Path $evidence $Name), [System.Drawing.Imaging.ImageFormat]::Png)
  } finally {
    $graphics.Dispose()
    $bitmap.Dispose()
  }
}

function Capture-RendererDiagnostics($Windows) {
  $controls = $Windows | Where-Object { $_.Title -match 'Controls$' } | Select-Object -First 1
  if (-not $controls) { return $null }
  $null = [An3WindowCapture]::ShowWindow($controls.Handle, 9)
  $null = [An3WindowCapture]::SetForegroundWindow($controls.Handle)
  Start-Sleep -Milliseconds 300
  $x = [int]($controls.Left + 0.75 * ($controls.Right - $controls.Left))
  $y = [int]($controls.Top + 0.23 * ($controls.Bottom - $controls.Top))
  $null = [An3WindowCapture]::SetCursorPos($x, $y)
  [An3WindowCapture]::mouse_event(2, 0, 0, 0, [IntPtr]::Zero)
  [An3WindowCapture]::mouse_event(4, 0, 0, 0, [IntPtr]::Zero)
  Start-Sleep -Milliseconds 500
  $width = $controls.Right - $controls.Left
  $height = $controls.Bottom - $controls.Top
  $bitmap = New-Object System.Drawing.Bitmap($width, $height)
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  try {
    $graphics.CopyFromScreen($controls.Left, $controls.Top, 0, 0, $bitmap.Size, [System.Drawing.CopyPixelOperation]::SourceCopy)
    $bitmap.Save((Join-Path $evidence 'renderer-diagnostics.png'), [System.Drawing.Imaging.ImageFormat]::Png)
  } finally {
    $graphics.Dispose()
    $bitmap.Dispose()
  }
  $x = [int]($controls.Left + 0.15 * ($controls.Right - $controls.Left))
  $null = [An3WindowCapture]::SetCursorPos($x, $y)
  [An3WindowCapture]::mouse_event(2, 0, 0, 0, [IntPtr]::Zero)
  [An3WindowCapture]::mouse_event(4, 0, 0, 0, [IntPtr]::Zero)
  Start-Sleep -Milliseconds 500
  $bitmap = New-Object System.Drawing.Bitmap($width, $height)
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  try {
    $graphics.CopyFromScreen($controls.Left, $controls.Top, 0, 0, $bitmap.Size, [System.Drawing.CopyPixelOperation]::SourceCopy)
    $bitmap.Save((Join-Path $evidence 'renderer-graphics.png'), [System.Drawing.Imaging.ImageFormat]::Png)
  } finally {
    $graphics.Dispose()
    $bitmap.Dispose()
  }
  return 'renderer-diagnostics.png,renderer-graphics.png'
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
  $installerStartedApp = $false
  foreach ($installedProcess in @(Get-CimInstance Win32_Process -Filter "Name = 'an3-offline-native.exe'" |
      Where-Object { $_.ExecutablePath -and $_.ExecutablePath.Equals($mainExe, [StringComparison]::OrdinalIgnoreCase) })) {
    $installerStartedApp = $true
    $runningApp = Get-Process -Id $installedProcess.ProcessId -ErrorAction SilentlyContinue
    if ($runningApp -and $runningApp.MainWindowHandle -ne 0) {
      $null = $runningApp.CloseMainWindow()
      if (!$runningApp.WaitForExit(10000)) {
        & taskkill.exe /PID $runningApp.Id /T /F | Out-Null
        $runningApp.WaitForExit(5000) | Out-Null
      }
    } elseif ($runningApp) {
      & taskkill.exe /PID $runningApp.Id /T /F | Out-Null
      $runningApp.WaitForExit(5000) | Out-Null
    }
    if (Get-Process -Id $installedProcess.ProcessId -ErrorAction SilentlyContinue) {
      throw 'The freshly installed VCE shell did not exit before the package smoke.'
    }
  }
  $portOwner = Get-NetTCPConnection -State Listen -LocalPort 38471 -ErrorAction SilentlyContinue
  if ($portOwner) { throw 'The fresh install left port 38471 occupied before the package smoke.' }
  $playerDir = Join-Path $installDir 'runtime/windows-x64'
  $coreDir = Join-Path $playerDir 'libretro'
  $playerExe = Join-Path $playerDir 'an3-native-runtime.exe'
  if (!(Test-Path $mainExe)) { throw "Installed VCE shell is missing: $mainExe" }
  if (!(Test-Path $playerExe)) { throw "Installed Windows GBA/NDS runtime is missing: $playerExe" }
  if (!(Test-Path (Join-Path $coreDir 'mgba_libretro.dll'))) {
    throw 'Installed mGBA core is missing from the bundled libretro directory.'
  }

  # The player loads vulkan-1.dll from its own directory or System32 only. A
  # real machine gets that loader from its GPU driver; this runner has none, so
  # the smoke adds the ephemeral package loader beside the player and records it.
  # It is not part of the shipped artifact.
  if ($env:AN3_TEST_VULKAN_LOADER) {
    if (!(Test-Path -LiteralPath $env:AN3_TEST_VULKAN_LOADER)) {
      throw "Test Vulkan loader is unavailable: $env:AN3_TEST_VULKAN_LOADER"
    }
    $loaderTarget = Join-Path $playerDir 'vulkan-1.dll'
    Copy-Item -LiteralPath $env:AN3_TEST_VULKAN_LOADER -Destination $loaderTarget -Force
    Write-Evidence 'test-vulkan-loader.json' ([ordered]@{
      source = $env:AN3_TEST_VULKAN_LOADER
      sourceSha256 = (Get-FileHash -LiteralPath $env:AN3_TEST_VULKAN_LOADER -Algorithm SHA256).Hash.ToLowerInvariant()
      installed = $loaderTarget
      installedSha256 = (Get-FileHash -LiteralPath $loaderTarget -Algorithm SHA256).Hash.ToLowerInvariant()
      note = 'ephemeral test dependency beside the installed player; not shipped'
    })
  }

  $distributionShellSha = (Get-FileHash $mainExe -Algorithm SHA256).Hash.ToLowerInvariant()
  $distributionShellBytes = [IO.File]::ReadAllBytes($mainExe)
  if ([Text.Encoding]::ASCII.GetString($distributionShellBytes).Contains('AN3_UI_CONTROL_FILE')) {
    throw 'The shipped Windows app unexpectedly includes the test-only ui-control feature.'
  }

  $env:AN3_NATIVE_RUNTIME_PORT = '38471'
  $env:AN3_WINDOWS_CDP_LOCAL = '1'
  $env:SDL_AUDIODRIVER = 'dummy'
  $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-address=127.0.0.1 --remote-debugging-port=9222'
  $distributionProcess = Start-Process -FilePath $mainExe -WorkingDirectory $installDir -PassThru
  $distributionStartup = $null
  $deadline = [DateTime]::UtcNow.AddSeconds(60)
  while ([DateTime]::UtcNow -lt $deadline) {
    $distributionProcess.Refresh()
    if ($distributionProcess.HasExited) { throw "Packaged VCE shell exited early with code $($distributionProcess.ExitCode)." }
    try {
      $response = Invoke-WebRequest -Uri 'http://127.0.0.1:38471/' -TimeoutSec 3 -UseBasicParsing
      if ($response.StatusCode -eq 200 -and $response.Content -match 'Vibe Coded Emulator') {
        $distributionStartup = $true
        break
      }
    } catch { Start-Sleep -Milliseconds 500 }
    Start-Sleep -Milliseconds 500
  }
  if (!$distributionStartup) { throw 'Packaged VCE shell did not serve the expected UI within 60 seconds.' }

  $distributionTree = $null
  $deadline = [DateTime]::UtcNow.AddSeconds(60)
  while ([DateTime]::UtcNow -lt $deadline) {
    $distributionProcess.Refresh()
    if ($distributionProcess.HasExited) { throw "Packaged VCE shell exited before CDP became ready (code $($distributionProcess.ExitCode))." }
    try {
      $distributionTree = Invoke-An3ctl @('ui', 'tree', '--target', 'windows', '--limit', '120', '--json')
      if ($distributionTree.data.section -eq 'play') { break }
    } catch { Start-Sleep -Milliseconds 500 }
    Start-Sleep -Milliseconds 500
  }
  if (!$distributionTree -or $distributionTree.data.section -ne 'play') { throw 'an3ctl could not attach to the packaged Windows shell through loopback WebView2 CDP.' }
  $debugListener = Get-NetTCPConnection -State Listen -LocalPort 9222 -ErrorAction SilentlyContinue
  if (!$debugListener -or @($debugListener | Where-Object { $_.LocalAddress -notin @('127.0.0.1', '::1') }).Count -gt 0) {
    throw 'Packaged WebView2 CDP did not remain bound exclusively to a loopback address.'
  }

  $distributionSections = @('play')
  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--css', '.native-sidebar [data-nav="library"]', '--json')
  $library = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'game-grid', '--json')
  if (!$library.data.node.visible -or $library.data.node.name -notmatch 'No games on this device') {
    throw 'The packaged shell Library did not show its fresh empty state.'
  }
  $distributionSections += (Invoke-An3ctl @('ui', 'tree', '--target', 'windows', '--limit', '120', '--json')).data.section
  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--css', '.native-sidebar [data-nav="settings"]', '--json')
  $settings = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'application-settings', '--json')
  if (!$settings.data.node.visible -or $settings.data.node.name -notmatch 'In-game settings') {
    throw 'The packaged shell Settings page did not show its reviewed In-game settings card.'
  }
  $gameSettingsForm = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'game-settings', '--json')
  if ($gameSettingsForm.data.node.visible) {
    throw 'The packaged shell rendered a Game Settings form on a host with no settings bridge.'
  }
  $distributionSections += (Invoke-An3ctl @('ui', 'tree', '--target', 'windows', '--limit', '120', '--json')).data.section
  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--css', '.native-sidebar [data-nav="about"]', '--json')
  $distributionVersion = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'native-app-version', '--json')
  if (!$distributionVersion.data.node.visible -or !$distributionVersion.data.node.name -or $distributionVersion.data.node.name -match '__AN3_VERSION__') {
    throw 'The packaged shell About page did not show a substituted app version.'
  }
  $distributionSections += (Invoke-An3ctl @('ui', 'tree', '--target', 'windows', '--limit', '120', '--json')).data.section
  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--css', '.native-sidebar [data-nav="play"]', '--json')
  $distributionSections += (Invoke-An3ctl @('ui', 'tree', '--target', 'windows', '--limit', '120', '--json')).data.section
  if (($distributionSections -join ',') -ne 'play,library,settings,about,play') {
    throw "Packaged shell navigation ended on unexpected sections: $($distributionSections -join ',')."
  }
  $distributionProcess.Refresh()
  $null = $distributionProcess.CloseMainWindow()
  if (!$distributionProcess.WaitForExit(10000)) {
    & taskkill.exe /PID $distributionProcess.Id /T /F | Out-Null
    $distributionProcess.WaitForExit(5000) | Out-Null
    throw 'The packaged Windows shell did not close cleanly after its navigation check.'
  }
  $distributionProcess.Refresh()
  if (!$distributionProcess.HasExited) { throw 'The packaged Windows shell remained open after its close request.' }
  $deadline = [DateTime]::UtcNow.AddSeconds(10)
  do {
    $portOwner = Get-NetTCPConnection -State Listen -LocalPort 38471 -ErrorAction SilentlyContinue
    $debugPortOwner = Get-NetTCPConnection -State Listen -LocalPort 9222 -ErrorAction SilentlyContinue
    if (!$portOwner -and !$debugPortOwner) { break }
    Start-Sleep -Milliseconds 250
  } while ([DateTime]::UtcNow -lt $deadline)
  if ($portOwner) { throw 'Closing the packaged shell left port 38471 occupied.' }
  if ($debugPortOwner) { throw 'Closing the packaged shell left WebView2 CDP port 9222 occupied.' }
  Write-Evidence 'distribution-shell-ui.json' ([ordered]@{
    sourceSha = $ExpectedSourceSha
    sha256 = $distributionShellSha
    sections = $distributionSections
    emptyLibraryVisible = $true
    inGameSettingsVisible = $true
    gameSettingsFormHidden = $true
    appVersion = $distributionVersion.data.node.name
    cdpAddress = '127.0.0.1:9222'
    runtimeAndCdpPortsReleased = $true
    closedCleanly = $true
  })
  $distributionProcess = $null

  # Keep the packaged distribution executable immutable. Replacing it in-place
  # can fail when Windows or the installer still holds the file open, and it
  # needlessly complicates proving that the shipped executable was preserved.
  # The test shell uses the same resource directory when placed beside it.
  $automationTestExe = Join-Path $installDir 'an3-offline-native-ui-test.exe'
  Copy-Item -LiteralPath $automationExe -Destination $automationTestExe
  if ((Get-FileHash $automationTestExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $automationHash) {
    throw 'The source-matched Windows UI-control shell was not copied beside the isolated package resources.'
  }

  $fixture = Join-Path $evidence 'AN3TAPTEST.gba'
  & python tools/testrom/gba_homebrew_test.py $fixture AN3TAPTEST --latch-input
  if ($LASTEXITCODE -ne 0) { throw 'Could not generate the lawful GBA UI-import fixture.' }
  $fixtureHash = (Get-FileHash $fixture -Algorithm SHA256).Hash.ToLowerInvariant()
  $env:AN3_UI_TEST_ROM = $fixture

  # Windows Server hosted runners have no WASAPI endpoint; keep the probe and
  # the shell-launched player on the dummy audio driver.
  $env:SDL_AUDIODRIVER = 'dummy'
  # Run the installed player once without the shell. If a windowed player cannot
  # start on this runner, its own stdout/stderr and process state say so before
  # the shell journey adds a second moving part.
  $probeStorage = Join-Path $evidence 'player-probe-storage'
  New-Item -ItemType Directory -Force -Path $probeStorage | Out-Null
  $probeStdout = Join-Path $evidence 'player-probe-stdout.log'
  $probeStderr = Join-Path $evidence 'player-probe-stderr.log'
  $probe = Start-Process -FilePath $playerExe `
    -ArgumentList @('--rom', $fixture, '--system', 'gba', '--control-stdin', '--no-controls', '--storage', $probeStorage) `
    -WorkingDirectory $playerDir -PassThru `
    -RedirectStandardOutput $probeStdout -RedirectStandardError $probeStderr
  $probeDeadline = [DateTime]::UtcNow.AddSeconds(20)
  while ([DateTime]::UtcNow -lt $probeDeadline) {
    $probe.Refresh()
    if ($probe.HasExited) { break }
    if ((Get-Content -LiteralPath $probeStdout -Raw -ErrorAction SilentlyContinue) -match 'AN3_NATIVE_READY') { break }
    Start-Sleep -Milliseconds 500
  }
  $probe.Refresh()
  $probeReady = (Get-Content -LiteralPath $probeStdout -Raw -ErrorAction SilentlyContinue) -match 'AN3_NATIVE_READY'
  $probeExited = $probe.HasExited
  $probeMainWindow = $probe.MainWindowHandle
  $probeThreads = $probe.Threads.Count
  if (!$probe.HasExited) { & taskkill.exe /PID $probe.Id /T /F | Out-Null; $probe.WaitForExit(5000) | Out-Null }
  Write-Evidence 'player-probe.json' ([ordered]@{
    ready = $probeReady
    exited = $probeExited
    exitCode = if ($probeExited) { $probe.ExitCode } else { $null }
    mainWindowHandle = [string]$probeMainWindow
    threads = $probeThreads
    stdout = (Get-Content -LiteralPath $probeStdout -Raw -ErrorAction SilentlyContinue)
    stderr = (Get-Content -LiteralPath $probeStderr -Raw -ErrorAction SilentlyContinue)
    environment = [ordered]@{
      VK_ICD_FILENAMES = $env:VK_ICD_FILENAMES
      VK_DRIVER_FILES = $env:VK_DRIVER_FILES
      VK_LOADER_DEBUG = $env:VK_LOADER_DEBUG
    }
  })
  if (!$probeReady) {
    throw "The installed player did not reach AN3_NATIVE_READY on its own (exited=$probeExited; stderr=$(Get-Content -LiteralPath $probeStderr -Raw -ErrorAction SilentlyContinue))."
  }

  $env:AN3_NATIVE_RUNTIME_PORT = '38471'
  $env:AN3_WINDOWS_CDP_LOCAL = '1'
  # Windows Server hosted runners have no WASAPI endpoint; keep native launch testable.
  $env:SDL_AUDIODRIVER = 'dummy'
  $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-address=127.0.0.1 --remote-debugging-port=9222'
  $mainProcess = Start-Process -FilePath $automationTestExe -WorkingDirectory $installDir -PassThru
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

  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--css', '.native-sidebar [data-nav="library"]', '--json')
  $library = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'game-grid', '--json')
  if (!$library.data.node.visible -or $library.data.node.name -notmatch 'No games on this device') {
    throw 'The installed shell Library did not show its fresh empty state.'
  }
  $librarySection = (Invoke-An3ctl @('ui', 'tree', '--target', 'windows', '--limit', '120', '--json')).data.section
  if ($librarySection -ne 'library') { throw "Library navigation ended on '$librarySection'." }

  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--css', '.native-sidebar [data-nav="settings"]', '--json')
  $settings = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'application-settings', '--json')
  if (!$settings.data.node.visible -or $settings.data.node.name -notmatch 'In-game settings') {
    throw 'The installed shell Settings page did not show its reviewed In-game settings card.'
  }
  $gameSettingsForm = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'game-settings', '--json')
  if ($gameSettingsForm.data.node.visible) {
    throw 'The installed shell rendered a Game Settings form on a host with no settings bridge.'
  }
  $settingsSection = (Invoke-An3ctl @('ui', 'tree', '--target', 'windows', '--limit', '120', '--json')).data.section
  if ($settingsSection -ne 'settings') { throw "Settings navigation ended on '$settingsSection'." }

  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--css', '.native-sidebar [data-nav="about"]', '--json')
  $aboutVersion = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'native-app-version', '--json')
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
    inGameSettingsVisible = $true
    gameSettingsFormHidden = $true
    appVersion = $aboutVersion.data.node.name
  })

  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--css', '.native-sidebar [data-nav="play"]', '--json')
  # The topbar Open ROM is hidden on Play by design; the hero action is the
  # visible one and runs the same real import handler.
  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--css', '.native-hero-open', '--json')
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
  $initialNativeStatus = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'native-status', '--json')
  $initialNativeStatusName = [string]$initialNativeStatus.data.node.name
  $null = Invoke-An3ctl @('ui', 'click', '--target', 'windows', '--testid', 'game-launch', '--json')
  $nativeStatus = $null
  $nativeStatusQueryError = $null
  $nativeStatusNames = @()
  $launchedPlayer = $null
  $deadline = [DateTime]::UtcNow.AddSeconds(60)
  while ([DateTime]::UtcNow -lt $deadline) {
    # A live bundled player process is the product's success condition; the
    # card's status note is a UI hint that a re-render may replace.
    $launchedPlayer = Get-CimInstance Win32_Process -Filter "Name = 'an3-native-runtime.exe'" |
      Where-Object { $_.ParentProcessId -eq $mainProcess.Id } | Select-Object -First 1
    try {
      $nativeStatus = Invoke-An3ctl @('ui', 'query', '--target', 'windows', '--testid', 'native-status', '--json')
      $nativeStatusQueryError = $null
      $currentStatusName = [string]$nativeStatus.data.node.name
      if ($currentStatusName) { $nativeStatusNames += $currentStatusName }
      $isStarting = $currentStatusName -match '^(Starting native|Đang khởi động)\b'
      if ($launchedPlayer) { break }
      if ($currentStatusName -and $currentStatusName -ne $initialNativeStatusName -and !$isStarting) { break }
    } catch {
      $nativeStatusQueryError = $_.Exception.Message
    }
    Start-Sleep -Milliseconds 500
  }
  $nativeLaunchDetail = if ($nativeStatusNames.Count -gt 0) { [string]$nativeStatusNames[-1] } else { '' }
  $nativeLaunchState = if ($launchedPlayer) { 'running' }
    elseif ($nativeLaunchDetail -match '(?i)unavailable|not in the app.s private storage|could not|failed|missing|error') { 'error' }
    else { 'unknown' }
  $launchToastDetail = (Get-WindowsPageDiagnostics).toastText
  # The shell redirects the player's stderr into the per-game storage. When a
  # player starts but presents no window, that log names the failing subsystem.
  $playerLogPath = Join-Path (Join-Path $env:APPDATA 'space.an3tocom.offline.automation') ("native-player/gba/$gameCardRomId/runtime.log")
  $playerLogTail = if (Test-Path -LiteralPath $playerLogPath) {
    $text = Get-Content -LiteralPath $playerLogPath -Raw -ErrorAction SilentlyContinue
    if ($text) { $text.Substring([Math]::Max(0, $text.Length - 4000)) } else { '' }
  } else { "<no log at $playerLogPath>" }
  Write-Evidence 'launch.json' ([ordered]@{
    sourceSha = $ExpectedSourceSha
    appVersion = $automationVersionMatch.Groups[1].Value.Trim()
    launchStatus = $nativeLaunchState
    launchDetail = $nativeLaunchDetail
    launchToastDetail = $launchToastDetail
    playerProcessFound = [bool]$launchedPlayer
    nativeStatusTexts = @($nativeStatusNames | Select-Object -Last 6)
    playerLogPath = $playerLogPath
    playerLogTail = $playerLogTail
    lastStatusQueryError = $nativeStatusQueryError
  })
  if ($nativeLaunchState -ne 'running') {
    throw "The shell game card did not start the bundled Windows runtime (state=$nativeLaunchState; detail=$nativeLaunchDetail; queryError=$nativeStatusQueryError)."
  }
  # The full-feature 3.6.12 shell is a launcher: it opens the bundled player in
  # its own window and owns no in-page pause/save card (that card exists only on
  # the core-only shell line). Input, quick-save and quick-load are exercised
  # against the installed player below, so this journey keeps only what the
  # shipped shell really offers.
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
  # The process exists before its first frame is presented, so retry until the
  # fixture's blue frame is actually on screen instead of sampling a black
  # startup window.
  $frameCapture = $null
  $frameDeadline = [DateTime]::UtcNow.AddSeconds(30)
  $frameErrors = @()
  while ([DateTime]::UtcNow -lt $frameDeadline) {
    try { $frameCapture = Capture-NativePlayerWindow ([int]$runtimeProcess.ProcessId); break }
    catch { $frameErrors += $_.Exception.Message; Start-Sleep -Milliseconds 750 }
  }
  if (!$frameCapture) {
    try { Save-DesktopScreenshot 'desktop-at-launch-failure.png' } catch { Write-Evidence 'desktop-capture-error.txt' ([ordered]@{ error = $_.Exception.Message }) }
    $livePlayer = Get-Process -Id ([int]$runtimeProcess.ProcessId) -ErrorAction SilentlyContinue
    $playerState = if ($livePlayer) { "alive, threads=$($livePlayer.Threads.Count)" } else { 'exited' }
    throw "The bundled Windows player presented no fixture frame within 30 seconds ($playerState): $($frameErrors | Select-Object -Last 1)`nPlayer log:`n$playerLogTail"
  }
  $visibleNativeWindows = @([An3WindowCapture]::GetWindowsForProcess([int]$runtimeProcess.ProcessId))
  $controlsWindow = $visibleNativeWindows | Where-Object { $_.Title -match 'Controls$' } | Select-Object -First 1
  if ($controlsWindow) {
    throw "The native player still exposes a separate GTK Controls window: '$($controlsWindow.Title)'."
  }
  if ($visibleNativeWindows.Count -ne 1) {
    $windowTitles = @($visibleNativeWindows | ForEach-Object { $_.Title }) -join ', '
    throw "The native player must show exactly one visible game window; found $($visibleNativeWindows.Count): $windowTitles"
  }
  Write-Evidence 'windows-shell-launch.json' ([ordered]@{
    shellKind = 'full-feature launcher (no in-page session card)'
    launchStatus = $nativeLaunchState
    launchDetail = $nativeLaunchDetail
    playerWindowTitle = $runtimeWindow.MainWindowTitle
    videoFrame = $frameCapture.status
    visibleNativeWindowCount = $visibleNativeWindows.Count
  })
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
    launchStatus = $nativeLaunchState
    playerImage = $runtimeProcess.Name
    playerParentProcessId = $runtimeProcess.ParentProcessId
    playerWindowHandle = [string]$runtimeWindow.MainWindowHandle
    playerWindowTitle = $runtimeWindow.MainWindowTitle
    videoFrameStatus = $frameCapture.status
    videoFrameWidth = $frameCapture.width
    videoFrameHeight = $frameCapture.height
    centerPixel = $frameCapture.centerPixel
    videoFrameScreenshot = $frameCapture.screenshot
    visiblePlayerWindows = $frameCapture.candidateWindows
    visibleNativeWindowCount = $visibleNativeWindows.Count
    visibleNativeWindowTitles = @($visibleNativeWindows | ForEach-Object { $_.Title })
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
    distributionShellUnchanged = ((Get-FileHash $mainExe -Algorithm SHA256).Hash.ToLowerInvariant() -eq $distributionShellSha)
    sourceSha = $ExpectedSourceSha
  })
  if ((Get-FileHash $mainExe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $distributionShellSha) {
    throw 'The installed distribution shell changed during the test-shell runtime check.'
  }
  Write-Evidence 'distribution-shell.json' ([ordered]@{
    sha256 = $distributionShellSha
    unchangedAfterSmoke = $true
    installerStartedAndClosedApp = $installerStartedApp
    uiJourneyPassed = (Test-Path (Join-Path $evidence 'distribution-shell-ui.json'))
  })
  $mainProcess = $null
  Remove-Item Env:AN3_UI_TEST_ROM -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $automationTestExe -Force
  $automationTestExe = $null

  $env:PATH = "$playerDir;$env:PATH"
  $env:AN3_PLAYER = $playerExe
  $env:SDL_VIDEODRIVER = 'dummy'
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

  $sramFixture = Join-Path $evidence 'AN3SRAMTEST.gba'
  & python tools/testrom/gba_homebrew_test.py $sramFixture AN3SRAMTEST
  if ($LASTEXITCODE -ne 0) { throw 'Could not generate the lawful GBA SRAM persistence fixture.' }
  $sramFixtureHash = (Get-FileHash $sramFixture -Algorithm SHA256).Hash.ToLowerInvariant()
  $sramStorage = Join-Path $installRoot 'gba-sram-storage'
  New-Item -ItemType Directory -Force -Path $sramStorage | Out-Null
  $sramBase = @(
    'emulator', 'snapshot', '--rom', $sramFixture, '--system', 'gba', '--frames', '120',
    '--player', $playerExe, '--libdir', $coreDir, '--storage', $sramStorage,
    '--seq', 'A@0-120', '--json'
  )
  $sramFresh = Invoke-An3ctl $sramBase
  $sramSecond = Invoke-An3ctl $sramBase
  if (!$sramFresh.ok -or !$sramSecond.ok) {
    throw 'The packaged Windows player failed one of the two SRAM fixture launches.'
  }
  # mGBA selects a cartridge save type by scanning the ROM for a known
  # save-library signature. This lawful homebrew fixture has none, so the core
  # never creates a .srm - the same two-launch sequence produces no .srm with
  # the Linux player either. Record the observation; only a written save that
  # fails to restore is a failure here.
  $sramFiles = @(Get-ChildItem -LiteralPath $sramStorage -Filter '*.srm' -File -Recurse)
  $sramFrameChanged = $sramFresh.data.rawHash -ne $sramSecond.data.rawHash
  if ($sramFiles.Count -gt 0 -and !$sramFrameChanged) {
    throw 'The player wrote a cartridge save but the relaunch did not restore it.'
  }
  Write-Evidence 'sram.json' ([ordered]@{
    fixtureSha256 = $sramFixtureHash
    playerSha256 = (Get-FileHash $playerExe -Algorithm SHA256).Hash.ToLowerInvariant()
    framesPerLaunch = 120
    sameStorageAcrossLaunches = $true
    freshRawHash = $sramFresh.data.rawHash
    secondRawHash = $sramSecond.data.rawHash
    sramFrameChanged = $sramFrameChanged
    sramFileCount = $sramFiles.Count
    cartridgeSramPersistence = if ($sramFiles.Count -gt 0) { 'VERIFIED' } else { 'UNVERIFIED' }
    note = 'mGBA needs a known save-library signature in the ROM to select a cartridge save type; this homebrew fixture has none, and the Linux player shows the same no-.srm result. Cartridge SRAM persistence is not established by this fixture.'
  })
  foreach ($snapshot in @($sramFresh.data, $sramSecond.data)) {
    foreach ($capturePath in @([string]$snapshot.pngPath, [string]$snapshot.rawPath)) {
      if ($capturePath -and (Test-Path $capturePath)) {
        Remove-Item -LiteralPath $capturePath -Force
      }
    }
  }
  Remove-Item -LiteralPath $sramStorage -Recurse -Force
  $sramStorage = $null
  Write-Host 'WINDOWS_INSTALL_SHELL_IMPORT_LAUNCH_INPUT_SAVE_LOAD=GOOD SRAM=UNVERIFIED'
} catch {
  Write-Evidence 'failure.json' ([ordered]@{ message = $_.Exception.Message; sourceSha = $ExpectedSourceSha; artifactRunId = $ArtifactRunId })
  throw
} finally {
  if ($sramStorage -and (Test-Path $sramStorage)) {
    Remove-Item -LiteralPath $sramStorage -Recurse -Force -ErrorAction SilentlyContinue
  }
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
  if ($distributionProcess) {
    $distributionProcess.Refresh()
    if (!$distributionProcess.HasExited) {
      $null = $distributionProcess.CloseMainWindow()
      if (!$distributionProcess.WaitForExit(10000)) {
        & taskkill.exe /PID $distributionProcess.Id /T /F | Out-Null
        $distributionProcess.WaitForExit(5000)
      }
    }
  }
  Remove-Item Env:AN3_UI_TEST_ROM -ErrorAction SilentlyContinue
  if ($automationTestExe -and (Test-Path $automationTestExe)) {
    Remove-Item -LiteralPath $automationTestExe -Force -ErrorAction SilentlyContinue
  }
}
