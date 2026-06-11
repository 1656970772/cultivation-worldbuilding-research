import json
from pathlib import Path

import pytest

from scripts.pipeline.evidence_builder import build_evidence_pack
from scripts.pipeline.renderer import render_report
from scripts.pipeline.validator import validate_expected_present, validate_report


ROOT = Path(__file__).resolve().parents[1]


def _minimal_confirmed_fixture():
    path = ROOT / "tests" / "fixtures" / "confirmed-items" / "fanren-medicine-minimal.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_build_evidence_uses_candidate_offsets_not_first_name():
    text = "黄龙丹只是传闻。真正服下黄龙丹之后，韩立才记录药效。"
    second_start = text.rindex("黄龙丹")
    segments = [
        {
            "segment_id": "seg-1",
            "title": "测试章节",
            "text": text,
            "start_line": 10,
            "start_char": 100,
            "end_char": 100 + len(text),
        }
    ]
    candidates = [
        {
            "name": "黄龙丹",
            "status": "needs-review",
            "segment_id": "seg-1",
            "start": second_start,
            "end": second_start + len("黄龙丹"),
            "start_char": 100 + second_start,
            "end_char": 100 + second_start + len("黄龙丹"),
        }
    ]

    evidence = build_evidence_pack(candidates, segments, context_chars=8)

    assert evidence[0]["source_span"] == {
        "start_char": 100 + second_start,
        "end_char": 100 + second_start + len("黄龙丹"),
    }
    assert evidence[0]["line"] == 10
    assert "真正服下黄龙丹" in evidence[0]["summary"]


def test_build_evidence_rejects_inconsistent_global_offsets():
    text = "黄龙丹只是传闻。真正服下黄龙丹之后，韩立才记录药效。"
    second_start = text.rindex("黄龙丹")
    segments = [
        {
            "segment_id": "seg-1",
            "title": "测试章节",
            "text": text,
            "start_line": 10,
            "start_char": 100,
            "end_char": 100 + len(text),
        }
    ]
    candidates = [
        {
            "name": "黄龙丹",
            "status": "needs-review",
            "segment_id": "seg-1",
            "start": second_start,
            "end": second_start + len("黄龙丹"),
            "start_char": 100,
            "end_char": 100 + len("黄龙丹"),
        }
    ]

    with pytest.raises(ValueError, match="global offsets"):
        build_evidence_pack(candidates, segments, context_chars=8)


def test_build_evidence_rejects_span_text_that_does_not_match_name():
    text = "韩立服下黄龙丹。"
    start = text.index("黄龙丹")
    segments = [
        {
            "segment_id": "seg-1",
            "title": "测试章节",
            "text": text,
            "start_line": 1,
            "start_char": 50,
            "end_char": 50 + len(text),
        }
    ]
    candidates = [
        {
            "name": "金髓丸",
            "status": "needs-review",
            "segment_id": "seg-1",
            "start": start,
            "end": start + len("黄龙丹"),
            "start_char": 50 + start,
            "end_char": 50 + start + len("黄龙丹"),
        }
    ]

    with pytest.raises(ValueError, match="span text"):
        build_evidence_pack(candidates, segments)


def test_render_and_validate_medicine_report(tmp_path):
    fixture = _minimal_confirmed_fixture()
    out = tmp_path / "凡人修仙传丹药分析.md"

    render_report(fixture, out)
    result = validate_report(
        out,
        fixture["report_config"]["required_columns"],
        ["丹田", "结丹", "散发", "脸上露"],
    )

    assert result["passed"] is True
    assert "# 《凡人修仙传》丹药分析" in out.read_text(encoding="utf-8")


def test_render_rejects_confirmed_item_without_source_spans(tmp_path):
    fixture = _minimal_confirmed_fixture()
    fixture["items"][0]["source_spans"] = []

    with pytest.raises(ValueError, match="source_spans"):
        render_report(fixture, tmp_path / "凡人修仙传丹药分析.md")


def test_validate_report_rejects_duplicate_names(tmp_path):
    report = tmp_path / "report.md"
    report.write_text(
        "\n".join(
            [
                "# 《凡人修仙传》丹药分析",
                "",
                "| 丹药名称 | 稀有度 | 功效 |",
                "| --- | --- | --- |",
                "| 黄龙丹 | 原文未说明 | 辅助修炼 |",
                "| 黄龙丹 | 原文未说明 | 增加功力 |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = validate_report(report, ["丹药名称", "稀有度", "功效"], [])
    duplicate_error = next(
        error
        for error in result["blocking_errors"]
        if error["type"] == "duplicate_names"
    )

    assert result["passed"] is False
    assert duplicate_error["duplicate_names"] == ["黄龙丹"]


def test_expected_present_is_validation_only(tmp_path):
    confirmed = {
        "work_title": "凡人修仙传",
        "items": [
            {
                "status": "confirmed",
                "name": "黄龙丹",
                "fields": {"丹药名称": "黄龙丹"},
                "source_spans": [
                    {"segment_id": "seg-1", "line": 1, "summary": "证据摘要"}
                ],
            }
        ],
    }
    expected = {"expected_present": ["黄龙丹", "金髓丸"]}

    result = validate_expected_present(confirmed, expected)

    assert result["blocking_errors"] == []
    assert result["coverage_warnings"]["expected_present_missing"] == ["金髓丸"]
    assert all(item["name"] != "金髓丸" for item in confirmed["items"])
