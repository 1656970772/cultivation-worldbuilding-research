from pathlib import Path

from scripts.pipeline.evidence_builder import build_evidence_pack
from scripts.pipeline.renderer import render_report
from scripts.pipeline.validator import validate_expected_present, validate_report


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


def test_render_and_validate_medicine_report(tmp_path):
    fixture = {
        "work_title": "凡人修仙传",
        "report_config": {
            "subject_type": "丹药",
            "report_title": "《凡人修仙传》丹药分析",
            "unknown_text": "原文未说明",
            "output_name": "凡人修仙传丹药分析.md",
            "required_columns": [
                "丹药名称",
                "稀有度",
                "功效",
                "用途",
                "丹方",
                "炼制方式",
                "来源",
                "限制/副作用",
                "适用境界",
            ],
            "evidence_in_final_report": False,
        },
        "items": [
            {
                "status": "confirmed",
                "name": "黄龙丹",
                "fields": {
                    "丹药名称": "黄龙丹",
                    "稀有度": "原文未说明",
                    "功效": "辅助修炼",
                    "用途": "修炼",
                    "丹方": "原文未说明",
                    "炼制方式": "原文未说明",
                    "来源": "原文未说明",
                    "限制/副作用": "原文未说明",
                    "适用境界": "炼气",
                },
                "source_spans": [
                    {"segment_id": "seg-1", "line": 1, "summary": "证据摘要"}
                ],
            }
        ],
    }
    out = tmp_path / "凡人修仙传丹药分析.md"

    render_report(fixture, out)
    result = validate_report(
        out,
        fixture["report_config"]["required_columns"],
        ["丹田", "结丹", "散发", "脸上露"],
    )

    assert result["passed"] is True
    assert "# 《凡人修仙传》丹药分析" in out.read_text(encoding="utf-8")


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
