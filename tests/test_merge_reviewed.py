import importlib
import json

import pytest


def _module():
    try:
        return importlib.import_module("scripts.pipeline.merge_reviewed")
    except ModuleNotFoundError as exc:
        pytest.fail(f"merge_reviewed module is required: {exc}")


def _curation(required=None, unknown_text="原文未说明"):
    fields = {"required": required or ["丹药名称", "稀有度", "功效"]}
    if unknown_text is not None:
        fields["unknown_text"] = unknown_text
    return {
        "work_title": "凡人修仙传",
        "curation_pack": "entity-medicine",
        "fields": fields,
    }


def _entry(review_id="medicine-000001", name="黄龙丹", aliases=None, source_spans=None):
    return {
        "review_id": review_id,
        "name": name,
        "aliases": aliases or [],
        "fields": {
            "丹药名称": name,
            "稀有度": "原文未说明",
            "功效": "原文未说明",
        },
        "source_spans": source_spans
        if source_spans is not None
        else [
            {
                "segment_id": "seg-001",
                "start_char": 10,
                "end_char": 13,
                "line": 6,
                "summary": "韩立服下黄龙丹。",
            }
        ],
    }


def _decision(review_id="medicine-000001", decision="confirmed", name="黄龙丹", fields=None, aliases=None):
    return {
        "review_id": review_id,
        "decision": decision,
        "name": name,
        "aliases": aliases or [],
        "fields": fields if fields is not None else {"丹药名称": name, "功效": "辅助修炼"},
        "notes": "证据足够",
    }


def test_confirmed_decision_becomes_confirmed_item_with_source_spans():
    merge_reviewed_entries = _module().merge_reviewed_entries
    entry = _entry()
    decision = _decision()

    confirmed, report = merge_reviewed_entries(
        [entry],
        [decision],
        _curation(),
        {"subject_type": "丹药"},
    )

    assert confirmed["work_title"] == "凡人修仙传"
    assert confirmed["report_config"] == {
        "subject_type": "丹药",
        "required_columns": ["丹药名称", "稀有度", "功效"],
        "unknown_text": "原文未说明",
    }
    assert confirmed["items"] == [
        {
            "status": "confirmed",
            "name": "黄龙丹",
            "aliases": [],
            "fields": {
                "丹药名称": "黄龙丹",
                "稀有度": "原文未说明",
                "功效": "辅助修炼",
            },
            "source_spans": entry["source_spans"],
        }
    ]
    assert report["counts"]["confirmed"] == 1
    assert report["confirmed"][0]["review_id"] == "medicine-000001"


def test_rejected_decision_is_reported_and_not_written_to_confirmed_items():
    merge_reviewed_entries = _module().merge_reviewed_entries

    confirmed, report = merge_reviewed_entries(
        [_entry()],
        [_decision(decision="rejected", fields={"丹药名称": "黄龙丹"})],
        _curation(),
        {},
    )

    assert confirmed["items"] == []
    assert report["counts"]["rejected"] == 1
    assert report["rejected"] == [
        {
            "review_id": "medicine-000001",
            "name": "黄龙丹",
            "notes": "证据足够",
        }
    ]


def test_duplicate_confirmed_names_merge_aliases_fields_and_evidence_without_deleting_values():
    merge_reviewed_entries = _module().merge_reviewed_entries
    first_span = {"segment_id": "seg-001", "start_char": 10, "end_char": 13}
    second_span = {"segment_id": "seg-002", "start_char": 30, "end_char": 33}
    entries = [
        _entry(
            review_id="medicine-000001",
            name="黄龙丹",
            aliases=["黄龙"],
            source_spans=[first_span],
        ),
        _entry(
            review_id="medicine-000002",
            name="黄龙丹",
            aliases=["小黄龙丹"],
            source_spans=[second_span],
        ),
    ]
    decisions = [
        _decision(
            review_id="medicine-000001",
            aliases=["黄龙丹丸"],
            fields={"丹药名称": "黄龙丹", "稀有度": "", "功效": "辅助修炼"},
        ),
        _decision(
            review_id="medicine-000002",
            aliases=["黄龙丹别名"],
            fields={"丹药名称": "黄龙丹", "稀有度": "常见", "功效": ""},
        ),
    ]

    confirmed, report = merge_reviewed_entries(entries, decisions, _curation(), {})

    assert len(confirmed["items"]) == 1
    item = confirmed["items"][0]
    assert item["aliases"] == ["小黄龙丹", "黄龙", "黄龙丹丸", "黄龙丹别名"]
    assert item["fields"] == {
        "丹药名称": "黄龙丹",
        "稀有度": "常见",
        "功效": "辅助修炼",
    }
    assert item["source_spans"] == [first_span, second_span]
    assert report["counts"]["confirmed"] == 2


def test_confirmed_item_without_source_spans_raises_blocking_error():
    merge_reviewed_entries = _module().merge_reviewed_entries

    with pytest.raises(ValueError, match="source_spans"):
        merge_reviewed_entries(
            [_entry(source_spans=[])],
            [_decision()],
            _curation(),
            {},
        )


def test_confirmed_item_with_non_dict_source_span_raises_blocking_error():
    merge_reviewed_entries = _module().merge_reviewed_entries

    with pytest.raises(ValueError, match="source_spans"):
        merge_reviewed_entries(
            [_entry(source_spans=[None])],
            [_decision()],
            _curation(),
            {},
        )


def test_confirmed_item_with_empty_normalized_name_raises_blocking_error():
    merge_reviewed_entries = _module().merge_reviewed_entries

    with pytest.raises(ValueError, match="missing_name"):
        merge_reviewed_entries(
            [_entry(name="")],
            [_decision(name="", fields={})],
            _curation(),
            {},
        )


def test_confirmed_item_with_null_names_raises_blocking_error():
    merge_reviewed_entries = _module().merge_reviewed_entries

    with pytest.raises(ValueError, match="missing_name"):
        merge_reviewed_entries(
            [_entry(name=None)],
            [_decision(name=None, fields={})],
            _curation(),
            {},
        )


def test_decision_rename_preserves_review_entry_name_as_alias():
    merge_reviewed_entries = _module().merge_reviewed_entries

    confirmed, _report = merge_reviewed_entries(
        [_entry(name="黄龙丹")],
        [_decision(name="黄龙丹丸")],
        _curation(),
        {},
    )

    assert confirmed["items"][0]["name"] == "黄龙丹丸"
    assert "黄龙丹" in confirmed["items"][0]["aliases"]


def test_null_entry_name_and_aliases_are_not_emitted_as_aliases_when_decision_names_item():
    merge_reviewed_entries = _module().merge_reviewed_entries

    confirmed, _report = merge_reviewed_entries(
        [_entry(name=None, aliases=[None])],
        [_decision(name="黄龙丹丸", aliases=[None])],
        _curation(),
        {},
    )

    assert confirmed["items"][0]["name"] == "黄龙丹丸"
    assert "None" not in confirmed["items"][0]["aliases"]
    assert confirmed["items"][0]["aliases"] == []


def test_missing_or_blank_required_fields_use_unknown_text_and_name_field_uses_item_name():
    merge_reviewed_entries = _module().merge_reviewed_entries
    curation = _curation(required=["丹药名称", "稀有度", "功效"], unknown_text=None)

    confirmed, _report = merge_reviewed_entries(
        [_entry()],
        [_decision(fields={"稀有度": "", "功效": "   "})],
        curation,
        {},
    )

    assert confirmed["report_config"]["unknown_text"] == "原文未说明"
    assert confirmed["items"][0]["fields"] == {
        "丹药名称": "黄龙丹",
        "稀有度": "原文未说明",
        "功效": "原文未说明",
    }


def test_report_config_required_columns_and_unknown_text_fill_when_curation_fields_are_empty():
    merge_reviewed_entries = _module().merge_reviewed_entries
    curation = {"work_title": "凡人修仙传", "fields": {}}
    report_config = {
        "required_columns": ["丹药名称", "稀有度"],
        "unknown_text": "未知",
    }

    confirmed, _report = merge_reviewed_entries(
        [_entry()],
        [_decision(fields={})],
        curation,
        report_config,
    )

    assert confirmed["items"][0]["fields"] == {
        "丹药名称": "黄龙丹",
        "稀有度": "未知",
    }


def test_curation_unknown_text_overrides_report_config_unknown_text_for_field_fill():
    merge_reviewed_entries = _module().merge_reviewed_entries
    curation = _curation(required=["丹药名称", "稀有度"], unknown_text="未载")
    report_config = {"required_columns": ["丹药名称", "稀有度"], "unknown_text": "未知"}

    confirmed, _report = merge_reviewed_entries(
        [_entry()],
        [_decision(fields={"丹药名称": "黄龙丹", "稀有度": ""})],
        curation,
        report_config,
    )

    assert confirmed["report_config"]["unknown_text"] == "未知"
    assert confirmed["items"][0]["fields"] == {
        "丹药名称": "黄龙丹",
        "稀有度": "未载",
    }


def test_needs_review_decision_stays_out_of_confirmed_items_and_is_reported():
    merge_reviewed_entries = _module().merge_reviewed_entries

    confirmed, report = merge_reviewed_entries(
        [_entry()],
        [_decision(decision="needs-review")],
        _curation(),
        {},
    )

    assert confirmed["items"] == []
    assert report["counts"]["needs_review"] == 1
    assert report["needs_review"][0]["review_id"] == "medicine-000001"


def test_invalid_decision_raises_blocking_error():
    merge_reviewed_entries = _module().merge_reviewed_entries

    with pytest.raises(ValueError, match="decision must be one of"):
        merge_reviewed_entries(
            [_entry()],
            [_decision(decision="approved")],
            _curation(),
            {},
        )


def test_read_decisions_jsonl_reads_utf8_sig_skips_blanks_and_requires_objects(tmp_path):
    module = _module()
    path = tmp_path / "decisions.jsonl"
    path.write_text(
        "\ufeff" + json.dumps(_decision(), ensure_ascii=False) + "\n\n",
        encoding="utf-8",
    )

    assert module.read_decisions_jsonl(path) == [_decision()]

    bad_path = tmp_path / "bad-decisions.jsonl"
    bad_path.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        module.read_decisions_jsonl(bad_path)

    malformed_path = tmp_path / "malformed-decisions.jsonl"
    malformed_path.write_text('{"review_id": "medicine-000001"', encoding="utf-8")
    with pytest.raises(ValueError) as exc_info:
        module.read_decisions_jsonl(malformed_path)
    assert f"Invalid JSONL: {malformed_path}:1:" in str(exc_info.value)


def test_write_confirmed_outputs_writes_both_json_files(tmp_path):
    module = _module()
    confirmed = {"work_title": "凡人修仙传", "report_config": {}, "items": []}
    report = {
        "counts": {"confirmed": 0, "rejected": 0, "needs_review": 0, "blocking_errors": 0},
        "confirmed": [],
        "rejected": [],
        "needs_review": [],
        "blocking_errors": [],
    }
    confirmed_path = tmp_path / "confirmed-items.json"
    report_path = tmp_path / "curation-report.json"

    module.write_confirmed_outputs(confirmed, report, confirmed_path, report_path)

    assert json.loads(confirmed_path.read_text(encoding="utf-8")) == confirmed
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    confirmed_text = confirmed_path.read_text(encoding="utf-8")
    report_text = report_path.read_text(encoding="utf-8")
    assert confirmed_text.startswith('{\n  "work_title": "凡人修仙传"')
    assert report_text.startswith('{\n  "counts": {')
    assert "\\u51e1\\u4eba" not in confirmed_text
    assert confirmed_path.read_bytes().startswith(b"{")
    assert "  \"report_config\": {}" in confirmed_text
    assert confirmed_text.endswith("\n")
    assert report_text.endswith("\n")
