param([switch]$Staged)

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Push-Location $root
try {
    $safeRoot = $root.Replace('\','/')
    if ($Staged) { $files = @(git -c "safe.directory=$safeRoot" -c core.quotepath=false diff --cached --name-only --diff-filter=ACMR) }
    else { $files = @(git -c "safe.directory=$safeRoot" -c core.quotepath=false ls-files --cached --others --exclude-standard) }
    if ($LASTEXITCODE -ne 0) { throw "Unable to read the Git file list." }
    $pathRules = @('^data/', '^backups/', '^releases/', '^ResumeDetective\.exe$', '^Reasonix Cli/', '(^|/)node_modules/', '(^|/)\.env$', '\.(db|db-shm|db-wal|enc|xlsx|jsonl)$', '(^|/)reasonix\.exe$')
    $secretRules = @('sk-[A-Za-z0-9_-]{20,}', '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----', '(?i)(deepseek_api_key|reasonix_api_key)\s*=\s*[^\s#]{12,}')
    $textExtensions = @('.go','.ts','.tsx','.js','.mjs','.json','.md','.yml','.yaml','.ps1','.sh','.bat','.txt','.html','.css','.example')
    $problems = [System.Collections.Generic.List[string]]::new()
    foreach ($relative in $files) {
        if (-not $relative) { continue }
        $normalized = $relative.Replace('\','/')
        foreach ($rule in $pathRules) {
            if ($normalized -match $rule -and $normalized -notmatch '\.env\.example$') { $problems.Add("Blocked private path: $normalized"); break }
        }
        $full = Join-Path $root $relative
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { continue }
        $item = Get-Item -LiteralPath $full
        if ($item.Length -gt 5MB -or $textExtensions -notcontains $item.Extension.ToLowerInvariant()) { continue }
        $content = Get-Content -LiteralPath $full -Raw -Encoding UTF8
        foreach ($rule in $secretRules) {
            if ($content -match $rule -and $normalized -notmatch '\.env\.example$') { $problems.Add("Possible secret in: $normalized"); break }
        }
    }
    if ($problems.Count) {
        $problems | Sort-Object -Unique | ForEach-Object { Write-Error $_ }
        exit 1
    }
    Write-Host "[safety] Passed. Checked $($files.Count) candidate files."
}
finally { Pop-Location }
