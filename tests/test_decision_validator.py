import pytest

from scripts.pipeline.decision_validator import (
    DecisionRecord,
    load_decision_records,
    resolve_review_workflow,
    validate_decision_records,
    validate_decisions,
)


def test_review_workflow_defaults_are_generic():
    config = resolve_review_workflow({})
    assert 40 <= config.entries_per_shard <= 80
    assert config.part_dir == "review-decisions.parts"
    assert config.allowed_decisions == ("confirmed", "rejected", "needs-review")
    assert config.require_all_review_ids is True
    assert config.expected_present_blocking is False


def test_review_workflow_rejects_non_positive_entries_per_shard():
    with pytest.raises(ValueError, match="review_workflow.entries_per_shard"):
        resolve_review_workflow({"review_workflow": {"entries_per_shard": 0}})


def _review_entry(review_id, name, *, fields=None, source_spans=None):
    if source_spans is None:
        source_spans = [{"segment_id": "seg-001", "line": 1, "summary": name}]
    return {
        "review_id": review_id,
        "name": name,
        "fields": fields or {"名称": name},
        "source_spans": source_spans,
    }


def _types(items):
    return {item["type"] for item in items}


def _first(items, error_type):
    return next(item for item in items if item["type"] == error_type)


def test_validate_decisions_blocks_missing_duplicate_extra_and_invalid_decisions():
    review_entries = [
        _review_entry("review-001", "甲"),
        _review_entry("review-002", "乙"),
        _review_entry("review-003", "丙"),
    ]

    report = validate_decisions(
        review_entries,
        [
            {"review_id": "review-001", "decision": "confirmed", "name": "甲"},
            {"review_id": "review-002", "decision": "maybe", "name": "乙"},
            {"review_id": "review-002", "decision": "rejected", "name": "乙"},
            {"review_id": "review-999", "decision": "confirmed", "name": "额外"},
        ],
        {},
        {},
    )

    assert report["passed"] is False
    assert {
        "invalid_decision",
        "missing_review_id",
        "duplicate_review_id",
        "extra_review_id",
    } <= _types(report["blocking_errors"])


def test_decision_record_error_context_includes_line_shard_and_review_id():
    report = validate_decision_records(
        [_review_entry("review-001", "甲")],
        [
            DecisionRecord(
                path="part.jsonl",
                line=7,
                shard="002",
                data={"review_id": "review-001", "decision": "bogus", "name": "甲"},
            )
        ],
        {},
        {},
    )

    error = _first(report["blocking_errors"], "invalid_decision")
    assert error["path"] == "part.jsonl"
    assert error["line"] == 7
    assert error["shard"] == "002"
    assert error["review_id"] == "review-001"


def test_load_decision_records_keeps_invalid_jsonl_lines_for_validation(tmp_path):
    decisions = tmp_path / "part.jsonl"
    decisions.write_text(
        "\n".join(
            [
                '{"review_id": "review-001", "decision": "confirmed", "name": "甲"}',
                "{not json",
                '["not", "an", "object"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    records = load_decision_records(decisions, shard="003")
    report = validate_decision_records(
        [_review_entry("review-001", "甲")],
        records,
        {},
        {},
    )

    assert len(records) == 3
    assert records[1].line == 2
    assert records[1].shard == "003"
    assert {"invalid_json", "invalid_jsonl_object"} <= _types(report["blocking_errors"])


def test_load_decision_records_streams_invalid_jsonl_with_line_context(tmp_path, monkeypatch):
    decisions = tmp_path / "part.jsonl"
    decisions.write_text(
        "\n".join(
            [
                '{"review_id": "review-001", "decision": "confirmed", "name": "甲"}',
                "",
                '{"review_id": "review-002", "decision": "rejected", "name": "乙"}',
                "{not json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fail_read_text(*args, **kwargs):
        raise AssertionError("load_decision_records must stream with open()")

    monkeypatch.setattr(type(decisions), "read_text", fail_read_text)

    records = load_decision_records(decisions, shard="003")
    report = validate_decision_records(
        [_review_entry("review-001", "甲"), _review_entry("review-002", "乙")],
        records,
        {},
        {},
    )

    error = _first(report["blocking_errors"], "invalid_json")
    assert error["line"] == 4
    assert error["shard"] == "003"


def test_expected_present_is_warning_by_default_and_blocking_when_configured():
    review_entries = [_review_entry("review-001", "甲")]
    decisions = [{"review_id": "review-001", "decision": "confirmed", "name": "甲"}]
    expected = {"expected_present": ["甲", "乙"]}

    warning_report = validate_decisions(review_entries, decisions, {}, expected)

    assert warning_report["passed"] is True
    assert "expected_present_missing" in _types(warning_report["warnings"])
    assert "expected_present_missing" not in _types(warning_report["blocking_errors"])

    blocking_report = validate_decisions(
        review_entries,
        decisions,
        {"decision_validation": {"expected_present_blocking": True}},
        expected,
    )

    assert blocking_report["passed"] is False
    assert "expected_present_missing" in _types(blocking_report["blocking_errors"])


def test_expected_forbidden_names_block_confirmed_decisions():
    report = validate_decisions(
        [_review_entry("review-001", "甲")],
        [{"review_id": "review-001", "decision": "confirmed", "name": "甲"}],
        {},
        {"forbidden_names": ["甲"]},
    )

    assert report["passed"] is False
    assert "forbidden_confirmed_name" in _types(report["blocking_errors"])


def test_curation_forbidden_confirmed_names_block_confirmed_decisions():
    report = validate_decisions(
        [_review_entry("review-001", "甲")],
        [{"review_id": "review-001", "decision": "confirmed", "name": "甲"}],
        {"decision_validation": {"forbidden_confirmed_names": ["甲"]}},
        {},
    )

    assert report["passed"] is False
    assert "forbidden_confirmed_name" in _types(report["blocking_errors"])


def test_forbidden_confirmed_name_error_context_includes_current_decision_record():
    report = validate_decision_records(
        [_review_entry("review-001", "甲")],
        [
            DecisionRecord(
                path="part.jsonl",
                line=7,
                shard="002",
                data={"review_id": "review-001", "decision": "confirmed", "name": "甲"},
            )
        ],
        {"decision_validation": {"forbidden_confirmed_names": ["甲"]}},
        {},
    )

    error = _first(report["blocking_errors"], "forbidden_confirmed_name")
    assert error["path"] == "part.jsonl"
    assert error["line"] == 7
    assert error["shard"] == "002"
    assert error["review_id"] == "review-001"
    assert error["name"] == "甲"


def test_confirmed_requires_source_spans_from_review_pack_entry():
    report = validate_decisions(
        [_review_entry("review-001", "甲", source_spans=[])],
        [
            {
                "review_id": "review-001",
                "decision": "confirmed",
                "name": "甲",
                "fields": {"来源": "伪造字段"},
                "source_spans": [{"segment_id": "decision-only"}],
                "evidence": [{"segment_id": "decision-only"}],
            }
        ],
        {},
        {},
    )

    assert report["passed"] is False
    assert "missing_confirmed_source_spans" in _types(report["blocking_errors"])


def test_require_confirmed_source_spans_false_allows_empty_review_pack_spans():
    report = validate_decisions(
        [_review_entry("review-001", "甲", source_spans=[])],
        [{"review_id": "review-001", "decision": "confirmed", "name": "甲"}],
        {"decision_validation": {"require_confirmed_source_spans": False}},
        {},
    )

    assert report["passed"] is True
    assert "missing_confirmed_source_spans" not in _types(report["blocking_errors"])


def test_require_all_review_ids_false_allows_partial_decisions():
    report = validate_decisions(
        [_review_entry("review-001", "甲"), _review_entry("review-002", "乙")],
        [{"review_id": "review-001", "decision": "confirmed", "name": "甲"}],
        {"decision_validation": {"require_all_review_ids": False}},
        {},
    )

    assert report["passed"] is True
    assert "missing_review_id" not in _types(report["blocking_errors"])


def test_missing_required_fields_fill_unknown_mutates_decision_and_warns():
    decision = {
        "review_id": "review-001",
        "decision": "confirmed",
        "name": "甲",
        "fields": {"名称": "甲"},
    }

    report = validate_decisions(
        [_review_entry("review-001", "甲", fields={"名称": "甲"})],
        [decision],
        {"fields": {"required": ["名称", "功效"]}},
        {},
    )

    assert report["passed"] is True
    assert decision["fields"]["功效"] == "unknown"
    assert "missing_required_field" in _types(report["warnings"])


def test_missing_required_fields_block_when_policy_is_block():
    report = validate_decisions(
        [_review_entry("review-001", "甲", fields={"名称": "甲"})],
        [
            {
                "review_id": "review-001",
                "decision": "confirmed",
                "name": "甲",
                "fields": {"名称": "甲"},
            }
        ],
        {
            "fields": {"required": ["名称", "功效"]},
            "decision_validation": {"required_field_policy": "block"},
        },
        {},
    )

    assert report["passed"] is False
    assert "missing_required_field" in _types(report["blocking_errors"])
