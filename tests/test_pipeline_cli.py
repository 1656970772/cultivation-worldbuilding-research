import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "worldbuilding_pipeline.py"
RUNNER = ROOT / "scripts" / "run_worldbuilding_pipeline.ps1"


def _write_json(path, data, encoding="utf-8"):
    path.write_text(
        json.dumps(data, ensure_ascii=False) + "\n",
        encoding=encoding,
    )


def _write_jsonl(path, items, encoding="utf-8"):
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items),
        encoding=encoding,
    )


def _collect_shard(name, expected_output, review_ids):
    return {
        "shard": name,
        "input": f"{name}.jsonl",
        "expected_output": expected_output,
        "count": len(review_ids),
        "first_review_id": review_ids[0],
        "last_review_id": review_ids[-1],
        "review_ids": review_ids,
        "input_sha256": "unused",
    }


def _write_collect_manifest(parts_dir, shards):
    manifest_path = parts_dir / "review-shard-manifest.json"
    _write_json(
        manifest_path,
        {
            "schema_version": 1,
            "review_pack": str(parts_dir.parent / "review-pack.jsonl"),
            "review_pack_sha256": "unused",
            "entries_per_shard": 2,
            "total_entries": sum(len(shard["review_ids"]) for shard in shards),
            "shards": shards,
        },
    )
    return manifest_path


def _confirmed_item(name, *, fields=None, aliases=None, source_spans=None):
    return {
        "status": "confirmed",
        "name": name,
        "aliases": aliases or [],
        "fields": fields or {"Name": name, "Effect": "known"},
        "source_spans": source_spans
        if source_spans is not None
        else [
            {
                "segment_id": "seg-001",
                "start_char": 0,
                "end_char": len(name),
                "line": 1,
                "summary": "evidence",
            }
        ],
    }


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(CLI), *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _run_wrapper(*args):
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is required to exercise the runtime wrapper")
    command = [powershell, "-NoProfile"]
    if Path(powershell).name.lower() == "powershell.exe":
        command += ["-ExecutionPolicy", "Bypass"]
    return subprocess.run(
        [*command, "-File", str(RUNNER), *map(str, args)],
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
        "draft-decisions",
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


def test_cli_make_review_pack_writes_jsonl_and_markdown_defaults(tmp_path):
    _write_jsonl(
        tmp_path / "candidates.jsonl",
        [
            {
                "name": "黄龙丹",
                "status": "needs-review",
                "segment_id": "seg-000001",
                "start_char": 10,
                "end_char": 13,
            }
        ],
    )
    _write_jsonl(
        tmp_path / "evidence-pack.jsonl",
        [
            {
                "name": "黄龙丹",
                "segment_id": "seg-000001",
                "line": 6,
                "summary": "韩立服下黄龙丹。",
                "source_span": {"start_char": 10, "end_char": 13},
            }
        ],
    )

    result = _run_cli(
        "make-review-pack",
        "--workdir",
        tmp_path,
        "--curation",
        ROOT / "assets" / "curation" / "entity-medicine.yaml",
    )

    assert result.returncode == 0, result.stderr
    stdout = json.loads(result.stdout)
    assert stdout == {
        "output_jsonl": str(tmp_path / "review-pack.jsonl"),
        "output_md": str(tmp_path / "review-pack.md"),
        "entries": 1,
    }

    [entry] = [
        json.loads(line)
        for line in (tmp_path / "review-pack.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert entry["review_id"] == "medicine-000001"
    assert entry["name"] == "黄龙丹"
    assert entry["source_spans"] == [
        {
            "segment_id": "seg-000001",
            "start_char": 10,
            "end_char": 13,
            "line": 6,
            "summary": "韩立服下黄龙丹。",
        }
    ]
    assert entry["fields"]["丹药名称"] == "黄龙丹"
    assert "功效" in entry["fields"]

    markdown = (tmp_path / "review-pack.md").read_text(encoding="utf-8")
    assert "medicine-000001" in markdown
    assert "黄龙丹" in markdown
    assert "seg-000001:10-13" in markdown
    assert "韩立服下黄龙丹。" in markdown
    assert "### Fields" in markdown
    assert "- 丹药名称: 黄龙丹" in markdown
    assert "- 功效: 原文未说明" in markdown


def test_cli_split_review_pack_writes_manifest_default(tmp_path):
    _write_jsonl(
        tmp_path / "review-pack.jsonl",
        [
            {"review_id": "review-001", "name": "A"},
            {"review_id": "review-002", "name": "B"},
            {"review_id": "review-003", "name": "C"},
        ],
    )

    result = _run_cli(
        "split-review-pack",
        "--workdir",
        tmp_path,
        "--entries-per-shard",
        "2",
    )

    assert result.returncode == 0, result.stderr
    manifest_path = tmp_path / "review-decisions.parts" / "review-shard-manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["entries_per_shard"] == 2
    assert manifest["total_entries"] == 3
    assert [shard["count"] for shard in manifest["shards"]] == [2, 1]

    stdout = json.loads(result.stdout)
    assert stdout == {
        "manifest": str(manifest_path),
        "parts_dir": str(tmp_path / "review-decisions.parts"),
        "shards": 2,
        "total_entries": 3,
    }


def test_cli_collect_decision_parts_writes_defaults_and_returns_zero(tmp_path):
    parts_dir = tmp_path / "review-decisions.parts"
    parts_dir.mkdir()
    _write_collect_manifest(
        parts_dir,
        [
            _collect_shard(
                "review-shard-000001",
                "review-decisions.part-000001.jsonl",
                ["review-001", "review-002"],
            )
        ],
    )
    _write_jsonl(
        parts_dir / "review-decisions.part-000001.jsonl",
        [
            {"review_id": "review-001", "decision": "confirmed"},
            {"review_id": "review-002", "decision": "rejected"},
        ],
    )

    result = _run_cli("collect-decision-parts", "--workdir", tmp_path)

    assert result.returncode == 0, result.stderr
    output_path = tmp_path / "review-decisions.jsonl"
    report_path = tmp_path / "decision-collection-report.json"
    assert output_path.exists()
    assert report_path.exists()
    stdout = json.loads(result.stdout)
    assert stdout["output"] == str(output_path)
    assert stdout["report"] == str(report_path)
    assert stdout["passed"] is True
    assert stdout["counts"]["collected_records"] == 2


def test_cli_collect_decision_parts_bad_shard_returns_one_with_context(tmp_path):
    parts_dir = tmp_path / "review-decisions.parts"
    parts_dir.mkdir()
    _write_collect_manifest(
        parts_dir,
        [
            _collect_shard(
                "review-shard-000001",
                "review-decisions.part-000001.jsonl",
                ["review-001"],
            )
        ],
    )
    part_path = parts_dir / "review-decisions.part-000001.jsonl"
    _write_jsonl(part_path, [{"review_id": "review-999", "decision": "confirmed"}])

    result = _run_cli("collect-decision-parts", "--workdir", tmp_path)

    assert result.returncode == 1, result.stderr
    assert not (tmp_path / "review-decisions.jsonl").exists()
    report = json.loads(
        (tmp_path / "decision-collection-report.json").read_text(encoding="utf-8")
    )
    error = next(
        item
        for item in report["blocking_errors"]
        if item["type"] == "review_id_outside_shard"
    )
    assert error["shard"] == "review-shard-000001"
    assert error["path"] == str(part_path)
    assert error["line"] == 1
    assert error["review_id"] == "review-999"


def test_cli_collect_decision_parts_honors_curation_allowed_decisions(tmp_path):
    parts_dir = tmp_path / "review-decisions.parts"
    parts_dir.mkdir()
    _write_collect_manifest(
        parts_dir,
        [
            _collect_shard(
                "review-shard-000001",
                "review-decisions.part-000001.jsonl",
                ["review-001"],
            )
        ],
    )
    _write_jsonl(
        parts_dir / "review-decisions.part-000001.jsonl",
        [{"review_id": "review-001", "decision": "accepted"}],
    )
    curation = tmp_path / "curation.yaml"
    curation.write_text(
        "decision_validation:\n  allowed_decisions: [accepted, rejected]\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "collect-decision-parts",
        "--workdir",
        tmp_path,
        "--curation",
        curation,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(
        (tmp_path / "decision-collection-report.json").read_text(encoding="utf-8")
    )
    assert report["passed"] is True
    assert report["counts"]["accepted"] == 1


def test_cli_collect_decision_parts_uses_curation_part_dir_by_default(tmp_path):
    parts_dir = tmp_path / "custom-parts"
    parts_dir.mkdir()
    manifest_path = _write_collect_manifest(
        parts_dir,
        [
            _collect_shard(
                "review-shard-000001",
                "review-decisions.part-000001.jsonl",
                ["review-001"],
            )
        ],
    )
    _write_jsonl(
        parts_dir / "review-decisions.part-000001.jsonl",
        [{"review_id": "review-001", "decision": "accepted"}],
    )
    curation = tmp_path / "curation.yaml"
    curation.write_text(
        "\n".join(
            [
                "review_workflow:",
                "  part_dir: custom-parts",
                "decision_validation:",
                "  allowed_decisions: [accepted, rejected]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "collect-decision-parts",
        "--workdir",
        tmp_path,
        "--curation",
        curation,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(
        (tmp_path / "decision-collection-report.json").read_text(encoding="utf-8")
    )
    assert report["passed"] is True
    assert report["manifest"] == str(manifest_path)
    assert report["counts"]["accepted"] == 1


def test_cli_collect_decision_parts_uses_parts_dir_manifest_by_default(tmp_path):
    parts_dir = tmp_path / "review-output-parts"
    parts_dir.mkdir()
    manifest_path = _write_collect_manifest(
        parts_dir,
        [
            _collect_shard(
                "review-shard-000001",
                "review-decisions.part-000001.jsonl",
                ["review-001"],
            )
        ],
    )
    _write_jsonl(
        parts_dir / "review-decisions.part-000001.jsonl",
        [{"review_id": "review-001", "decision": "confirmed"}],
    )

    result = _run_cli(
        "collect-decision-parts",
        "--workdir",
        tmp_path,
        "--parts-dir",
        parts_dir,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(
        (tmp_path / "decision-collection-report.json").read_text(encoding="utf-8")
    )
    assert report["passed"] is True
    assert report["manifest"] == str(manifest_path)
    assert report["counts"]["confirmed"] == 1


def test_cli_draft_decisions_writes_default_draft_for_review_pack(tmp_path):
    review_entries = [
        {
            "review_id": "review-001",
            "name": "甲",
            "status_suggestion": "rejected",
            "aliases": [],
            "fields": {"名称": "甲"},
        },
        {
            "review_id": "review-002",
            "name": "乙",
            "status_suggestion": "needs-review",
            "aliases": [],
            "fields": {"名称": "乙"},
        },
    ]
    _write_jsonl(tmp_path / "review-pack.jsonl", review_entries)

    result = _run_cli("draft-decisions", "--workdir", tmp_path)

    assert result.returncode == 0, result.stderr
    draft_path = tmp_path / "review-decisions.draft.jsonl"
    assert draft_path.exists()
    drafts = [
        json.loads(line)
        for line in draft_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(drafts) == len(review_entries)


def test_cli_merge_reviewed_writes_confirmed_outputs_and_summary(tmp_path):
    _write_jsonl(
        tmp_path / "review-pack.jsonl",
        [
            {
                "review_id": "medicine-000001",
                "name": "黄龙丹",
                "aliases": [],
                "fields": {
                    "丹药名称": "黄龙丹",
                    "稀有度": "原文未说明",
                    "功效": "原文未说明",
                },
                "source_spans": [
                    {
                        "segment_id": "seg-000001",
                        "start_char": 10,
                        "end_char": 13,
                        "line": 6,
                        "summary": "韩立服下黄龙丹。",
                    }
                ],
            }
        ],
    )
    _write_jsonl(
        tmp_path / "review-decisions.jsonl",
        [
            {
                "review_id": "medicine-000001",
                "decision": "confirmed",
                "name": "黄龙丹",
                "fields": {
                    "丹药名称": "黄龙丹",
                    "功效": "辅助修炼",
                },
                "notes": "证据足够",
            }
        ],
    )

    result = _run_cli(
        "merge-reviewed",
        "--workdir",
        tmp_path,
        "--review-pack",
        tmp_path / "review-pack.jsonl",
        "--decisions",
        tmp_path / "review-decisions.jsonl",
        "--curation",
        ROOT / "assets" / "curation" / "entity-medicine.yaml",
    )

    assert result.returncode == 0, result.stderr
    confirmed_path = tmp_path / "confirmed-items.json"
    report_path = tmp_path / "curation-report.json"
    assert confirmed_path.exists()
    assert report_path.exists()

    stdout = json.loads(result.stdout)
    assert stdout["output_confirmed"] == str(confirmed_path)
    assert stdout["output_report"] == str(report_path)
    assert stdout["confirmed"] == 1
    assert stdout["report"]["counts"]["confirmed"] == 1
    assert stdout["report"]["counts"]["blocking_errors"] == 0

    confirmed = json.loads(confirmed_path.read_text(encoding="utf-8"))
    assert confirmed["items"][0]["name"] == "黄龙丹"
    assert confirmed["items"][0]["fields"]["功效"] == "辅助修炼"


def test_cli_validate_decisions_bad_fixture_writes_report_with_line_context(tmp_path):
    _write_jsonl(
        tmp_path / "review-pack.jsonl",
        [
            {
                "review_id": "review-001",
                "name": "甲",
                "fields": {"名称": "甲"},
                "source_spans": [{"segment_id": "seg-001", "line": 1, "summary": "甲"}],
            },
            {
                "review_id": "review-002",
                "name": "乙",
                "fields": {"名称": "乙"},
                "source_spans": [{"segment_id": "seg-002", "line": 2, "summary": "乙"}],
            },
        ],
    )
    _write_jsonl(
        tmp_path / "review-decisions.bad.jsonl",
        [
            {"review_id": "review-001", "decision": "confirmed", "name": "甲"},
            {"review_id": "review-002", "decision": "maybe", "name": "乙"},
        ],
    )
    curation = tmp_path / "curation.yaml"
    curation.write_text(
        "\n".join(
            [
                "fields:",
                "  required: [名称]",
                "decision_validation:",
                "  allowed_decisions: [confirmed, rejected, needs-review]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "validate-decisions",
        "--workdir",
        tmp_path,
        "--decisions",
        tmp_path / "review-decisions.bad.jsonl",
        "--curation",
        curation,
    )

    assert result.returncode == 1, result.stderr
    report_path = tmp_path / "decision-validation-report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    error = next(
        item for item in report["blocking_errors"] if item["type"] == "invalid_decision"
    )
    assert error["line"] == 2
    assert error["review_id"] == "review-002"


def test_wrapper_make_review_pack_and_merge_reviewed_sets_confirmed(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("韩立服下黄龙丹。", encoding="utf-8")
    template = tmp_path / "丹药分析模板.md"
    template.write_text("# 丹药分析模板\n", encoding="utf-8")
    decisions = tmp_path / "review-decisions.jsonl"
    _write_jsonl(
        decisions,
        [
            {
                "review_id": "medicine-000001",
                "decision": "confirmed",
                "name": "黄龙丹",
                "fields": {
                    "丹药名称": "黄龙丹",
                    "功效": "辅助修炼",
                },
            }
        ],
    )

    result = _run_wrapper(
        "-Source",
        source,
        "-Template",
        template,
        "-Workdir",
        tmp_path,
        "-Curation",
        ROOT / "assets" / "curation" / "entity-medicine.yaml",
        "-MakeReviewPack",
        "-Decisions",
        decisions,
        "-MergeReviewed",
        "-SkipRender",
        "-SkipValidate",
    )

    assert result.returncode == 0, result.stderr
    confirmed_path = tmp_path / "confirmed-items.json"
    assert (tmp_path / "review-pack.jsonl").exists()
    assert confirmed_path.exists()
    assert (tmp_path / "curation-report.json").exists()
    assert confirmed_path.name in result.stdout

    confirmed = json.loads(confirmed_path.read_text(encoding="utf-8"))
    assert confirmed["items"][0]["name"] == "黄龙丹"


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


def test_cli_audit_confirmed_writes_default_output_success(tmp_path):
    _write_json(
        tmp_path / "confirmed-items.json",
        {"items": [_confirmed_item("Alpha")]},
    )

    result = _run_cli("audit-confirmed", "--workdir", tmp_path)

    assert result.returncode == 0, result.stderr
    report_path = tmp_path / "confirmed-audit-report.json"
    assert report_path.exists()
    stdout = json.loads(result.stdout)
    assert stdout["output"] == str(report_path)
    assert stdout["passed"] is True
    assert stdout["counts"]["items"] == 1


def test_cli_audit_confirmed_blocking_returns_one_and_writes_report(tmp_path):
    _write_json(
        tmp_path / "confirmed-items.json",
        {
            "items": [
                _confirmed_item("Alpha", source_spans=[]),
                _confirmed_item("Alpha"),
            ]
        },
    )

    result = _run_cli("audit-confirmed", "--workdir", tmp_path)

    assert result.returncode == 1, result.stderr
    report = json.loads(
        (tmp_path / "confirmed-audit-report.json").read_text(encoding="utf-8")
    )
    assert report["passed"] is False
    assert {error["type"] for error in report["blocking_errors"]} >= {
        "duplicate_name",
        "missing_source_spans",
    }


def test_cli_audit_confirmed_curation_required_fields_take_precedence(tmp_path):
    _write_json(
        tmp_path / "confirmed-items.json",
        {
            "report_config": {"required_columns": ["Name", "Effect"]},
            "items": [_confirmed_item("Alpha", fields={"Name": "Alpha"})],
        },
    )
    curation = tmp_path / "curation.yaml"
    curation.write_text(
        "\n".join(
            [
                "fields:",
                "  required: [Name]",
                "confirmed_audit:",
                "  require_source_spans: true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "audit-confirmed",
        "--workdir",
        tmp_path,
        "--curation",
        curation,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(
        (tmp_path / "confirmed-audit-report.json").read_text(encoding="utf-8")
    )
    assert report["passed"] is True
    assert all(
        error["type"] != "missing_required_field"
        for error in report["blocking_errors"]
    )


def test_cli_audit_confirmed_uses_confirmed_report_config_required_columns_fallback(tmp_path):
    _write_json(
        tmp_path / "confirmed-items.json",
        {
            "report_config": {"required_columns": ["Name", "Effect"]},
            "items": [_confirmed_item("Alpha", fields={"Name": "Alpha"})],
        },
    )

    result = _run_cli("audit-confirmed", "--workdir", tmp_path)

    assert result.returncode == 1, result.stderr
    report = json.loads(
        (tmp_path / "confirmed-audit-report.json").read_text(encoding="utf-8")
    )
    missing = next(
        error
        for error in report["blocking_errors"]
        if error["type"] == "missing_required_field"
    )
    assert missing["field"] == "Effect"


def test_cli_audit_confirmed_curation_without_required_fields_falls_back_to_confirmed_report_config(tmp_path):
    _write_json(
        tmp_path / "confirmed-items.json",
        {
            "report_config": {"required_columns": ["Name", "Effect"]},
            "items": [_confirmed_item("Alpha", fields={"Name": "Alpha"})],
        },
    )
    curation = tmp_path / "curation.yaml"
    curation.write_text(
        "\n".join(
            [
                "confirmed_audit:",
                "  require_source_spans: true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "audit-confirmed",
        "--workdir",
        tmp_path,
        "--curation",
        curation,
    )

    assert result.returncode == 1, result.stderr
    report = json.loads(
        (tmp_path / "confirmed-audit-report.json").read_text(encoding="utf-8")
    )
    missing = next(
        error
        for error in report["blocking_errors"]
        if error["type"] == "missing_required_field"
    )
    assert missing["field"] == "Effect"


def test_cli_audit_confirmed_empty_curation_required_fields_fall_back_to_confirmed_report_config(tmp_path):
    _write_json(
        tmp_path / "confirmed-items.json",
        {
            "report_config": {"required_columns": ["Name", "Effect"]},
            "items": [_confirmed_item("Alpha", fields={"Name": "Alpha"})],
        },
    )
    curation = tmp_path / "curation.yaml"
    curation.write_text(
        "\n".join(
            [
                "fields:",
                "  required: []",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "audit-confirmed",
        "--workdir",
        tmp_path,
        "--curation",
        curation,
    )

    assert result.returncode == 1, result.stderr
    report = json.loads(
        (tmp_path / "confirmed-audit-report.json").read_text(encoding="utf-8")
    )
    missing = next(
        error
        for error in report["blocking_errors"]
        if error["type"] == "missing_required_field"
    )
    assert missing["field"] == "Effect"


def test_cli_audit_confirmed_rejects_non_mapping_confirmed_audit_config(tmp_path):
    _write_json(
        tmp_path / "confirmed-items.json",
        {"items": [_confirmed_item("Alpha")]},
    )
    curation = tmp_path / "curation.yaml"
    curation.write_text("confirmed_audit: []\n", encoding="utf-8")

    result = _run_cli(
        "audit-confirmed",
        "--workdir",
        tmp_path,
        "--curation",
        curation,
    )

    assert result.returncode != 0
    assert "confirmed_audit must be a mapping" in (result.stderr + result.stdout)


def test_cli_audit_confirmed_markdown_report_row_count_cross_check(tmp_path):
    _write_json(
        tmp_path / "confirmed-items.json",
        {
            "report_config": {"required_columns": ["Name", "Effect"]},
            "items": [
                _confirmed_item("Alpha"),
                _confirmed_item("Beta"),
            ],
        },
    )
    report = tmp_path / "report.md"
    report.write_text(
        "\n".join(
            [
                "| Name | Effect |",
                "| --- | --- |",
                "| Alpha | known |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = _run_cli(
        "audit-confirmed",
        "--workdir",
        tmp_path,
        "--report",
        report,
    )

    assert result.returncode == 1, result.stderr
    audit = json.loads(
        (tmp_path / "confirmed-audit-report.json").read_text(encoding="utf-8")
    )
    mismatch = next(
        error
        for error in audit["blocking_errors"]
        if error["type"] == "markdown_row_count_mismatch"
    )
    assert mismatch["confirmed_items"] == 2
    assert mismatch["markdown_rows"] == 1
