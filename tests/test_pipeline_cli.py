import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "worldbuilding_pipeline.py"


def _write_json(path, data, encoding="utf-8"):
    path.write_text(
        json.dumps(data, ensure_ascii=False) + "\n",
        encoding=encoding,
    )


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(CLI), *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_cli_lists_phase1_commands():
    result = _run_cli("--help")
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


def test_cli_inspect_writes_report_and_template_columns(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("韩立服下黄龙丹。", encoding="utf-8")
    template = tmp_path / "丹药分析模板.md"
    template.write_text(
        "\n".join(
            [
                "# 丹药分析模板",
                "",
                "| 丹药名称 | 稀有度 | 功效 |",
                "| --- | --- | --- |",
                "| 示例 | 示例 | 示例 |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "inspect",
        "--workdir",
        tmp_path,
        "--source",
        source,
        "--template",
        template,
    )

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "inspect.json").exists()
    report = json.loads((tmp_path / "inspect-report.json").read_text(encoding="utf-8"))
    assert report["template_columns_found"] == ["丹药名称", "稀有度", "功效"]


def test_cli_inspect_and_segment_accept_input_alias(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("第一章\n韩立服下黄龙丹。", encoding="utf-8")
    template = tmp_path / "丹药分析模板.md"
    template.write_text("# 丹药分析模板\n", encoding="utf-8")
    config = ROOT / "assets" / "default-config.yaml"

    inspect_result = _run_cli(
        "inspect",
        "--workdir",
        tmp_path,
        "--input",
        source,
    )

    assert inspect_result.returncode == 0, inspect_result.stderr
    inspect_report = json.loads(
        (tmp_path / "inspect-report.json").read_text(encoding="utf-8")
    )
    assert inspect_report["source"] == str(source)

    segment_result = _run_cli(
        "segment",
        "--config",
        config,
        "--workdir",
        tmp_path,
        "--input",
        source,
        "--template",
        template,
    )

    assert segment_result.returncode == 0, segment_result.stderr
    segments = [
        json.loads(line)
        for line in (tmp_path / "segments.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "韩立服下黄龙丹。" in segments[0]["text"]


def test_cli_route_template_uses_report_default_name(tmp_path):
    template = tmp_path / "丹药分析模板.md"
    template.write_text("# 丹药分析模板\n", encoding="utf-8")

    result = _run_cli(
        "route-template",
        "--workdir",
        tmp_path,
        "--template",
        template,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "route-report.json").exists()
    assert not (tmp_path / "route.json").exists()


def test_cli_route_template_accepts_plan_style_aliases_and_ignored_args(tmp_path):
    template = tmp_path / "丹药分析模板.md"
    template.write_text("# 丹药分析模板\n", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text("unused: true\n", encoding="utf-8")
    source = tmp_path / "source.txt"
    source.write_text("韩立服下黄龙丹。", encoding="utf-8")

    result = _run_cli(
        "route-template",
        "--workdir",
        tmp_path,
        "--template",
        template,
        "--registry",
        ROOT / "assets" / "template-registry.yaml",
        "--request",
        "梳理丹药设定",
        "--config",
        config,
        "--input",
        source,
    )

    assert result.returncode == 0, result.stderr
    route = json.loads((tmp_path / "route-report.json").read_text(encoding="utf-8"))
    assert route["subject_type"] == "丹药"


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
        encoding="utf-8-sig",
    )
    result = _run_cli(
        "extract-candidates",
        "--workdir",
        tmp_path,
        "--mode-rule",
        ROOT / "assets" / "mode-rules" / "entity.yaml",
        "--rule-pack",
        ROOT / "assets" / "rule-packs" / "entity-medicine.yaml",
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


def test_cli_extract_candidates_accepts_plan_style_ignored_args(tmp_path):
    text = "韩立服下黄龙丹。"
    segment = {
        "segment_id": "seg-000001",
        "title": "测试",
        "text": text,
        "start_line": 1,
        "end_line": 1,
        "start_char": 0,
        "end_char": len(text),
    }
    (tmp_path / "segments.jsonl").write_text(
        json.dumps(segment, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "extract-candidates",
        "--workdir",
        tmp_path,
        "--config",
        tmp_path / "config.yaml",
        "--input",
        tmp_path / "source.txt",
        "--template",
        tmp_path / "丹药分析模板.md",
        "--mode-rule",
        ROOT / "assets" / "mode-rules" / "entity.yaml",
        "--rule-pack",
        ROOT / "assets" / "rule-packs" / "entity-medicine.yaml",
    )

    assert result.returncode == 0, result.stderr
    candidates = [
        json.loads(line)
        for line in (tmp_path / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(candidate["name"] == "黄龙丹" for candidate in candidates)


def test_cli_render_accepts_bom_confirmed_and_keeps_expected_only_out(tmp_path):
    route = {
        "subject_type": "丹药",
        "output_name_pattern": "{work_title}-bom.md",
        "report_title_pattern": "《{work_title}》{subject_type}分析",
        "required_columns": ["丹药名称"],
    }
    confirmed = {
        "work_title": "测试书",
        "items": [
            {
                "status": "confirmed",
                "name": "黄龙丹",
                "fields": {"丹药名称": "黄龙丹"},
                "source_spans": [
                    {"segment_id": "seg-000001", "line": 1, "summary": "韩立服下黄龙丹"}
                ],
            }
        ],
    }
    (tmp_path / "expected.yaml").write_text(
        "expected_present: [黄龙丹, 金髓丸]\n",
        encoding="utf-8",
    )
    _write_json(tmp_path / "route-report.json", route)
    confirmed_path = tmp_path / "confirmed.json"
    _write_json(confirmed_path, confirmed, encoding="utf-8-sig")

    result = _run_cli(
        "render",
        "--workdir",
        tmp_path,
        "--confirmed",
        confirmed_path,
    )

    assert result.returncode == 0, result.stderr
    report = (tmp_path / "测试书-bom.md").read_text(encoding="utf-8")
    assert "黄龙丹" in report
    assert "金髓丸" not in report


def test_cli_build_evidence_uses_pack_default_name(tmp_path):
    text = "韩立服下黄龙丹。"
    start = text.index("黄龙丹")
    segment = {
        "segment_id": "seg-000001",
        "title": "测试",
        "text": text,
        "start_line": 1,
        "end_line": 1,
        "start_char": 100,
        "end_char": 100 + len(text),
    }
    candidate = {
        "name": "黄龙丹",
        "status": "needs-review",
        "segment_id": "seg-000001",
        "start": start,
        "end": start + len("黄龙丹"),
        "start_char": 100 + start,
        "end_char": 100 + start + len("黄龙丹"),
    }
    (tmp_path / "segments.jsonl").write_text(
        json.dumps(segment, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "candidates.jsonl").write_text(
        json.dumps(candidate, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = _run_cli("build-evidence", "--workdir", tmp_path)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "evidence-pack.jsonl").exists()
    assert not (tmp_path / "evidence.jsonl").exists()


def test_cli_build_evidence_accepts_plan_style_ignored_args(tmp_path):
    text = "韩立服下黄龙丹。"
    start = text.index("黄龙丹")
    segment = {
        "segment_id": "seg-000001",
        "title": "测试",
        "text": text,
        "start_line": 1,
        "end_line": 1,
        "start_char": 0,
        "end_char": len(text),
    }
    candidate = {
        "name": "黄龙丹",
        "status": "needs-review",
        "segment_id": "seg-000001",
        "start": start,
        "end": start + len("黄龙丹"),
        "start_char": start,
        "end_char": start + len("黄龙丹"),
    }
    (tmp_path / "segments.jsonl").write_text(
        json.dumps(segment, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "candidates.jsonl").write_text(
        json.dumps(candidate, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "build-evidence",
        "--workdir",
        tmp_path,
        "--config",
        tmp_path / "config.yaml",
        "--input",
        tmp_path / "source.txt",
        "--template",
        tmp_path / "丹药分析模板.md",
    )

    assert result.returncode == 0, result.stderr
    evidence = [
        json.loads(line)
        for line in (tmp_path / "evidence-pack.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert evidence[0]["name"] == "黄龙丹"


def test_cli_render_reads_route_report_by_default(tmp_path):
    route = {
        "subject_type": "丹药",
        "output_name_pattern": "{work_title}-from-route.md",
        "report_title_pattern": "《{work_title}》{subject_type}分析",
        "required_columns": ["丹药名称"],
    }
    confirmed = {
        "work_title": "测试书",
        "items": [
            {
                "status": "confirmed",
                "name": "黄龙丹",
                "fields": {"丹药名称": "黄龙丹"},
                "source_spans": [
                    {"segment_id": "seg-000001", "line": 1, "summary": "韩立服下黄龙丹"}
                ],
            }
        ],
    }
    _write_json(tmp_path / "route-report.json", route)
    confirmed_path = tmp_path / "confirmed.json"
    _write_json(confirmed_path, confirmed)

    result = _run_cli(
        "render",
        "--workdir",
        tmp_path,
        "--confirmed",
        confirmed_path,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "测试书-from-route.md").exists()
    assert not (tmp_path / "测试书丹药分析.md").exists()


def test_cli_render_accepts_config_alias_and_plan_style_ignored_args(tmp_path):
    confirmed = {
        "work_title": "测试书",
        "items": [
            {
                "status": "confirmed",
                "name": "黄龙丹",
                "fields": {"丹药名称": "黄龙丹"},
                "source_spans": [
                    {"segment_id": "seg-000001", "line": 1, "summary": "韩立服下黄龙丹"}
                ],
            }
        ],
    }
    config = tmp_path / "default.yaml"
    config.write_text(
        "\n".join(
            [
                "output:",
                "  output_name_pattern: \"{work_title}-from-config.md\"",
                "  report_title_pattern: \"《{work_title}》分析\"",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    confirmed_path = tmp_path / "confirmed.json"
    _write_json(confirmed_path, confirmed)

    result = _run_cli(
        "render",
        "--workdir",
        tmp_path,
        "--confirmed",
        confirmed_path,
        "--config",
        config,
        "--template",
        tmp_path / "丹药分析模板.md",
        "--registry",
        ROOT / "assets" / "template-registry.yaml",
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "测试书-from-config.md").exists()
    assert not (tmp_path / "测试书分析.md").exists()


def test_cli_validate_uses_report_default_name(tmp_path):
    report = tmp_path / "report.md"
    report.write_text(
        "\n".join(
            [
                "# 测试报告",
                "",
                "| 丹药名称 |",
                "| --- |",
                "| 黄龙丹 |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_cli("validate", "--workdir", tmp_path, "--report", report)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "validation-report.json").exists()
    assert not (tmp_path / "validation.json").exists()


def test_cli_validate_accepts_config_alias_for_default_config(tmp_path):
    confirmed = {
        "work_title": "测试书",
        "items": [
            {
                "status": "confirmed",
                "name": "黄龙丹",
                "fields": {"丹药名称": "黄龙丹"},
                "source_spans": [
                    {"segment_id": "seg-000001", "line": 1, "summary": "韩立服下黄龙丹"}
                ],
            }
        ],
    }
    config = tmp_path / "default.yaml"
    config.write_text(
        "\n".join(
            [
                "output:",
                "  output_name_pattern: \"{work_title}-validate-config.md\"",
                "required_columns: [丹药名称]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    confirmed_path = tmp_path / "confirmed.json"
    _write_json(confirmed_path, confirmed)
    report = tmp_path / "测试书-validate-config.md"
    report.write_text(
        "\n".join(
            [
                "# 测试报告",
                "",
                "| 丹药名称 |",
                "| --- |",
                "| 黄龙丹 |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "validate",
        "--workdir",
        tmp_path,
        "--confirmed",
        confirmed_path,
        "--config",
        config,
    )

    assert result.returncode == 0, result.stderr
    validation = json.loads(
        (tmp_path / "validation-report.json").read_text(encoding="utf-8")
    )
    assert validation["passed"] is True


def test_cli_validate_expected_present_warning_does_not_block(tmp_path):
    confirmed = {
        "work_title": "测试书",
        "items": [
            {
                "status": "confirmed",
                "name": "黄龙丹",
                "fields": {"丹药名称": "黄龙丹"},
                "source_spans": [
                    {"segment_id": "seg-000001", "line": 1, "summary": "韩立服下黄龙丹"}
                ],
            }
        ],
    }
    report = tmp_path / "report.md"
    report.write_text(
        "\n".join(
            [
                "# 测试报告",
                "",
                "| 丹药名称 |",
                "| --- |",
                "| 黄龙丹 |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    expected = tmp_path / "expected.yaml"
    expected.write_text(
        "\n".join(
            [
                "required_columns: [丹药名称]",
                "expected_present: [黄龙丹, 金髓丸]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    confirmed_path = tmp_path / "confirmed.json"
    _write_json(confirmed_path, confirmed, encoding="utf-8-sig")

    result = _run_cli(
        "validate",
        "--workdir",
        tmp_path,
        "--report",
        report,
        "--expected",
        expected,
        "--confirmed",
        confirmed_path,
    )

    assert result.returncode == 0, result.stderr
    validation = json.loads(
        (tmp_path / "validation-report.json").read_text(encoding="utf-8")
    )
    assert validation["passed"] is True
    assert validation["blocking_errors"] == []
    assert validation["coverage_warnings"]["expected_present_missing"] == ["金髓丸"]
