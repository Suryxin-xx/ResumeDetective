$ErrorActionPreference = "Stop"

function Get-SignTool {
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $kitsRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path -LiteralPath $kitsRoot -PathType Container) {
        $candidate = Get-ChildItem -LiteralPath $kitsRoot -Filter signtool.exe -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }
    return $null
}

function Invoke-OptionalCodeSigning([string]$executable) {
    $thumbprint = $env:RESUMEDETECTIVE_SIGN_SHA1
    $pfxPath = $env:RESUMEDETECTIVE_SIGN_PFX
    if (-not $thumbprint -and -not $pfxPath) {
        Write-Warning "Release is unsigned. Configure Authenticode signing to reduce SmartScreen/antivirus warnings."
        return $false
    }

    $signTool = Get-SignTool
    if (-not $signTool) {
        throw "Signing was requested, but signtool.exe was not found."
    }
    $timestamp = if ($env:RESUMEDETECTIVE_SIGN_TIMESTAMP) {
        $env:RESUMEDETECTIVE_SIGN_TIMESTAMP
    } else {
        "http://timestamp.digicert.com"
    }
    $arguments = @("sign", "/fd", "SHA256", "/td", "SHA256", "/tr", $timestamp)
    if ($thumbprint) {
        $arguments += @("/sha1", ($thumbprint -replace "\s", ""))
    } else {
        if (-not (Test-Path -LiteralPath $pfxPath -PathType Leaf)) {
            throw "Signing certificate was not found: $pfxPath"
        }
        $arguments += @("/f", $pfxPath)
        if ($env:RESUMEDETECTIVE_SIGN_PASSWORD) {
            $arguments += @("/p", $env:RESUMEDETECTIVE_SIGN_PASSWORD)
        }
    }
    $arguments += $executable
    & $signTool @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode signing failed."
    }
    & $signTool verify /pa /q $executable
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode signature verification failed."
    }
    Write-Host "Authenticode signature verified: $executable"
    return $true
}

function Write-VersionResource([string]$path, [string]$version) {
    $parts = @($version.Split(".") | ForEach-Object { [int]$_ })
    if ($parts.Count -ne 3) {
        throw "VERSION must use semantic x.y.z format: $version"
    }
    $tuple = "$($parts[0]), $($parts[1]), $($parts[2]), 0"
    $content = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($tuple),
    prodvers=($tuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404B0',
        [
          StringStruct('CompanyName', 'Resume Detective Open Source Project'),
          StringStruct('FileDescription', 'Resume Detective - Local-first job application manager'),
          StringStruct('FileVersion', '$version'),
          StringStruct('InternalName', 'ResumeDetective'),
          StringStruct('LegalCopyright', 'Copyright (c) Resume Detective contributors'),
          StringStruct('OriginalFilename', 'ResumeDetective.exe'),
          StringStruct('ProductName', 'Resume Detective'),
          StringStruct('ProductVersion', '$version')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"@
    Set-Content -LiteralPath $path -Value $content -Encoding UTF8
}

function Assert-NoLocalSecrets([string]$root) {
    $blockedNames = @(".env", "secret.json.enc", "data.db", "config.toml")
    $blocked = Get-ChildItem -LiteralPath $root -Recurse -Force -File -ErrorAction SilentlyContinue |
        Where-Object { $blockedNames -contains $_.Name -or $_.FullName -match "\\data\\(Resumes|Attachments|chat_history|reasonix\\(cache|projects|runtime))\\" }
    if ($blocked) {
        $paths = ($blocked | Select-Object -ExpandProperty FullName) -join "`n"
        throw "Release staging contains local/private files:`n$paths"
    }
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = if ($env:RESUMEDETECTIVE_BUILD_PYTHON) {
    $env:RESUMEDETECTIVE_BUILD_PYTHON
} else {
    (Get-Command python -ErrorAction Stop).Source
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Build Python was not found: $python"
}
$stageRoot = Join-Path ([IO.Path]::GetTempPath()) "ResumeDetective-Build"
$releaseRoot = Join-Path (Split-Path -Parent $projectRoot) "ResumeDetective-Releases"
$stageBuildRoot = Join-Path $stageRoot "build"
$stageDistRoot = Join-Path $stageRoot "dist"

$stageFull = [IO.Path]::GetFullPath($stageRoot).TrimEnd('\')
$expectedStageFull = [IO.Path]::GetFullPath(
    (Join-Path ([IO.Path]::GetTempPath()) "ResumeDetective-Build")
).TrimEnd('\')
if (-not $stageFull.Equals($expectedStageFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to recreate an unsafe staging path: $stageFull"
}
$releaseFull = [IO.Path]::GetFullPath($releaseRoot).TrimEnd('\')
$expectedReleaseFull = [IO.Path]::GetFullPath(
    (Join-Path (Split-Path -Parent $projectRoot) "ResumeDetective-Releases")
).TrimEnd('\')
if (-not $releaseFull.Equals($expectedReleaseFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to publish to an unsafe release path: $releaseFull"
}

Write-Host "Preparing clean release workspace..."

& $python -B -m unittest discover -s (Join-Path $projectRoot "tests") -p "test_*.py" -v
if ($LASTEXITCODE -ne 0) {
    throw "Automated tests failed. Refusing to build."
}

& $python (Join-Path $PSScriptRoot "check_repository_safety.py")
if ($LASTEXITCODE -ne 0) {
    throw "Repository safety check failed. Refusing to build."
}

if (Test-Path $stageRoot) {
    # Cloud-backed folders may preserve P/U/readonly attributes in a previous
    # generated snapshot. Clear attributes only inside the already-validated
    # build staging root before recreating it.
    Get-ChildItem -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue |
        ForEach-Object {
            try { $_.Attributes = [IO.FileAttributes]::Normal } catch { }
        }
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $stageRoot | Out-Null

$includeFiles = @(
    "main.py",
    "gateway_main.py",
    "local_gateway.py",
    "excel_sync.py",
    "main_window.py",
    "board_widget.py",
    "table_view.py",
    "detail_dialog.py",
    "dialogs.py",
    "materials_widget.py",
    "job_targets_widget.py",
    "tasks_widget.py",
    "interviews_widget.py",
    "data_safety.py",
    "gateway_instance.py",
    "db_manager.py",
    "models.py",
    "ai_service.py",
    "cli_ai.py",
    "chat_history.py",
    "io_export.py",
    "file_ops.py",
    "secure_store.py",
    "config_manager.py",
    "paths.py",
    "tools_pdf2img.py",
    "tools_imgpdf.py",
    "ResumeDetective.spec",
    "install.bat",
    "README.md",
    "LICENSE",
    ".gitignore",
    "PACKAGING.md",
    "VERSION",
    "RUNTIME_VERSION",
    "requirements.txt",
    "requirements-build.txt"
)

foreach ($file in $includeFiles) {
    $src = Join-Path $projectRoot $file
    if (-not (Test-Path -LiteralPath $src -PathType Leaf)) {
        throw "Required release file is missing: $src"
    }
    Copy-Item -LiteralPath $src -Destination (Join-Path $stageRoot $file)
}

$gatewayLaunchers = @(Get-ChildItem -LiteralPath $projectRoot -File -Filter "*.bat" |
    Where-Object { $_.Name -ne "install.bat" })
if ($gatewayLaunchers.Count -ne 1) {
    throw "Expected exactly one gateway launcher BAT file in the project root."
}
$gatewayLauncherName = $gatewayLaunchers[0].Name
Copy-Item -LiteralPath $gatewayLaunchers[0].FullName -Destination (Join-Path $stageRoot $gatewayLauncherName)

$testsSrc = Join-Path $projectRoot "tests"
if (Test-Path -LiteralPath $testsSrc -PathType Container) {
    Copy-Item -LiteralPath $testsSrc -Destination (Join-Path $stageRoot "tests") -Recurse
}

$scriptsSrc = Join-Path $projectRoot "scripts"
if (Test-Path -LiteralPath $scriptsSrc -PathType Container) {
    Copy-Item -LiteralPath $scriptsSrc -Destination (Join-Path $stageRoot "scripts") -Recurse
}

$publicDirectories = @("data.example", ".github")
foreach ($directory in $publicDirectories) {
    $sourceDirectory = Join-Path $projectRoot $directory
    if (Test-Path -LiteralPath $sourceDirectory -PathType Container) {
        Copy-Item -LiteralPath $sourceDirectory -Destination (Join-Path $stageRoot $directory) -Recurse
    }
}

# Screenshots remain on GitHub and are intentionally not duplicated in the
# downloadable Windows package.

$dataDirs = @(
    "data",
    "data\Resumes",
    "data\chat_history",
    "data\reasonix"
)

foreach ($dir in $dataDirs) {
    New-Item -ItemType Directory -Path (Join-Path $stageRoot $dir) -Force | Out-Null
}

New-Item -ItemType Directory -Path $stageBuildRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stageBuildRoot "ResumeDetective") -Force | Out-Null
New-Item -ItemType Directory -Path $stageDistRoot -Force | Out-Null

# Ship only a template. The real Reasonix .env is created in the user's data directory.
$envExample = Join-Path $projectRoot "data.example\reasonix\.env.example"
$envExampleDst = Join-Path $stageRoot "data\reasonix\.env.example"
if (Test-Path $envExample) {
    Copy-Item -LiteralPath $envExample -Destination $envExampleDst
} else {
    @'
# Copy this file to .env only for local development.
# DEEPSEEK_API_KEY=your-api-key-here
# REASONIX_API_KEY=your-api-key-here
'@ | Set-Content -LiteralPath $envExampleDst -Encoding UTF8
}

@'
{
  "tab_order": ["board", "tasks", "interviews", "materials", "ai", "targets", "tools"]
}
'@ | Set-Content -Path (Join-Path $stageRoot "data\config.json") -Encoding UTF8

@'
Release package notes:
1. This folder does not include your local API key, chat history, database, or runtime cache.
2. End users will generate their own data.db and encrypted key store on first launch.
3. Reasonix CLI is not bundled. Users download it from its upstream project when needed.
4. Never rename .env.example to .env inside the source tree.
'@ | Set-Content -Path (Join-Path $stageRoot "data\README.txt") -Encoding UTF8

Assert-NoLocalSecrets $stageRoot

$version = (Get-Content -LiteralPath (Join-Path $stageRoot "VERSION") -Raw).Trim()
$runtimeVersion = (Get-Content -LiteralPath (Join-Path $stageRoot "RUNTIME_VERSION") -Raw).Trim()
Write-VersionResource (Join-Path $stageRoot "file_version_info.txt") $version

Write-Host ""
Write-Host "Temporary clean build workspace created at: $stageRoot"

Write-Host ""
Write-Host "Building one-folder Windows package with a shared runtime..."
Push-Location $stageRoot
try {
    & $python -m PyInstaller ResumeDetective.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed. Inspect: $stageRoot\\build\\ResumeDetective"
    }
} finally {
    Pop-Location
}

$appDist = Join-Path $stageDistRoot "ResumeDetective"
$appExecutable = Join-Path $appDist "ResumeDetective.exe"
Copy-Item -LiteralPath (Join-Path $stageRoot $gatewayLauncherName) -Destination (Join-Path $appDist $gatewayLauncherName) -Force
Copy-Item -LiteralPath (Join-Path $stageRoot "README.md") -Destination (Join-Path $appDist "README.md") -Force
Copy-Item -LiteralPath (Join-Path $stageRoot "LICENSE") -Destination (Join-Path $appDist "LICENSE") -Force
Copy-Item -LiteralPath (Join-Path $stageRoot "VERSION") -Destination (Join-Path $appDist "VERSION") -Force
Copy-Item -LiteralPath (Join-Path $stageRoot "RUNTIME_VERSION") -Destination (Join-Path $appDist "RUNTIME_VERSION") -Force

$signed = [bool](Invoke-OptionalCodeSigning $appExecutable | Select-Object -Last 1)
$packageJson = & $python -c @'
import importlib.metadata as metadata
import json
names = ["PyInstaller", "PyQt6", "requests", "openpyxl", "PyMuPDF", "Pillow", "comtypes"]
print(json.dumps({name: metadata.version(name) for name in names}, ensure_ascii=False))
'@
if ($LASTEXITCODE -ne 0) {
    throw "Unable to collect runtime package versions."
}
$runtimeManifest = [ordered]@{
    schema_version = 1
    runtime_version = $runtimeVersion
    app_version = $version
    python = (& $python -c "import platform; print(platform.python_version())").Trim()
    architecture = (& $python -c "import platform; print(platform.machine())").Trim()
    packaging = "pyinstaller-onedir"
    signed = $signed
    packages = ($packageJson | ConvertFrom-Json)
}
$runtimeManifestPath = Join-Path $appDist "runtime-manifest.json"
$runtimeManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $runtimeManifestPath -Encoding UTF8

$pythonRuntimeDll = Get-ChildItem -LiteralPath (Join-Path $appDist "_internal") -Filter "python3*.dll" -File |
    Select-Object -First 1
if (-not $pythonRuntimeDll) {
    throw "Bundled Python runtime DLL was not found."
}
$requiredOutputs = @(
    $appExecutable,
    $pythonRuntimeDll.FullName,
    (Join-Path $appDist $gatewayLauncherName),
    (Join-Path $appDist "VERSION"),
    (Join-Path $appDist "RUNTIME_VERSION"),
    $runtimeManifestPath
)
foreach ($requiredOutput in $requiredOutputs) {
    if (-not (Test-Path -LiteralPath $requiredOutput -PathType Leaf)) {
        throw "Release output is incomplete: $requiredOutput"
    }
}

$updateRoot = Join-Path $stageDistRoot "ResumeDetective-update"
New-Item -ItemType Directory -Path $updateRoot -Force | Out-Null
foreach ($file in @(
    "ResumeDetective.exe", $gatewayLauncherName, "VERSION",
    "RUNTIME_VERSION", "runtime-manifest.json"
)) {
    Copy-Item -LiteralPath (Join-Path $appDist $file) -Destination (Join-Path $updateRoot $file) -Force
}
$updateReadme = @(
    "Resume Detective 增量更新包",
    "",
    "适用条件：",
    "1. 先退出桌面应用和网页看板托盘程序。",
    "2. 已安装版本的 RUNTIME_VERSION 必须与本包一致（当前为 $runtimeVersion）。",
    "3. 将本包全部文件覆盖到现有 ResumeDetective 文件夹；不要删除 _internal 和 data。",
    "",
    "如果 RUNTIME_VERSION 不一致，或首次安装，请下载 full 完整包。"
) -join [Environment]::NewLine
Set-Content -LiteralPath (Join-Path $updateRoot "更新说明.txt") -Value $updateReadme -Encoding UTF8

$fullArchive = Join-Path $stageDistRoot "ResumeDetective-v$version-windows-x64-full.zip"
$updateArchive = Join-Path $stageDistRoot "ResumeDetective-v$version-windows-x64-update.zip"
foreach ($archive in @($fullArchive, $updateArchive)) {
    if (Test-Path -LiteralPath $archive -PathType Leaf) {
        Remove-Item -LiteralPath $archive -Force
    }
}
Compress-Archive -Path $appDist -DestinationPath $fullArchive -CompressionLevel Optimal
Compress-Archive -Path (Join-Path $updateRoot "*") -DestinationPath $updateArchive -CompressionLevel Optimal

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
foreach ($archive in @($fullArchive, $updateArchive)) {
    $archiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    $hashPath = "$archive.sha256"
    Set-Content -LiteralPath $hashPath -Value "$archiveHash  $([IO.Path]::GetFileName($archive))" -Encoding ASCII
    $publishedArchive = Join-Path $releaseRoot ([IO.Path]::GetFileName($archive))
    Copy-Item -LiteralPath $archive -Destination $publishedArchive -Force
    Copy-Item -LiteralPath $hashPath -Destination "$publishedArchive.sha256" -Force
    Write-Host "GitHub Release asset: $publishedArchive"
}

Write-Host ""
Write-Host "Package build completed."
Write-Host "Full package: $fullArchive"
Write-Host "Incremental update: $updateArchive"
