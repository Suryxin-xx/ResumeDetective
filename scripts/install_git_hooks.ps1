$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot ".git"))) {
    throw "The current source folder is not a Git repository yet. Move/connect .git first, then run this script."
}

git -C $projectRoot config core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure Git hooks."
}

Write-Host "Git pre-commit safety hook enabled."
Write-Host "It blocks runtime data, API keys, Reasonix binaries, local paths, databases and release archives."
