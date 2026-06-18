import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "run_worldbuilding_pipeline.ps1"
BATCH_WRAPPER = ROOT / "scripts" / "run_batch.ps1"


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


def test_batch_wrapper_exposes_required_parameters():
    text = BATCH_WRAPPER.read_text(encoding="utf-8")

    assert "[Parameter(Mandatory = $true)]\n    [string]$TemplateDir" in text
    assert "[Parameter(Mandatory = $true)]\n    [string]$SourceDir" in text
    assert "[Parameter(Mandatory = $true)]\n    [string]$SourceFile" in text
    assert "[string]$TemplateDir" in text
    assert "[string]$SourceDir" in text
    assert "[string]$SourceFile" in text
    assert "[ValidateSet(\"overwrite\", \"merge\")]" in text
    assert "[string]$Mode = \"overwrite\"" in text
    assert "[string]$FrameworkRoot" in text
    assert "[string]$PromptContract" in text
    assert "[string]$PythonExe = \"python\"" in text
    assert "[string]$Output" in text


def test_batch_wrapper_calls_batch_plan_cli_only():
    text = BATCH_WRAPPER.read_text(encoding="utf-8")

    assert '"batch-plan"' in text
    assert "--template-dir" in text
    assert "--source-dir" in text
    assert "--source-file" in text
    assert "--framework-root" in text
    assert "--prompt-contract" in text
    assert "extract-candidates" not in text
    assert "make-review-pack" not in text
    assert "render" not in text


def test_batch_wrapper_runs_with_chinese_and_space_paths(tmp_path):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is required to exercise run_batch.ps1")
    template_dir = tmp_path / "模板 目录"
    source_dir = tmp_path / "凡人 修仙传"
    template_dir.mkdir()
    source_dir.mkdir()
    source_file = source_dir / "凡人修仙传.txt"
    source_file.write_text("韩立服下黄龙丹。", encoding="utf-8")
    (template_dir / "README.md").write_text("# 元规则\n", encoding="utf-8")
    (template_dir / "丹药分析模板.md").write_text(
        "# 丹药分析模板\n\n## 推荐结构\n\n| 丹药名称 | 功效 | 证据 |\n| --- | --- | --- |\n",
        encoding="utf-8",
    )

    command = [powershell, "-NoProfile"]
    if Path(powershell).name.lower() == "powershell.exe":
        command += ["-ExecutionPolicy", "Bypass"]
    result = subprocess.run(
        [
            *command,
            "-File",
            str(BATCH_WRAPPER),
            "-TemplateDir",
            str(template_dir),
            "-SourceDir",
            str(source_dir),
            "-SourceFile",
            str(source_file),
            "-PythonExe",
            sys.executable,
        ],
        cwd=tmp_path,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout.splitlines()[-1])
    output = source_dir / "batch-plan.json"
    assert stdout["output"] == str(output)
    plan = json.loads(output.read_text(encoding="utf-8"))
    assert plan["template_count"] == 1
    assert Path(plan["items"][0]["output_path"]).name == "丹药分析.md"
