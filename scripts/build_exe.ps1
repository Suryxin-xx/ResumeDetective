$ErrorActionPreference = "Stop"

# Public entry point: build from a clean staging tree so local data is never packaged.
$releaseScript = Join-Path $PSScriptRoot "build_release.ps1"
if (-not (Test-Path -LiteralPath $releaseScript)) {
    throw "Missing release staging script: $releaseScript"
}

Write-Host "Building ResumeDetective from a clean release tree..."
& powershell.exe -NoProfile -NoLogo -ExecutionPolicy Bypass -File $releaseScript
if ($LASTEXITCODE -ne 0) {
    throw "Release build failed with exit code $LASTEXITCODE"
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$output = Join-Path $projectRoot "build\release-src\dist\ResumeDetective"
if (Test-Path -LiteralPath $output) {
    Write-Host "EXE output: $output"
} else {
    throw "EXE output was not created. Ensure PyInstaller is installed and inspect the release build log."
}
