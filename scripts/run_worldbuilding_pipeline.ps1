param(
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [string]$Template,

    [Parameter(Mandatory = $true)]
    [string]$Workdir,

    [string]$Request = "",
    [string]$Confirmed = "",
    [string]$Expected = "",
    [string]$Config = "",
    [string]$Registry = "",
    [string]$ModeRule = "",
    [string]$RulePack = "",
    [int]$ContextChars = 120,
    [switch]$SkipRender,
    [switch]$SkipValidate
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONDONTWRITEBYTECODE = "1"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
chcp 65001 > $null

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pluginRoot = Split-Path -Parent $scriptRoot
$pipeline = Join-Path $scriptRoot "worldbuilding_pipeline.py"

if (-not $Config) {
    $Config = Join-Path $pluginRoot "assets\default-config.yaml"
}
if (-not $Registry) {
    $Registry = Join-Path $pluginRoot "assets\template-registry.yaml"
}
if (-not $ModeRule) {
    $ModeRule = Join-Path $pluginRoot "assets\mode-rules\entity.yaml"
}
if (-not $RulePack) {
    $RulePack = Join-Path $pluginRoot "assets\rule-packs\entity-medicine.yaml"
}

[System.IO.Directory]::CreateDirectory($Workdir) | Out-Null

function Invoke-PipelineStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host "== $Name =="
    $output = @(& python -B $pipeline @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    foreach ($line in $output) {
        Write-Host $line
    }
    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode"
    }

    if ($output.Count -gt 0) {
        try {
            return ($output[-1] | ConvertFrom-Json)
        } catch {
            return $null
        }
    }
    return $null
}

$inspect = Invoke-PipelineStep -Name "inspect" -Arguments @(
    "inspect",
    "--config", $Config,
    "--input", $Source,
    "--template", $Template,
    "--workdir", $Workdir
)

$segment = Invoke-PipelineStep -Name "segment" -Arguments @(
    "segment",
    "--config", $Config,
    "--input", $Source,
    "--template", $Template,
    "--workdir", $Workdir
)

$route = Invoke-PipelineStep -Name "route-template" -Arguments @(
    "route-template",
    "--config", $Config,
    "--input", $Source,
    "--template", $Template,
    "--registry", $Registry,
    "--request", $Request,
    "--workdir", $Workdir
)

$candidates = Invoke-PipelineStep -Name "extract-candidates" -Arguments @(
    "extract-candidates",
    "--config", $Config,
    "--input", $Source,
    "--template", $Template,
    "--mode-rule", $ModeRule,
    "--rule-pack", $RulePack,
    "--workdir", $Workdir
)

$evidence = Invoke-PipelineStep -Name "build-evidence" -Arguments @(
    "build-evidence",
    "--config", $Config,
    "--input", $Source,
    "--template", $Template,
    "--context-chars", "$ContextChars",
    "--workdir", $Workdir
)

$render = $null
if ($Confirmed -and -not $SkipRender) {
    $render = Invoke-PipelineStep -Name "render" -Arguments @(
        "render",
        "--config", $Config,
        "--confirmed", $Confirmed,
        "--template", $Template,
        "--registry", $Registry,
        "--workdir", $Workdir
    )
} elseif (-not $Confirmed) {
    Write-Host "== render skipped: no -Confirmed file provided =="
}

$validation = $null
if ($Expected -and -not $SkipValidate) {
    $validateArgs = @(
        "validate",
        "--config", $Config,
        "--expected", $Expected,
        "--workdir", $Workdir
    )
    if ($Confirmed) {
        $validateArgs += @("--confirmed", $Confirmed)
    }
    if ($render -and $render.output) {
        $validateArgs += @("--report", $render.output)
    }
    $validation = Invoke-PipelineStep -Name "validate" -Arguments $validateArgs
} elseif (-not $Expected) {
    Write-Host "== validate skipped: no -Expected file provided =="
}

[pscustomobject]@{
    inspect = $inspect.output
    segments = $segment.output
    route = $route.output
    candidates = $candidates.output
    evidence = $evidence.output
    report = if ($render) { $render.output } else { $null }
    validation = if ($validation) { $validation.output } else { $null }
} | ConvertTo-Json -Depth 4
