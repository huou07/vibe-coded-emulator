Param(
  [string]$Label = 'local heavyweight work',
  [string]$Path = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'
$warningGiB = if ($env:AN3_DISK_WARNING_GIB) { [long]$env:AN3_DISK_WARNING_GIB } else { 40L }
$reserveGiB = if ($env:AN3_DISK_RESERVE_GIB) { [long]$env:AN3_DISK_RESERVE_GIB } else { 25L }
if ($warningGiB -lt 0 -or $reserveGiB -lt 0 -or $reserveGiB -gt $warningGiB) {
  throw 'AN3_DISK_WARNING_GIB and AN3_DISK_RESERVE_GIB must be non-negative whole GiB values, with reserve no greater than warning.'
}

$root = [IO.Path]::GetPathRoot((Resolve-Path -LiteralPath $Path).Path)
$drive = [IO.DriveInfo]::new($root)
$availableBytes = [long]$drive.AvailableFreeSpace
$availableGiB = [long][Math]::Floor($availableBytes / 1GB)
if ($availableBytes -lt ($reserveGiB * 1GB)) {
  throw "DISK_PREFLIGHT=STOP task=$Label available=${availableGiB}GiB reserve=${reserveGiB}GiB; use CI or free known disposable build outputs first."
}
if ($availableBytes -lt ($warningGiB * 1GB)) {
  [Console]::Error.WriteLine("DISK_PREFLIGHT=WARNING task=$Label available=${availableGiB}GiB warning=${warningGiB}GiB reserve=${reserveGiB}GiB.")
} else {
  Write-Output "DISK_PREFLIGHT=PASS task=$Label available=${availableGiB}GiB reserve=${reserveGiB}GiB."
}
