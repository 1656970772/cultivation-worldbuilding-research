import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_extraction.ps1"


def test_run_extraction_wrapper_dry_run_accepts_chinese_paths(tmp_path: Path):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is required")
    source = tmp_path / "凡人修仙传.txt"
    source.write_text("韩立服下聚气丹。", encoding="utf-8")
    template = tmp_path / "丹药分析模板.md"
    template.write_text("# 丹药分析模板\n", encoding="utf-8")
    output_dir = tmp_path / "输出"
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "encoding:",
                "  fallbacks: [utf-8]",
                "extraction:",
                "  model_id: MiniMax-M2.7",
                "  max_char_buffer: 1000",
                "  dry_run: false",
                "  run_summary_name: custom-summary.json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    command = [powershell, "-NoProfile"]
    if Path(powershell).name.lower() == "powershell.exe":
        command += ["-ExecutionPolicy", "Bypass"]
    result = subprocess.run(
        [
            *command,
            "-File",
            str(RUNNER),
            "-Template",
            str(template),
            "-SourceFile",
            str(source),
            "-OutputDir",
            str(output_dir),
            "-Config",
            str(config),
            "-DryRun",
            "-LimitChars",
            "8",
            "-MaxCharBuffer",
            "4",
        ],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads((output_dir / "custom-summary.json").read_text(encoding="utf-8"))
    assert summary["dry_run"] is True
    assert summary["source"]["limit_chars"] == 8
