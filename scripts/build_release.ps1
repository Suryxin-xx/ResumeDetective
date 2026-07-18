$ErrorActionPreference = "Stop"

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
$stageRoot = Join-Path $projectRoot "build\release-src"
$stageBuildRoot = Join-Path $stageRoot "build"
$stageDistRoot = Join-Path $stageRoot "dist"

$buildFull = [IO.Path]::GetFullPath((Join-Path $projectRoot "build")).TrimEnd('\')
$stageFull = [IO.Path]::GetFullPath($stageRoot).TrimEnd('\')
if (-not $stageFull.StartsWith($buildFull + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to recreate an unsafe staging path: $stageFull"
}

Write-Host "Preparing clean release workspace..."

& python (Join-Path $PSScriptRoot "check_repository_safety.py")
if ($LASTEXITCODE -ne 0) {
    throw "Repository safety check failed. Refusing to build."
}

if (Test-Path $stageRoot) {
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
    "ResumeDetectiveGateway.spec",
    "install.bat",
    "README.md",
    "LICENSE",
    ".gitignore",
    "PACKAGING.md",
    "VERSION",
    "requirements.txt"
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

$publicDirectories = @("data.example", ".github", ".githooks")
foreach ($directory in $publicDirectories) {
    $sourceDirectory = Join-Path $projectRoot $directory
    if (Test-Path -LiteralPath $sourceDirectory -PathType Container) {
        Copy-Item -LiteralPath $sourceDirectory -Destination (Join-Path $stageRoot $directory) -Recurse
    }
}

$screenshotsSrc = Join-Path $projectRoot "screenshots"
$screenshotsDst = Join-Path $stageRoot "screenshots"
$publicScreenshots = @(
    "app-board-kanban.png", "app-board-table.png", "app-tasks.png",
    "app-materials.png", "app-ai.png", "app-targets.png", "app-tools.png",
    "web-overview.png", "web-board.png", "web-applications.png"
)
if (Test-Path -LiteralPath $screenshotsSrc -PathType Container) {
    New-Item -ItemType Directory -Path $screenshotsDst -Force | Out-Null
    foreach ($name in $publicScreenshots) {
        $src = Join-Path $screenshotsSrc $name
        if (Test-Path -LiteralPath $src -PathType Leaf) {
            Copy-Item -LiteralPath $src -Destination (Join-Path $screenshotsDst $name)
        }
    }
}

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
  "tab_order": ["board", "tasks", "materials", "ai", "targets", "tools"]
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

Write-Host ""
Write-Host "Clean release workspace created at: $stageRoot"
Write-Host "Build from that folder instead of packaging your live development directory."

$pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
if ($pyinstaller) {
    Write-Host ""
    Write-Host "PyInstaller found. Building Windows package now..."
    Push-Location $stageRoot
    try {
        & pyinstaller ResumeDetective.spec
        if ($LASTEXITCODE -eq 0) {
            & pyinstaller ResumeDetectiveGateway.spec
            if ($LASTEXITCODE -ne 0) {
                throw "Gateway executable build failed."
            }
            $appDist = Join-Path $stageDistRoot "ResumeDetective"
            Copy-Item -LiteralPath (Join-Path $stageDistRoot "ResumeDetectiveGateway.exe") -Destination (Join-Path $appDist "ResumeDetectiveGateway.exe") -Force
            Copy-Item -LiteralPath (Join-Path $stageRoot $gatewayLauncherName) -Destination (Join-Path $appDist $gatewayLauncherName) -Force
            Copy-Item -LiteralPath (Join-Path $stageRoot "README.md") -Destination (Join-Path $appDist "README.md") -Force
            Copy-Item -LiteralPath (Join-Path $stageRoot "LICENSE") -Destination (Join-Path $appDist "LICENSE") -Force
            Copy-Item -LiteralPath (Join-Path $stageRoot "VERSION") -Destination (Join-Path $appDist "VERSION") -Force
            if (Test-Path -LiteralPath (Join-Path $stageRoot "screenshots") -PathType Container) {
                Copy-Item -LiteralPath (Join-Path $stageRoot "screenshots") -Destination (Join-Path $appDist "screenshots") -Recurse -Force
            }

            $requiredOutputs = @(
                (Join-Path $appDist "ResumeDetective.exe"),
                (Join-Path $appDist "ResumeDetectiveGateway.exe"),
                (Join-Path $appDist $gatewayLauncherName),
                (Join-Path $appDist "VERSION")
            )
            foreach ($requiredOutput in $requiredOutputs) {
                if (-not (Test-Path -LiteralPath $requiredOutput -PathType Leaf)) {
                    throw "Release output is incomplete: $requiredOutput"
                }
            }
            Write-Host ""
            Write-Host "Package build completed."
            Write-Host "Output folder: $stageRoot\\dist\\ResumeDetective"

            $version = (Get-Content -LiteralPath (Join-Path $stageRoot "VERSION") -Raw).Trim()
            $archive = Join-Path $stageDistRoot "ResumeDetective-v$version-windows-x64.zip"
            if (Test-Path -LiteralPath $archive) {
                Remove-Item -LiteralPath $archive -Force
            }
            Compress-Archive -Path $appDist -DestinationPath $archive -CompressionLevel Optimal
            $archiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
            Set-Content -LiteralPath "$archive.sha256" -Value "$archiveHash  $([IO.Path]::GetFileName($archive))" -Encoding ASCII
            Write-Host "GitHub Release archive: $archive"
            Write-Host "SHA256 file: $archive.sha256"
        } else {
            Write-Host ""
            Write-Host "PyInstaller finished with a non-zero exit code."
            Write-Host "Please inspect: $stageRoot\\build\\ResumeDetective"
            exit 1
        }
    } finally {
        Pop-Location
    }
} else {
    throw "PyInstaller was not found in PATH. Install project dependencies before building the EXE package."
}
