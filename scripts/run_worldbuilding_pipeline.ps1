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
    [string]$Curation = "",
    [string]$Decisions = "",
    [string]$ReviewPack = "",
    [int]$ShardSize = 0,
    [string]$ReviewPartsDir = "",
    [string]$ShardManifest = "",
    [string]$Route = "",
    [string]$OutputReport = "",
    [string]$AuditMarkdownReport = "",
    [string]$AuditOutput = "",
    [string]$DraftMode = "",
    [string]$RunManifest = "",
    [int]$ContextChars = 120,
    [switch]$MakeReviewPack,
    [switch]$MergeReviewed,
    [switch]$SplitReviewPack,
    [switch]$DraftDecisions,
    [switch]$CollectDecisionParts,
    [switch]$ValidateDecisions,
    [switch]$FinalizeReviewed,
    [switch]$AuditConfirmed,
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

if (($MakeReviewPack -or $MergeReviewed) -and [string]::IsNullOrWhiteSpace($Curation)) {
    throw "Missing -Curation: -MakeReviewPack or -MergeReviewed requires a curation yaml."
}
if ($MergeReviewed -and [string]::IsNullOrWhiteSpace($Decisions)) {
    throw "Missing -Decisions: -MergeReviewed requires a review decisions JSONL."
}

[System.IO.Directory]::CreateDirectory($Workdir) | Out-Null

function Invoke-PipelineStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
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

$reviewPipelineRequested = $SplitReviewPack -or $DraftDecisions -or $CollectDecisionParts -or $ValidateDecisions -or $FinalizeReviewed -or $AuditConfirmed
$legacyPipelineRequested = (-not $reviewPipelineRequested) -or $MakeReviewPack -or $MergeReviewed

$inspect = $null
$segment = $null
$routeResult = $null
$candidates = $null
$evidence = $null
$legacyReviewPackResult = $null
$mergeReviewedResult = $null
$render = $null
$validation = $null

if ($legacyPipelineRequested) {
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

    $routeArgs = @(
        "route-template",
        "--config", $Config,
        "--input", $Source,
        "--template", $Template,
        "--registry", $Registry,
        "--workdir", $Workdir
    )
    if (-not [string]::IsNullOrWhiteSpace($Request)) {
        $routeArgs += @("--request", $Request)
    }
    $routeResult = Invoke-PipelineStep -Name "route-template" -Arguments $routeArgs

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

    if ($MakeReviewPack -or $MergeReviewed) {
        $legacyReviewPackResult = Invoke-PipelineStep -Name "make-review-pack" -Arguments @(
            "make-review-pack",
            "--workdir", $Workdir,
            "--curation", $Curation
        )
    }

    if ($MergeReviewed) {
        $mergeArgs = @(
            "merge-reviewed",
            "--workdir", $Workdir,
            "--curation", $Curation,
            "--decisions", $Decisions
        )
        if ($legacyReviewPackResult -and $legacyReviewPackResult.output_jsonl) {
            $mergeArgs += @("--review-pack", [string]$legacyReviewPackResult.output_jsonl)
        }
        $mergeReviewedResult = Invoke-PipelineStep -Name "merge-reviewed" -Arguments $mergeArgs
        if ($mergeReviewedResult -and $mergeReviewedResult.output_confirmed) {
            $Confirmed = [string]$mergeReviewedResult.output_confirmed
        } else {
            $Confirmed = Join-Path $Workdir "confirmed-items.json"
        }
    }

    if ($Confirmed -and -not $SkipRender) {
        $renderArgs = @(
            "render",
            "--config", $Config,
            "--confirmed", $Confirmed,
            "--template", $Template,
            "--registry", $Registry,
            "--workdir", $Workdir
        )
        if ($OutputReport -ne "") { $renderArgs += @("--output", $OutputReport) }
        $render = Invoke-PipelineStep -Name "render" -Arguments $renderArgs
    } elseif (-not $Confirmed) {
        Write-Host "== render skipped: no -Confirmed file provided =="
    }

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
}

$baseArgs = @("--workdir", $Workdir)
if ($Curation -ne "") { $baseArgs += @("--curation", $Curation) }

$splitArgs = @("split-review-pack") + $baseArgs
if ($ReviewPack -ne "") { $splitArgs += @("--review-pack", $ReviewPack) }
if ($ShardSize -gt 0) { $splitArgs += @("--entries-per-shard", "$ShardSize") }
if ($ReviewPartsDir -ne "") { $splitArgs += @("--parts-dir", $ReviewPartsDir) }
if ($ShardManifest -ne "") { $splitArgs += @("--manifest", $ShardManifest) }

$draftArgs = @("draft-decisions") + $baseArgs
if ($ReviewPack -ne "") { $draftArgs += @("--review-pack", $ReviewPack) }
if ($DraftMode -ne "") { $draftArgs += @("--mode", $DraftMode) }
if ($Decisions -ne "") { $draftArgs += @("--output", $Decisions) }

$collectArgs = @("collect-decision-parts") + $baseArgs
if ($ShardManifest -ne "") { $collectArgs += @("--manifest", $ShardManifest) }
if ($ReviewPartsDir -ne "") { $collectArgs += @("--parts-dir", $ReviewPartsDir) }
if ($Decisions -ne "") { $collectArgs += @("--output", $Decisions) }
if ($OutputReport -ne "") { $collectArgs += @("--report", $OutputReport) }

$validateDecisionArgs = @("validate-decisions") + $baseArgs
if ($ReviewPack -ne "") { $validateDecisionArgs += @("--review-pack", $ReviewPack) }
if ($Decisions -ne "") { $validateDecisionArgs += @("--decisions", $Decisions) }
if ($Expected -ne "") { $validateDecisionArgs += @("--expected", $Expected) }
if ($OutputReport -ne "") { $validateDecisionArgs += @("--output", $OutputReport) }

$finalizeArgs = @("finalize-reviewed") + $baseArgs
if ($ReviewPack -ne "") { $finalizeArgs += @("--review-pack", $ReviewPack) }
if ($Decisions -ne "") { $finalizeArgs += @("--decisions", $Decisions) }
if ($Config -ne "") { $finalizeArgs += @("--config", $Config) }
if ($Expected -ne "") { $finalizeArgs += @("--expected", $Expected) }
if ($Template -ne "") { $finalizeArgs += @("--template", $Template) }
if ($Route -ne "") { $finalizeArgs += @("--route", $Route) }
if ($OutputReport -ne "") { $finalizeArgs += @("--output-report", $OutputReport) }
if ($RunManifest -ne "") { $finalizeArgs += @("--run-manifest", $RunManifest) }

$auditArgs = @("audit-confirmed") + $baseArgs
if ($Confirmed -ne "") { $auditArgs += @("--confirmed", $Confirmed) }
if ($Expected -ne "") { $auditArgs += @("--expected", $Expected) }
if ($AuditMarkdownReport -ne "") { $auditArgs += @("--report", $AuditMarkdownReport) }
if ($AuditOutput -ne "") { $auditArgs += @("--output", $AuditOutput) }

$splitReviewResult = $null
$draftDecisionResult = $null
$collectDecisionPartsResult = $null
$validateDecisionResult = $null
$finalizeReviewedResult = $null
$auditConfirmedResult = $null

if ($SplitReviewPack) {
    $splitReviewResult = Invoke-PipelineStep -Name "split-review-pack" -Arguments $splitArgs
}
if ($DraftDecisions) {
    $draftDecisionResult = Invoke-PipelineStep -Name "draft-decisions" -Arguments $draftArgs
}
if ($CollectDecisionParts) {
    $collectDecisionPartsResult = Invoke-PipelineStep -Name "collect-decision-parts" -Arguments $collectArgs
}
if ($ValidateDecisions) {
    $validateDecisionResult = Invoke-PipelineStep -Name "validate-decisions" -Arguments $validateDecisionArgs
}
if ($FinalizeReviewed) {
    $finalizeReviewedResult = Invoke-PipelineStep -Name "finalize-reviewed" -Arguments $finalizeArgs
}
if ($AuditConfirmed) {
    $auditConfirmedResult = Invoke-PipelineStep -Name "audit-confirmed" -Arguments $auditArgs
}

[pscustomobject]@{
    inspect = $inspect.output
    segments = $segment.output
    route = $routeResult.output
    candidates = $candidates.output
    evidence = $evidence.output
    review_pack = if ($legacyReviewPackResult) { $legacyReviewPackResult.output_jsonl } else { $null }
    confirmed = if ($Confirmed) { $Confirmed } else { $null }
    curation_report = if ($mergeReviewedResult) { $mergeReviewedResult.output_report } else { $null }
    report = if ($render) { $render.output } else { $null }
    validation = if ($validation) { $validation.output } else { $null }
    split_review_pack = $splitReviewResult
    draft_decisions = $draftDecisionResult
    collect_decision_parts = $collectDecisionPartsResult
    validate_decisions = $validateDecisionResult
    finalize_reviewed = $finalizeReviewedResult
    audit_confirmed = $auditConfirmedResult
} | ConvertTo-Json -Depth 4
