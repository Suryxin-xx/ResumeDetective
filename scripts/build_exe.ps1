$ErrorActionPreference = "Stop"

function Remove-TemporaryBuildWorkspace([string]$path) {
    $target = [IO.Path]::GetFullPath($path).TrimEnd('\')
    $expected = [IO.Path]::GetFullPath(
        (Join-Path ([IO.Path]::GetTempPath()) "ResumeDetective-Build")
    ).TrimEnd('\')
    if (-not $target.Equals($expected, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean an unsafe build path: $target"
    }
    if (-not (Test-Path -LiteralPath $target -PathType Container)) {
        return
    }
    Get-ChildItem -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue |
        ForEach-Object {
            try { $_.Attributes = [IO.FileAttributes]::Normal } catch { }
        }
    Remove-Item -LiteralPath $target -Recurse -Force
}

$releaseScript = Join-Path $PSScriptRoot "build_release.ps1"
if (-not (Test-Path -LiteralPath $releaseScript -PathType Leaf)) {
    throw "Missing release staging script: $releaseScript"
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$buildWorkspace = Join-Path ([IO.Path]::GetTempPath()) "ResumeDetective-Build"
$releaseRoot = Join-Path (Split-Path -Parent $projectRoot) "ResumeDetective-Releases"
$version = (Get-Content -LiteralPath (Join-Path $projectRoot "VERSION") -Raw).Trim()
$archive = Join-Path $releaseRoot "ResumeDetective-v$version-windows-x64.zip"
$hashFile = "$archive.sha256"

Write-Host "Building ResumeDetective in a temporary clean workspace..."
try {
    & powershell.exe -NoProfile -NoLogo -ExecutionPolicy Bypass -File $releaseScript
    if ($LASTEXITCODE -ne 0) {
        throw "Release build failed with exit code $LASTEXITCODE"
    }

    foreach ($requiredOutput in @($archive, $hashFile)) {
        if (-not (Test-Path -LiteralPath $requiredOutput -PathType Leaf)) {
            throw "Release output was not created: $requiredOutput"
        }
    }

    $unexpected = @(Get-ChildItem -LiteralPath $releaseRoot -Force |
        Where-Object {
            $_.PSIsContainer -or
            ($_.Name -notmatch '^ResumeDetective-v\d+\.\d+\.\d+-windows-x64\.zip(\.sha256)?$')
        })
    if ($unexpected) {
        throw "Release directory contains unexpected non-release items: $($unexpected.Name -join ', ')"
    }

    Write-Host "Release files ready in: $releaseRoot"
    Write-Host "Upload to GitHub Release:"
    Write-Host "  $archive"
    Write-Host "  $hashFile"
}
finally {
    Remove-TemporaryBuildWorkspace $buildWorkspace
    Write-Host "Temporary build workspace cleaned: $buildWorkspace"
}
