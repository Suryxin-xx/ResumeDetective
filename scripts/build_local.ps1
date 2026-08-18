param(
    [string]$Version = "4.2.0-dev"
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$goExe = "E:\Agent\Project\Job\.tools\go1.26.5\go\bin\go.exe"
if (-not (Test-Path -LiteralPath $goExe)) {
    $command = Get-Command go -ErrorAction SilentlyContinue
    if (-not $command) { throw "Go was not found." }
    $goExe = $command.Source
}
if (-not (Get-Command gcc -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath "D:\Mingw64\bin\gcc.exe")) {
    $env:PATH = "D:\Mingw64\bin;$env:PATH"
}
Push-Location $repoRoot
try {
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
