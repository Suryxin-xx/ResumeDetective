param(
    [string]$Version = "4.5.1-dev"
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$package = Get-Content -LiteralPath (Join-Path $repoRoot "frontend\package.json") -Raw | ConvertFrom-Json
$baseVersion = $Version -replace '-.*$', ''
if ($package.version -ne $baseVersion) {
    throw "Version mismatch: local build=$Version, package.json=$($package.version)."
}
$command = Get-Command go -ErrorAction SilentlyContinue
if ($command) {
    $goExe = $command.Source
} elseif (Test-Path -LiteralPath "D:\Go\bin\go.exe") {
    $goExe = "D:\Go\bin\go.exe"
} else {
    throw "Go was not found. Install Go or add its bin directory to PATH."
}
if (-not (Get-Command gcc -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath "D:\Mingw64\bin\gcc.exe")) {
    $env:PATH = "D:\Mingw64\bin;$env:PATH"
}
Push-Location $repoRoot
$stagedExe = Join-Path $repoRoot "ResumeDetective.building.exe"
$finalExe = Join-Path $repoRoot "ResumeDetective.exe"
$backupExe = $null
try {
    # Keep caches outside the Go module so `go test ./...` never walks a nested GOPATH.
    $goWorkspace = Join-Path $env:TEMP "ResumeDetective-go-build"
    $env:GOPATH = Join-Path $goWorkspace "path"
    $env:GOCACHE = Join-Path $goWorkspace "cache"
    $env:GOTMPDIR = Join-Path $goWorkspace "tmp"
    New-Item -ItemType Directory -Force -Path $env:GOPATH, $env:GOCACHE, $env:GOTMPDIR | Out-Null
    npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    $env:CGO_ENABLED = "1"
    if (Test-Path -LiteralPath $stagedExe) {
        Remove-Item -LiteralPath $stagedExe -Force
    }
    & $goExe build -trimpath -buildvcs=false -ldflags "-s -w -H=windowsgui -X main.version=$Version" -o $stagedExe ./cmd/resumedetective
    if ($LASTEXITCODE -ne 0) { throw "Go build failed." }
    if (-not (Test-Path -LiteralPath $stagedExe)) {
        throw "The staged executable disappeared after compilation. Check Microsoft Defender protection history."
    }
    & $goExe run ./cmd/windows-resource -exe $stagedExe -icon ".\assets\app-icon.ico" -version ($Version -replace '-.*$','')
    if ($LASTEXITCODE -ne 0) { throw "Writing Windows resources failed." }
    if (-not (Test-Path -LiteralPath $stagedExe)) {
        throw "The staged executable disappeared while writing resources. Check Microsoft Defender protection history."
    }
    if ((Get-Item -LiteralPath $stagedExe).Length -lt 1MB) {
        throw "The staged executable is unexpectedly small and will not replace the existing local build."
    }

    if (Test-Path -LiteralPath $finalExe) {
        $backupDir = Join-Path $repoRoot "backups"
        New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
        $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $backupExe = Join-Path $backupDir "ResumeDetective-pre-local-build-$timestamp.exe"
        [System.IO.File]::Replace($stagedExe, $finalExe, $backupExe, $true)
    } else {
        Move-Item -LiteralPath $stagedExe -Destination $finalExe
    }
}
finally {
    if (Test-Path -LiteralPath $stagedExe) {
        Remove-Item -LiteralPath $stagedExe -Force
    }
    Pop-Location
}
Write-Host "Local test build ready: $repoRoot\ResumeDetective.exe"
