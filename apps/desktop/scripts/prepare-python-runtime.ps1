param(
  [string]$Version = "3.12.10",
  [string]$Arch = "win-x64",
  [switch]$ForceRefresh
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$cacheDir = Join-Path $repoRoot "build\cache"
$runtimeDir = Join-Path $repoRoot "build\python\$Arch"
$packagePath = Join-Path $cacheDir "python.$Version.nupkg"
$zipPath = Join-Path $cacheDir "python.$Version.zip"
$extractDir = Join-Path $cacheDir "python.$Version"
$url = "https://www.nuget.org/api/v2/package/python/$Version"

$existingPython = Join-Path $runtimeDir "python.exe"
if (!$ForceRefresh -and (Test-Path $existingPython)) {
  $existingVersion = & $existingPython -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}')"
  if ($existingVersion -eq $Version) {
    Write-Host "[python-runtime] Ready: $existingPython ($existingVersion)"
    exit 0
  }
}

New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null

if (!(Test-Path $packagePath)) {
  Write-Host "[python-runtime] Downloading Python $Version from NuGet..."
  Invoke-WebRequest -Uri $url -OutFile $packagePath
}

if (Test-Path $extractDir) {
  Remove-Item -LiteralPath $extractDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $extractDir | Out-Null

Write-Host "[python-runtime] Extracting $packagePath..."
Copy-Item -LiteralPath $packagePath -Destination $zipPath -Force
Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force

$toolsDir = Join-Path $extractDir "tools"
if (!(Test-Path (Join-Path $toolsDir "python.exe"))) {
  throw "Downloaded package did not contain tools\python.exe"
}

if (Test-Path $runtimeDir) {
  Remove-Item -LiteralPath $runtimeDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

Copy-Item -Path (Join-Path $toolsDir "*") -Destination $runtimeDir -Recurse -Force

$python = Join-Path $runtimeDir "python.exe"
$versionText = & $python -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}')"
Write-Host "[python-runtime] Ready: $python ($versionText)"

& $python -m pip --disable-pip-version-check --no-input install --upgrade pip setuptools wheel
