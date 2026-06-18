param(
    [string]$Template = "",
    [string]$TemplateDir = "",

    [Parameter(Mandatory = $true)]
    [string]$SourceFile,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    [string]$Config = "",
    [string]$Model = "",
    [int]$Passes = 0,
    [int]$Workers = 0,
    [int]$MaxCharBuffer = 0,
    [int]$TemplateLimit = 0,
    [int]$LimitChars = 0,
    [switch]$DryRun,
    [switch]$NoVisualization
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONDONTWRITEBYTECODE = "1"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
chcp 65001 > $null

if ([string]::IsNullOrWhiteSpace($Template) -and [string]::IsNullOrWhiteSpace($TemplateDir)) {
    throw "Missing -Template or -TemplateDir."
}
if (-not [string]::IsNullOrWhiteSpace($Template) -and -not [string]::IsNullOrWhiteSpace($TemplateDir)) {
    throw "Use only one of -Template or -TemplateDir."
}
if (-not (Test-Path -LiteralPath $SourceFile)) {
    throw "Source file not found: $SourceFile"
}
if (-not [string]::IsNullOrWhiteSpace($Template) -and -not (Test-Path -LiteralPath $Template)) {
    throw "Template not found: $Template"
}
if (-not [string]::IsNullOrWhiteSpace($TemplateDir) -and -not (Test-Path -LiteralPath $TemplateDir)) {
    throw "TemplateDir not found: $TemplateDir"
}
if (-not [string]::IsNullOrWhiteSpace($Config) -and -not (Test-Path -LiteralPath $Config)) {
    throw "Config not found: $Config"
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pipeline = Join-Path $scriptRoot "worldbuilding_pipeline.py"

$arguments = @("run-extraction", "--source-file", $SourceFile, "--output-dir", $OutputDir)
if (-not [string]::IsNullOrWhiteSpace($Template)) {
    $arguments += @("--template", $Template)
} else {
    $arguments += @("--template-dir", $TemplateDir)
}
if (-not [string]::IsNullOrWhiteSpace($Model)) { $arguments += @("--model", $Model) }
if (-not [string]::IsNullOrWhiteSpace($Config)) { $arguments += @("--config", $Config) }
if ($Passes -gt 0) { $arguments += @("--passes", "$Passes") }
if ($Workers -gt 0) { $arguments += @("--workers", "$Workers") }
if ($MaxCharBuffer -gt 0) { $arguments += @("--max-char-buffer", "$MaxCharBuffer") }
if ($TemplateLimit -gt 0) { $arguments += @("--template-limit", "$TemplateLimit") }
if ($LimitChars -gt 0) { $arguments += @("--limit-chars", "$LimitChars") }
if ($DryRun) { $arguments += "--dry-run" }
if ($NoVisualization) { $arguments += "--no-visualization" }

& python -B $pipeline @arguments
if ($LASTEXITCODE -ne 0) {
    throw "run-extraction failed with exit code $LASTEXITCODE"
}
