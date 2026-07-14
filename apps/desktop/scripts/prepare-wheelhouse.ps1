param(
  [string]$Arch = "win-x64",
  [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (!$PythonPath) {
  $candidate = Join-Path $repoRoot "build\python\$Arch\python.exe"
  if (Test-Path $candidate) {
    $PythonPath = $candidate
  } else {
    $PythonPath = "py"
  }
}

$pyArgs = @()
if ($PythonPath -eq "py") {
  $pyArgs += "-3.12"
}

$versionTag = & $PythonPath @pyArgs -c "import sys; print(f'py{sys.version_info[0]}{sys.version_info[1]}')"
$wheelhouse = Join-Path $repoRoot "wheelhouse\$Arch-$versionTag"
$requirements = Join-Path $repoRoot "backend\requirements.txt"

if (!(Test-Path $requirements)) {
  throw "Missing requirements file: $requirements"
}

if (Test-Path $wheelhouse) {
  Remove-Item -LiteralPath $wheelhouse -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $wheelhouse | Out-Null

Write-Host "[wheelhouse] Building wheels into $wheelhouse"
& $PythonPath @pyArgs -m pip --disable-pip-version-check --no-input wheel --prefer-binary --wheel-dir $wheelhouse -r $requirements

$count = (Get-ChildItem -Path $wheelhouse -Filter *.whl -File | Measure-Object).Count
if ($count -lt 1) {
  throw "Wheelhouse was created but no wheels were written."
}
Write-Host "[wheelhouse] Ready: $count wheels in $wheelhouse"
