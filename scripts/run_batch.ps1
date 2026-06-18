param(
    [Parameter(Mandatory = $true)]
    [string]$TemplateDir,

    [Parameter(Mandatory = $true)]
    [string]$SourceDir,

    [Parameter(Mandatory = $true)]
    [string]$SourceFile,

    [ValidateSet("overwrite", "merge")]
    [string]$Mode = "overwrite",

    [string]$FrameworkRoot = "",
    [string]$PromptContract = "",
    [string]$PythonExe = "python",
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONDONTWRITEBYTECODE = "1"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
chcp 65001 > $null

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pipeline = Join-Path $scriptRoot "worldbuilding_pipeline.py"

if (-not $FrameworkRoot) {
    $FrameworkRoot = Join-Path $SourceDir ".worldbuilding-framework"
}
if (-not $PromptContract) {
    $pluginRoot = Split-Path -Parent $scriptRoot
    $PromptContract = Join-Path $pluginRoot "assets\batch-prompt-contract.yaml"
}
if (-not $Output) {
    $Output = Join-Path $SourceDir "batch-plan.json"
}

$arguments = @(
    "batch-plan",
    "--template-dir", $TemplateDir,
    "--source-dir", $SourceDir,
    "--source-file", $SourceFile,
    "--mode", $Mode,
    "--framework-root", $FrameworkRoot,
    "--prompt-contract", $PromptContract,
    "--output", $Output
)

& $PythonExe -B $pipeline @arguments
if ($LASTEXITCODE -ne 0) {
    throw "batch-plan failed with exit code $LASTEXITCODE"
}
