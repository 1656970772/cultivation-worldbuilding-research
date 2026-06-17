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
