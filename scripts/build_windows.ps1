param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = "4.3.1",
    [string]$ReleaseRoot = "",
    [switch]$ArchiveExisting
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$package = Get-Content -LiteralPath (Join-Path $repoRoot "frontend\package.json") -Raw | ConvertFrom-Json
$packageLockText = Get-Content -LiteralPath (Join-Path $repoRoot "frontend\package-lock.json") -Raw
$packageLockVersion = [regex]::Match($packageLockText, '(?m)^  "version": "([^"]+)"').Groups[1].Value
if ($package.version -ne $Version -or $packageLockVersion -ne $Version) {
    throw "Version mismatch: release=$Version, package.json=$($package.version), package-lock.json=$packageLockVersion."
}
if (-not $ReleaseRoot) { $ReleaseRoot = Join-Path $repoRoot "releases\v$Version" }
$ReleaseRoot = [System.IO.Path]::GetFullPath($ReleaseRoot)
$releaseParent = [System.IO.Path]::GetFullPath((Split-Path -Parent $ReleaseRoot))
if ((Test-Path -LiteralPath $ReleaseRoot) -and -not $ArchiveExisting) {
    throw "Release directory already exists: $ReleaseRoot. Choose another version or rerun with -ArchiveExisting."
}
New-Item -ItemType Directory -Force -Path $releaseParent | Out-Null
$stagingRoot = Join-Path $releaseParent (".staging-{0}-{1}" -f ([System.IO.Path]::GetFileName($ReleaseRoot)), [guid]::NewGuid().ToString("N"))
$payload = Join-Path $stagingRoot "ResumeDetective"
$zipPath = Join-Path $stagingRoot "ResumeDetective-windows-x64.zip"
$archivedExisting = $null

$go = Get-Command go -ErrorAction SilentlyContinue
if (-not $go -and $env:RESUME_DETECTIVE_GO) { $go = Get-Item -LiteralPath $env:RESUME_DETECTIVE_GO -ErrorAction SilentlyContinue }
if (-not $go) {
    $jobRoot = Split-Path -Parent (Split-Path -Parent $repoRoot)
    $bundled = Get-ChildItem -Path (Join-Path $jobRoot ".tools\go*\go\bin\go.exe") -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
    if ($bundled) { $go = $bundled }
}
if (-not $go) { throw "Go was not found. Install Go or set RESUME_DETECTIVE_GO to go.exe." }
$goExe = if ($go.PSObject.Properties.Name -contains "Source") { $go.Source } else { $go.FullName }
if (-not (Get-Command gcc -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath "D:\Mingw64\bin\gcc.exe")) {
    $env:PATH = "D:\Mingw64\bin;$env:PATH"
}
if (-not (Get-Command gcc -ErrorAction SilentlyContinue)) { throw "GCC was not found. Add MinGW bin to PATH." }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw "Node.js/npm was not found." }

# Keep caches outside the Go module. A repo-local GOPATH can be mistaken for source
# by recursive Go package patterns and makes an otherwise healthy release fail.
$goWorkspace = Join-Path $env:TEMP "ResumeDetective-go-build"
$env:GOPATH = Join-Path $goWorkspace "path"
$env:GOCACHE = Join-Path $goWorkspace "cache"
$env:GOTMPDIR = Join-Path $goWorkspace "tmp"
New-Item -ItemType Directory -Force -Path $env:GOPATH, $env:GOCACHE, $env:GOTMPDIR | Out-Null

Push-Location $repoRoot
try {
    & (Join-Path $PSScriptRoot "check_repository_safety.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Repository safety check failed." }
    if (-not (Test-Path -LiteralPath ".\frontend\node_modules")) {
        npm --prefix frontend ci
        if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
    }
    npm --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    & $goExe test ./cmd/... ./internal/...
    if ($LASTEXITCODE -ne 0) { throw "Go tests failed." }
    & $goExe vet ./cmd/... ./internal/...
    if ($LASTEXITCODE -ne 0) { throw "Go vet failed." }

    New-Item -ItemType Directory -Force -Path $payload | Out-Null
    $exe = Join-Path $payload "ResumeDetective.exe"
    $env:CGO_ENABLED = "1"
    & $goExe build -trimpath -buildvcs=false -ldflags "-s -w -H=windowsgui -X main.version=$Version" -o $exe ./cmd/resumedetective
    if ($LASTEXITCODE -ne 0) { throw "Go build failed." }
    & $goExe run ./cmd/windows-resource -exe $exe -icon ".\assets\app-icon.ico" -version $Version
    if ($LASTEXITCODE -ne 0) { throw "Writing Windows icon/version metadata failed." }
    $demoDataDir = Join-Path $payload "data"
    New-Item -ItemType Directory -Force -Path $demoDataDir | Out-Null
    & $goExe run ./cmd/demo-data -input ".\data.example\sample-data.json" -output (Join-Path $demoDataDir "resume_detective.db")
    if ($LASTEXITCODE -ne 0) { throw "Creating the public demo database failed." }
    Copy-Item -LiteralPath ".\README.md" -Destination $payload
    Copy-Item -LiteralPath ".\LICENSE" -Destination $payload
    Copy-Item -LiteralPath ".\data.example" -Destination (Join-Path $payload "data.example") -Recurse
    $releaseScreenshots = Join-Path $payload "screenshots"
    New-Item -ItemType Directory -Path $releaseScreenshots | Out-Null
    Copy-Item -Path ".\screenshots\v4-*.png" -Destination $releaseScreenshots
    Compress-Archive -Path (Join-Path $payload "*") -DestinationPath $zipPath -CompressionLevel Optimal
    foreach ($artifact in @($exe, $zipPath)) {
        $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $artifact
        $line = "$($hash.Hash.ToLowerInvariant())  $([System.IO.Path]::GetFileName($artifact))"
        [System.IO.File]::WriteAllText("$artifact.sha256", "$line`r`n", [System.Text.UTF8Encoding]::new($false))
    }
}
catch {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
    throw
}
finally { Pop-Location }

try {
    if (Test-Path -LiteralPath $ReleaseRoot) {
        $archiveRoot = Join-Path $releaseParent "archive"
        New-Item -ItemType Directory -Force -Path $archiveRoot | Out-Null
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $archiveName = "{0}-{1}" -f ([System.IO.Path]::GetFileName($ReleaseRoot)), $stamp
        $archivedExisting = Join-Path $archiveRoot $archiveName
        $suffix = 1
        while (Test-Path -LiteralPath $archivedExisting) {
            $archivedExisting = Join-Path $archiveRoot ("{0}-{1}-{2}" -f ([System.IO.Path]::GetFileName($ReleaseRoot)), $stamp, $suffix)
            $suffix++
        }
        Move-Item -LiteralPath $ReleaseRoot -Destination $archivedExisting
    }
    Move-Item -LiteralPath $stagingRoot -Destination $ReleaseRoot
}
catch {
    if ($archivedExisting -and (Test-Path -LiteralPath $archivedExisting) -and -not (Test-Path -LiteralPath $ReleaseRoot)) {
        Move-Item -LiteralPath $archivedExisting -Destination $ReleaseRoot
    }
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
    throw
}

Write-Host "Release build completed: $ReleaseRoot"
if ($archivedExisting) { Write-Host "Previous same-version release archived at: $archivedExisting" }
Write-Host "Upload ResumeDetective-windows-x64.zip and its .sha256 to GitHub Releases."
