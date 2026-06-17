from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "run_worldbuilding_pipeline.ps1"


def test_wrapper_exposes_framework_parameters():
    text = WRAPPER.read_text(encoding="utf-8")

    assert "[switch]$PrepareFramework" in text
    assert "[switch]$SuggestAnalysisPoints" in text
    assert "[string]$FrameworkDir" in text


def test_wrapper_repoints_generated_framework_files_before_extraction():
    text = WRAPPER.read_text(encoding="utf-8")

    assert "$generatedRoute = Join-Path $FrameworkDir \"route.json\"" in text
    assert "$generatedRulePack = Join-Path $FrameworkDir \"rule-pack.yaml\"" in text
    assert "$generatedCuration = Join-Path $FrameworkDir \"curation.yaml\"" in text
    assert "$Route = $generatedRoute" in text
    assert "$RulePack = $generatedRulePack" in text
    assert "$Curation = $generatedCuration" in text


def test_wrapper_skips_registry_route_when_local_route_exists():
    text = WRAPPER.read_text(encoding="utf-8")

    assert "route-template skipped: using local route" in text
    assert "Test-Path -LiteralPath $Route" in text
