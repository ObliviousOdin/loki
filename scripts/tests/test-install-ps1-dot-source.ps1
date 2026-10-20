# Dot-sourcing loads installer functions without rebinding the embedding host.
# The native suite runner executes this under both Windows PowerShell 5.1 and 7;
# the portable pytest companion also exercises it on any host with pwsh.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
$installScript = Join-Path $repoRoot 'scripts/install.ps1'
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ('loki-dot-source-env-' + [Guid]::NewGuid().ToString('N'))
$ownHome = Join-Path $testRoot 'owned home'
$checkout = Join-Path $testRoot 'checkout'
$script:Failures = 0

function Assert-True {
    param([bool]$Condition, [string]$Label)
    if ($Condition) { Write-Host "PASS: $Label" }
    else { Write-Host "FAIL: $Label"; $script:Failures++ }
}

function Get-EnvironmentSnapshot {
    $snapshot = @{}
    Get-ChildItem Env: | ForEach-Object { $snapshot[$_.Name] = $_.Value }
    return $snapshot
}

function Assert-EnvironmentUnchanged {
    param([hashtable]$Before, [string]$Label)
    $after = Get-EnvironmentSnapshot
    Assert-True ($Before.Count -eq $after.Count) "$Label retains environment names"
    foreach ($name in $Before.Keys) {
        # Only names are logged on failure, never environment values.
        Assert-True ($after.ContainsKey($name) -and $after[$name] -ceq $Before[$name]) "$Label preserves $name"
    }
}

function Restore-EnvironmentSnapshot {
    param([hashtable]$Before)
    Get-ChildItem Env: | ForEach-Object {
        if (-not $Before.ContainsKey($_.Name)) { Remove-Item "Env:$($_.Name)" }
    }
    foreach ($name in $Before.Keys) { Set-Item "Env:$name" $Before[$name] }
}

# Tripwires prevent a broken dot-source guard from starting an installation.
function Invoke-WebRequest { throw 'unexpected download while loading definitions' }
function Invoke-RestMethod { throw 'unexpected download while loading definitions' }
function git { throw 'unexpected git while loading definitions' }
function uv { throw 'unexpected uv while loading definitions' }
function node { throw 'unexpected node while loading definitions' }
function npm { throw 'unexpected npm while loading definitions' }

$original = Get-EnvironmentSnapshot
try {
    foreach ($bound in @($false, $true)) {
        Restore-EnvironmentSnapshot $original
        $env:HERMES_HOME = Join-Path $testRoot 'foreign home'
        $env:HERMES_RUNTIME_DIR = Join-Path $testRoot 'foreign runtime'
        $env:HERMES_DOT_SOURCE_CANARY = 'existing internal value'
        $env:__HERMES_DOT_SOURCE_CANARY = 'existing internal marker'
        $env:LOKI_HOME = $ownHome
        $env:LOKI_RUNTIME_DIR = Join-Path $testRoot 'owned runtime'
        $env:LOKI_DOT_SOURCE_CANARY = 'public value differs from internal value'
        if ($bound) { $env:__LOKI_ENV_BOUND = 'embedding-host-marker' }
        else { Remove-Item Env:__LOKI_ENV_BOUND -ErrorAction SilentlyContinue }
        $before = Get-EnvironmentSnapshot

        . $installScript -LokiHome $ownHome -InstallDir $checkout

        Assert-EnvironmentUnchanged $before "dot-source (bound=$bound)"
        Assert-True ([bool](Get-Command Initialize-ResolvedPaths -CommandType Function)) 'installer functions are available'
        Assert-True ((Get-PmStoreRoot) -ceq $before['HERMES_RUNTIME_DIR']) 'loaded helper sees the unchanged embedding runtime'
        Assert-True (-not (Test-Path -LiteralPath $testRoot)) 'loading definitions creates no install paths'
    }

    # Real invocations must still translate public selectors and discard foreign
    # internal selectors before the existing store/checkout separation guard.
    $psExe = (Get-Process -Id $PID).Path
    Restore-EnvironmentSnapshot $original
    $env:LOKI_HOME = $ownHome
    $env:HERMES_HOME = Join-Path $testRoot 'foreign home'
    $env:HERMES_RUNTIME_DIR = $checkout
    $env:LOKI_RUNTIME_DIR = Join-Path $testRoot 'owned runtime'
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $raw = @(& $psExe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $installScript -HermesHome $checkout -InstallDir $checkout -ShowResolvedPaths 2>&1)
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    Assert-True ($code -eq 0) 'real invocation uses public runtime outside an otherwise refused checkout'
    if ($code -eq 0) {
        $paths = ($raw -join "`n") | ConvertFrom-Json
        Assert-True ($paths.hermes_home -ceq $checkout) 'real invocation preserves explicit home'
        Assert-True ($paths.install_dir -ceq $checkout) 'real invocation preserves explicit checkout'
    }

    Remove-Item Env:LOKI_RUNTIME_DIR -ErrorAction SilentlyContinue
    $env:HERMES_RUNTIME_DIR = $checkout
    $ErrorActionPreference = 'Continue'
    try {
        $raw = @(& $psExe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $installScript -InstallDir $checkout -ShowResolvedPaths 2>&1)
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    Assert-True ($code -eq 0) 'real invocation clears foreign internal runtime before the separation guard'
    if ($code -eq 0) {
        $paths = ($raw -join "`n") | ConvertFrom-Json
        Assert-True ($paths.hermes_home -ceq $ownHome) 'real invocation derives the public home'
        Assert-True ($paths.install_dir -ceq $checkout) 'real invocation keeps the requested checkout'
    }
    Assert-True (-not (Test-Path -LiteralPath $testRoot)) 'resolved-path queries perform no install writes'
} finally {
    Restore-EnvironmentSnapshot $original
}
if ($script:Failures) { throw "$script:Failures dot-source/environment assertions failed" }
Write-Host 'DOT_SOURCE_ENVIRONMENT_OK'
