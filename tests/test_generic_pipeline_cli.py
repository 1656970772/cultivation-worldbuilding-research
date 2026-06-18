import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "worldbuilding_pipeline.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(CLI), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def test_profile_template_cli_outputs_profile(tmp_path: Path):
    template = tmp_path / "关系链模板.md"
    template.write_text("# 关系链模板\n```markdown\n- 节点：\n- 关系边：\n```", encoding="utf-8")

    result = run_cli("profile-template", "--template", str(template))

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["report_shape"] == "relationship_chain"


def test_prepare_framework_cli_writes_reused_files(tmp_path: Path):
    template = tmp_path / "炼丹师模板.md"
    template.write_text("# 炼丹师模板\n```markdown\n## 炼丹师卡片：{名称}\n- 境界：\n- 丹方：\n```", encoding="utf-8")
    framework = tmp_path / "framework"

    result = run_cli(
        "prepare-framework",
        "--template",
        str(template),
        "--framework-dir",
        str(framework),
        "--work-title",
        "测试书",
        "--request",
        "分析炼丹师职业闭环",
    )

    assert result.returncode == 0
    assert (framework / "route.json").exists()
    assert (framework / "rule-pack.yaml").exists()
    assert (framework / "curation.yaml").exists()
    assert (framework / "framework-summary.json").exists()


def test_batch_plan_cli_writes_plan(tmp_path: Path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    source_dir = tmp_path / "凡人修仙传"
    source_dir.mkdir()
    source_file = source_dir / "凡人修仙传.txt"
    source_file.write_text("韩立服下黄龙丹。", encoding="utf-8")
    (template_dir / "README.md").write_text("# 元规则\n", encoding="utf-8")
    (template_dir / "丹药分析模板.md").write_text(
        "# 丹药分析模板\n\n## 推荐结构\n\n| 丹药名称 | 功效 | 证据 |\n| --- | --- | --- |\n",
        encoding="utf-8",
    )
    output = source_dir / "batch-plan.json"
    framework_root = source_dir / "frameworks"

    result = run_cli(
        "batch-plan",
        "--template-dir",
        str(template_dir),
        "--source-dir",
        str(source_dir),
        "--source-file",
        str(source_file),
        "--mode",
        "merge",
        "--output",
        str(output),
        "--framework-root",
        str(framework_root),
        "--prompt-contract",
        str(ROOT / "assets" / "batch-prompt-contract.yaml"),
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["output"] == str(output)
    assert stdout["items"] == 1
    plan = json.loads(output.read_text(encoding="utf-8"))
    assert plan["mode"] == "merge"
    assert plan["framework_root"] == str(framework_root)
    assert plan["items"][0]["template_name"] == "丹药分析模板.md"
    assert Path(plan["items"][0]["framework_dir"]).is_relative_to(framework_root)
    assert plan["prompt_contract"].endswith("batch-prompt-contract.yaml")


def test_batch_plan_cli_uses_default_output(tmp_path: Path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    source_dir = tmp_path / "凡人修仙传"
    source_dir.mkdir()
    source_file = source_dir / "凡人修仙传.txt"
    source_file.write_text("韩立服下黄龙丹。", encoding="utf-8")
    (template_dir / "README.md").write_text("# 元规则\n", encoding="utf-8")
    (template_dir / "丹药分析模板.md").write_text(
        "# 丹药分析模板\n\n## 推荐结构\n\n| 丹药名称 | 功效 | 证据 |\n| --- | --- | --- |\n",
        encoding="utf-8",
    )
    output = source_dir / "batch-plan.json"

    result = run_cli(
        "batch-plan",
        "--template-dir",
        str(template_dir),
        "--source-dir",
        str(source_dir),
        "--source-file",
        str(source_file),
        "--prompt-contract",
        str(ROOT / "assets" / "batch-prompt-contract.yaml"),
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout["output"] == str(output)
    assert output.exists()
