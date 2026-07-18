$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot ".git"))) {
    throw "Connect the existing .git directory to this source folder first. No files were changed."
}

Write-Host "Removing private/generated paths from the Git index only..."
Write-Host "The files remain on disk and are protected by .gitignore."
git -C $projectRoot rm -r --cached --ignore-unmatch -- "data" "Reasonix Cli" ".resumedetective.local.json" "build" "dist"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to clean the Git index. Working files were not intentionally deleted."
}

git -C $projectRoot config core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) {
    throw "Failed to enable the repository safety hook."
}

python (Join-Path $PSScriptRoot "check_repository_safety.py")
if ($LASTEXITCODE -ne 0) {
    throw "Repository still contains files blocked by the safety policy."
}

Write-Host "Repository index prepared. Review 'git status' before committing."
