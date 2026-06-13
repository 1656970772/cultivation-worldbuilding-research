from scripts.pipeline.confirmed_audit import audit_confirmed


def _item(name, *, aliases=None, fields=None, source_spans=None):
    item = {
        "status": "confirmed",
        "name": name,
        "aliases": aliases or [],
        "fields": fields or {"Name": name, "Effect": "known"},
    }
    if source_spans is not None:
        item["source_spans"] = source_spans
    return item


def _valid_span(start=0, end=5):
    return {
        "segment_id": "seg-001",
        "start_char": start,
        "end_char": end,
        "line": 1,
        "summary": "evidence",
    }


def test_audit_detects_duplicate_name_alias_conflict_and_missing_spans():
    confirmed = {
        "items": [
            _item("Alpha", aliases=["Shared"], source_spans=[_valid_span(0, 5)]),
            _item("Alpha", source_spans=[_valid_span(10, 15)]),
            _item(
                "Beta",
                aliases=["Alpha"],
                fields={"Name": "Beta"},
                source_spans=[],
            ),
            _item(
                "Gamma",
                source_spans=[{"segment_id": "seg-002", "start_char": 20, "end_char": 10}],
            ),
        ]
    }

    result = audit_confirmed(
        confirmed,
        expected={"expected_present": ["Alpha", "Missing"]},
        markdown_text=None,
        config={
            "name_fields": ["Name"],
            "required_fields": ["Name", "Effect"],
            "check_alias_conflicts": True,
            "require_source_spans": True,
        },
    )

    assert result["passed"] is False
    error_types = {error["type"] for error in result["blocking_errors"]}
    assert {
        "duplicate_name",
        "alias_conflict",
        "missing_source_spans",
        "invalid_source_spans",
        "missing_required_field",
    } <= error_types
    assert result["counts"]["items"] == 4
    assert result["warnings"] == [
        {"type": "expected_present_missing", "names": ["Missing"]}
    ]


def test_audit_forbidden_terms_and_markdown_row_count():
    confirmed = {
        "items": [
            _item(
                "Alpha",
                fields={"Name": "Alpha", "Effect": "contains ForbiddenTerm"},
                source_spans=[_valid_span(0, 5)],
            ),
            _item("Beta", source_spans=[_valid_span(10, 14)]),
        ]
    }
    markdown = "\n".join(
        [
            "| Name | Effect |",
            "| --- | --- |",
            "| Alpha | contains ForbiddenTerm |",
        ]
    )

    result = audit_confirmed(
        confirmed,
        expected=None,
        markdown_text=markdown,
        config={
            "name_fields": ["Name"],
            "required_fields": ["Name", "Effect"],
            "forbidden_terms": ["ForbiddenTerm"],
            "check_markdown_row_count": True,
        },
    )

    errors = {error["type"]: error for error in result["blocking_errors"]}
    assert result["passed"] is False
    assert errors["forbidden_term"]["term"] == "ForbiddenTerm"
    assert errors["markdown_row_count_mismatch"]["confirmed_items"] == 2
    assert errors["markdown_row_count_mismatch"]["markdown_rows"] == 1


def test_audit_markdown_header_separator_are_not_data_rows():
    confirmed = {
        "items": [
            _item("Alpha", source_spans=[_valid_span(0, 5)]),
        ]
    }
    markdown = "\n".join(
        [
            "| Name | Effect |",
            "| --- | --- |",
            "| Alpha | known |",
        ]
    )

    result = audit_confirmed(
        confirmed,
        expected=None,
        markdown_text=markdown,
        config={
            "name_fields": ["Name"],
            "required_fields": ["Name", "Effect"],
            "check_markdown_row_count": True,
        },
    )

    assert result["passed"] is True
    assert result["counts"]["markdown_rows"] == 1
    assert result["blocking_errors"] == []


def test_audit_markdown_selects_main_table_when_multiple_tables_exist():
    confirmed = {
        "items": [
            _item("Alpha", source_spans=[_valid_span(0, 5)]),
            _item("Beta", source_spans=[_valid_span(10, 14)]),
        ]
    }
    markdown = "\n".join(
        [
            "| Metric | Value |",
            "| --- | --- |",
            "| confirmed | 2 |",
            "",
            "| Name | Effect |",
            "| --- | --- |",
            "| Alpha | known |",
            "| Beta | known |",
        ]
    )

    result = audit_confirmed(
        confirmed,
        expected=None,
        markdown_text=markdown,
        config={
            "name_fields": ["Name"],
            "required_fields": ["Name", "Effect"],
            "check_markdown_row_count": True,
        },
    )

    assert result["passed"] is True
    assert result["counts"]["markdown_rows"] == 2
    assert result["blocking_errors"] == []
