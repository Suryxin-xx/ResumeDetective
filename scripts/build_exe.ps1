$ErrorActionPreference = "Stop"

function Get-CachedBuildPython([string]$projectRoot) {
    $requirements = Join-Path $projectRoot "requirements-build.txt"
    $runtimeFile = Join-Path $projectRoot "RUNTIME_VERSION"
    foreach ($required in @($requirements, $runtimeFile)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "Missing reproducible build input: $required"
        }
    }

    $systemPython = (Get-Command python -ErrorAction Stop).Source
    $pythonTag = (& $systemPython -c "import sys; print(f'py{sys.version_info.major}{sys.version_info.minor}')").Trim()
    if ($LASTEXITCODE -ne 0 -or -not $pythonTag) {
        throw "Unable to determine the Python build version."
    }
    $runtimeVersion = (Get-Content -LiteralPath $runtimeFile -Raw).Trim()
    $requirementsHash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash.ToLowerInvariant()
    $cacheKey = "$runtimeVersion-$pythonTag-$($requirementsHash.Substring(0, 12))"
    $cacheBase = Join-Path $env:LOCALAPPDATA "ResumeDetective\BuildEnv"
    $environment = Join-Path $cacheBase $cacheKey
    $buildPython = Join-Path $environment "Scripts\python.exe"
    $readyMarker = Join-Path $environment ".ready"

    if (-not (Test-Path -LiteralPath $readyMarker -PathType Leaf)) {
        Write-Host "Preparing a cached, isolated release environment..."
        New-Item -ItemType Directory -Path $cacheBase -Force | Out-Null
        & $systemPython -m venv $environment
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to create the isolated build environment: $environment"
        }
        $pipOutput = & $buildPython -m pip install --disable-pip-version-check -r $requirements 2>&1
        $pipExitCode = $LASTEXITCODE
        $pipOutput | ForEach-Object { Write-Host $_ }
        if ($pipExitCode -ne 0) {
            throw "Unable to install release dependencies."
        }
        Set-Content -LiteralPath $readyMarker -Value $requirementsHash -Encoding ASCII
    } else {
        Write-Host "Reusing cached release environment: $environment"
    }

    return $buildPython
}

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
$buildPython = Get-CachedBuildPython $projectRoot
$env:RESUMEDETECTIVE_BUILD_PYTHON = $buildPython
$buildWorkspace = Join-Path ([IO.Path]::GetTempPath()) "ResumeDetective-Build"
$releaseRoot = Join-Path (Split-Path -Parent $projectRoot) "ResumeDetective-Releases"
$version = (Get-Content -LiteralPath (Join-Path $projectRoot "VERSION") -Raw).Trim()
$fullArchive = Join-Path $releaseRoot "ResumeDetective-v$version-windows-x64-full.zip"
$updateArchive = Join-Path $releaseRoot "ResumeDetective-v$version-windows-x64-update.zip"
$expectedOutputs = @(
    $fullArchive, "$fullArchive.sha256",
    $updateArchive, "$updateArchive.sha256"
)

Write-Host "Building ResumeDetective in a temporary clean workspace..."
try {
    $releaseShell = Get-Command pwsh.exe -ErrorAction SilentlyContinue
    if (-not $releaseShell) {
        $releaseShell = Get-Command powershell.exe -ErrorAction Stop
    }
    & $releaseShell.Source -NoProfile -NoLogo -ExecutionPolicy Bypass -File $releaseScript
    if ($LASTEXITCODE -ne 0) {
        throw "Release build failed with exit code $LASTEXITCODE"
    }

    foreach ($requiredOutput in $expectedOutputs) {
        if (-not (Test-Path -LiteralPath $requiredOutput -PathType Leaf)) {
            throw "Release output was not created: $requiredOutput"
        }
    }

    $unexpected = @(Get-ChildItem -LiteralPath $releaseRoot -Force |
        Where-Object {
            -not $_.PSIsContainer -and
            ($_.Name -notmatch '^ResumeDetective-v\d+\.\d+\.\d+-windows-x64(?:-(?:full|update))?\.(?:zip|7z)(?:\.sha256)?$')
        })
    if ($unexpected) {
        Write-Warning "Release directory also contains unrecognized files: $($unexpected.Name -join ', ')"
    }

    Write-Host "Release files ready in: $releaseRoot"
    Write-Host "Upload all four generated files to GitHub Release:"
    foreach ($output in $expectedOutputs) {
        Write-Host "  $output"
    }
}
finally {
    Remove-Item Env:RESUMEDETECTIVE_BUILD_PYTHON -ErrorAction SilentlyContinue
    Remove-TemporaryBuildWorkspace $buildWorkspace
    Write-Host "Temporary build workspace cleaned: $buildWorkspace"
}
