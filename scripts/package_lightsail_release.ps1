# Package the CURRENT VocalAgent working tree for Lightsail.
# Does not commit, push, reset, checkout, or clean.
# Does not use git archive (would omit untracked source).
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
  $Py = "python"
}

Write-Host "Packaging working tree from $Root"
& $Py (Join-Path $Root "scripts\package_lightsail_release.py")
if ($LASTEXITCODE -ne 0) {
  throw "package_lightsail_release.py failed"
}

$Out = Join-Path $Root "qa_output\production_release_v1\lightsail"
@(
  "vocalfb-lightsail-release.tar.gz",
  "vocalfb-lightsail-release.sha256",
  "MANIFEST.txt",
  "DEPLOY_SOURCE_STATE.txt"
) | ForEach-Object {
  $p = Join-Path $Out $_
  if (-not (Test-Path $p)) {
    throw "missing output $_"
  }
}

Write-Host "PASS outputs in $Out"
Get-ChildItem $Out | Format-Table Name, Length
