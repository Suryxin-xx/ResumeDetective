param(
    [string]$Version = "4.3.0-dev"
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
    & $goExe build -trimpath -buildvcs=false -ldflags "-s -w -H=windowsgui -X main.version=$Version" -o ".\ResumeDetective.exe" ./cmd/resumedetective
    if ($LASTEXITCODE -ne 0) { throw "Go build failed." }
    & $goExe run ./cmd/windows-resource -exe ".\ResumeDetective.exe" -icon ".\assets\app-icon.ico" -version ($Version -replace '-.*$','')
    if ($LASTEXITCODE -ne 0) { throw "Writing Windows resources failed." }
}
finally { Pop-Location }
Write-Host "Local test build ready: $repoRoot\ResumeDetective.exe"
