import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "worldbuilding_pipeline.py"


def test_cli_lists_phase1_commands():
    result = subprocess.run(
        [sys.executable, str(CLI), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    for command in [
        "inspect",
        "segment",
        "route-template",
        "extract-candidates",
        "build-evidence",
        "render",
        "validate",
    ]:
        assert command in result.stdout


def test_cli_extract_candidates_writes_segment_and_global_offsets(tmp_path):
    text = "韩立服下黄龙丹和金髓丸。"
    segment = {
        "segment_id": "seg-000123",
        "title": "测试",
        "text": text,
        "start_line": 20,
        "end_line": 20,
        "start_char": 1000,
        "end_char": 1000 + len(text),
    }
    (tmp_path / "segments.jsonl").write_text(
        json.dumps(segment, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "extract-candidates",
            "--workdir",
            str(tmp_path),
            "--mode-rule",
            str(ROOT / "assets" / "mode-rules" / "entity.yaml"),
            "--rule-pack",
            str(ROOT / "assets" / "rule-packs" / "entity-medicine.yaml"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    candidates = [
        json.loads(line)
        for line in (tmp_path / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    item = next(candidate for candidate in candidates if candidate["name"] == "黄龙丹")
    assert item["segment_id"] == "seg-000123"
    assert item["start"] == text.index("黄龙丹")
    assert item["end"] == item["start"] + len("黄龙丹")
    assert item["start_char"] == 1000 + item["start"]
    assert item["end_char"] == 1000 + item["end"]
