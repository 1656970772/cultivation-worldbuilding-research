import json
from pathlib import Path

from scripts.pipeline.review_pack import (
    build_review_entries,
    load_curation_pack,
    normalize_candidate_name,
    write_review_pack,
)


ROOT = Path(__file__).resolve().parents[1]


def _curation(auto_confirm=False):
    return {
        "curation_pack": "entity-medicine",
        "subject_type": "丹药",
        "review": {
            "auto_confirm": auto_confirm,
            "max_evidence_per_entry": 5,
            "reject_exact": ["丹田", "丹药"],
        },
        "fields": {
            "required": ["丹药名称", "稀有度", "功效"],
            "unknown_text": "原文未说明",
        },
    }


def test_normalize_candidate_name_trims_whitespace_and_common_punctuation():
    assert normalize_candidate_name("  《黄龙丹》。 ") == "黄龙丹"


def test_same_name_candidates_are_grouped_into_one_review_entry():
    candidates = [
        {"name": "黄龙丹", "segment_id": "seg-001", "start_char": 10, "end_char": 13},
        {"name": " 黄龙丹 ", "segment_id": "seg-002", "start_char": 30, "end_char": 33},
    ]
    evidence = [
        {
            "name": "黄龙丹",
            "segment_id": "seg-001",
            "line": 1,
            "summary": "韩立服下黄龙丹。",
            "source_span": {"start_char": 10, "end_char": 13},
        },
        {
            "name": "黄龙丹",
            "segment_id": "seg-002",
            "line": 8,
            "summary": "瓶中还剩黄龙丹。",
            "source_span": {"start_char": 30, "end_char": 33},
        },
    ]

    entries = build_review_entries(candidates, evidence, _curation())

    assert len(entries) == 1
    entry = entries[0]
    assert entry["review_id"] == "medicine-000001"
    assert entry["name"] == "黄龙丹"
    assert entry["aliases"] == []
    assert entry["status_suggestion"] == "needs-review"
    assert entry["candidate_count"] == 2
    assert entry["evidence_count"] == 2
    assert entry["fields"] == {
        "丹药名称": "黄龙丹",
        "稀有度": "原文未说明",
        "功效": "原文未说明",
    }


def test_noise_exact_and_curation_reject_exact_are_not_confirmed_suggestions():
    candidates = [
        {"name": "丹田", "segment_id": "seg-001", "start_char": 1, "end_char": 3},
        {
            "name": "丹药",
            "status": "confirmed",
            "segment_id": "seg-002",
            "start_char": 5,
            "end_char": 7,
        },
        {
            "name": "筑基丹",
            "status": "confirmed",
            "segment_id": "seg-003",
            "start_char": 10,
            "end_char": 13,
        },
    ]
    evidence = [
        {
            "name": "丹田",
            "segment_id": "seg-001",
            "summary": "韩立检查丹田。",
            "source_span": {"start_char": 1, "end_char": 3},
        },
        {
            "name": "丹药",
            "segment_id": "seg-002",
            "summary": "此处泛称丹药。",
            "source_span": {"start_char": 5, "end_char": 7},
        },
        {
            "name": "筑基丹",
            "segment_id": "seg-003",
            "summary": "筑基丹可辅助筑基。",
            "source_span": {"start_char": 10, "end_char": 13},
        },
    ]
    curation = _curation(auto_confirm=True)

    entries = build_review_entries(candidates, evidence, curation)
    by_name = {entry["name"]: entry for entry in entries}

    assert by_name["丹田"]["status_suggestion"] == "rejected"
    assert by_name["丹药"]["status_suggestion"] == "rejected"
    assert by_name["筑基丹"]["status_suggestion"] == "needs-review"
    assert not any(entry["status_suggestion"] == "confirmed" for entry in entries)


def test_entries_keep_evidence_count_segments_and_source_spans():
    candidates = [
        {"name": "清灵散", "segment_id": "seg-001", "start_char": 100, "end_char": 103},
        {"name": "清灵散", "segment_id": "seg-002", "start_char": 200, "end_char": 203},
    ]
    evidence = [
        {
            "name": "清灵散",
            "segment_id": "seg-001",
            "line": 12,
            "summary": "清灵散用于压制毒性。",
            "source_span": {"start_char": 100, "end_char": 103},
            "local_span": {"start": 4, "end": 7},
        },
        {
            "name": "清灵散",
            "segment_id": "seg-002",
            "title": "第二章",
            "line": 45,
            "summary": "他又取出清灵散。",
            "source_span": {"start_char": 200, "end_char": 203},
        },
    ]

    [entry] = build_review_entries(candidates, evidence, _curation())

    assert entry["evidence_count"] == 2
    assert entry["segments"] == ["seg-001", "seg-002"]
    assert entry["source_spans"] == [
        {
            "segment_id": "seg-001",
            "start_char": 100,
            "end_char": 103,
            "line": 12,
            "summary": "清灵散用于压制毒性。",
            "local_span": {"start": 4, "end": 7},
        },
        {
            "segment_id": "seg-002",
            "title": "第二章",
            "start_char": 200,
            "end_char": 203,
            "line": 45,
            "summary": "他又取出清灵散。",
        },
    ]


def test_low_evidence_candidate_needs_review_and_required_examples_do_not_inject_confirmed():
    curation = _curation(auto_confirm=True)
    curation["review"]["required_confirmed_examples"] = ["补天丹"]
    candidates = [
        {"name": "回阳水", "segment_id": "seg-001", "start_char": 1, "end_char": 4},
    ]
    evidence = [
        {
            "name": "回阳水",
            "segment_id": "seg-001",
            "summary": "传闻回阳水能救命。",
            "source_span": {"start_char": 1, "end_char": 4},
        }
    ]

    entries = build_review_entries(candidates, evidence, curation)

    assert [entry["name"] for entry in entries] == ["回阳水"]
    assert entries[0]["status_suggestion"] == "needs-review"
    assert not any(entry["name"] == "补天丹" for entry in entries)


def test_load_curation_pack_reads_medicine_configuration():
    curation = load_curation_pack(ROOT / "assets" / "curation" / "entity-medicine.yaml")

    assert curation["curation_pack"] == "entity-medicine"
    assert curation["subject_type"] == "丹药"
    assert curation["review"]["auto_confirm"] is False
    assert curation["fields"]["unknown_text"] == "原文未说明"
    assert "筑基丹" in curation["review"]["required_confirmed_examples"]


def test_write_review_pack_outputs_jsonl_and_auditable_markdown(tmp_path):
    entry = {
        "review_id": "medicine-000001",
        "name": "黄龙丹",
        "aliases": [],
        "status_suggestion": "needs-review",
        "evidence_count": 1,
        "candidate_count": 1,
        "segments": ["seg-001"],
        "source_spans": [
            {
                "segment_id": "seg-001",
                "start_char": 10,
                "end_char": 13,
                "line": 6,
                "summary": "韩立服下黄龙丹。",
            }
        ],
        "fields": {"丹药名称": "黄龙丹"},
    }
    jsonl_path = tmp_path / "review-pack.jsonl"
    markdown_path = tmp_path / "review-pack.md"

    write_review_pack([entry], jsonl_path, markdown_path)

    lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0]) == entry
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "medicine-000001" in markdown
    assert "黄龙丹" in markdown
    assert "needs-review" in markdown
    assert "韩立服下黄龙丹。" in markdown
    assert "seg-001:10-13" in markdown
