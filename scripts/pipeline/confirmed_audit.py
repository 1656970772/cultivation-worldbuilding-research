from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _configured_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _raw_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _blank(value: Any) -> bool:
    return _text(value) == ""


def _confirmed_items(confirmed: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_items = confirmed.get("items", [])
    if not isinstance(raw_items, list):
        return []
    return [
        item
        for item in raw_items
        if isinstance(item, Mapping)
        and _text(item.get("status", "confirmed")) == "confirmed"
    ]


def _item_name(item: Mapping[str, Any]) -> str:
    return _text(item.get("name"))


def _item_fields(item: Mapping[str, Any]) -> Mapping[str, Any]:
    return _as_mapping(item.get("fields", {}))


def _item_aliases(item: Mapping[str, Any]) -> list[str]:
    return [_text(alias) for alias in _raw_list(item.get("aliases")) if _text(alias)]


def _add_error(errors: list[dict[str, Any]], error: dict[str, Any]) -> None:
    errors.append(error)


def _duplicate_name_errors(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, list[int]] = {}
    for index, item in enumerate(items):
        name = _item_name(item)
        if not name:
            continue
        seen.setdefault(name, []).append(index)
    return [
        {"type": "duplicate_name", "name": name, "indices": indices}
        for name, indices in seen.items()
        if len(indices) > 1
    ]


def _alias_conflict_errors(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    item_names = {_item_name(item) for item in items if _item_name(item)}
    alias_owner: dict[str, str] = {}
    errors: list[dict[str, Any]] = []
    emitted: set[tuple[str, str, str]] = set()

    for item in items:
        name = _item_name(item)
        for alias in _item_aliases(item):
            if alias in item_names and alias != name:
                key = (alias, name, alias)
                if key not in emitted:
                    errors.append(
                        {
                            "type": "alias_conflict",
                            "name": name,
                            "alias": alias,
                            "conflicts_with": alias,
                        }
                    )
                    emitted.add(key)

            owner = alias_owner.get(alias)
            if owner is not None and owner != name:
                key = (alias, name, owner)
                if key not in emitted:
                    errors.append(
                        {
                            "type": "alias_conflict",
                            "name": name,
                            "alias": alias,
                            "conflicts_with": owner,
                        }
                    )
                    emitted.add(key)
            else:
                alias_owner[alias] = name
    return errors


def _valid_int(value: Any) -> bool:
    return type(value) is int


def _invalid_span_reason(span: Any) -> str | None:
    if not isinstance(span, Mapping):
        return "source span must be an object"
    has_start = "start_char" in span
    has_end = "end_char" in span
    if has_start != has_end:
        return "start_char and end_char must be provided together"
    if has_start and has_end:
        start = span.get("start_char")
        end = span.get("end_char")
        if not _valid_int(start) or not _valid_int(end):
            return "start_char and end_char must be integers"
        if start < 0 or end <= start:
            return "end_char must be greater than start_char"
    return None


def _source_span_errors(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for item in items:
        name = _item_name(item)
        spans = item.get("source_spans")
        if spans is None or spans == []:
            errors.append({"type": "missing_source_spans", "name": name})
            continue
        if not isinstance(spans, list):
            errors.append(
                {
                    "type": "invalid_source_spans",
                    "name": name,
                    "reason": "source_spans must be a list",
                }
            )
            continue
        for span_index, span in enumerate(spans):
            reason = _invalid_span_reason(span)
            if reason is not None:
                errors.append(
                    {
                        "type": "invalid_source_spans",
                        "name": name,
                        "span_index": span_index,
                        "reason": reason,
                    }
                )
    return errors


def _missing_required_field_errors(
    items: list[Mapping[str, Any]],
    required_fields: list[str],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for item in items:
        fields = _item_fields(item)
        for field in required_fields:
            if field not in fields or _blank(fields.get(field)):
                errors.append(
                    {
                        "type": "missing_required_field",
                        "name": _item_name(item),
                        "field": field,
                    }
                )
    return errors


def _search_values(item: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    name = _item_name(item)
    if name:
        yield "name", name
    for alias in _item_aliases(item):
        yield "alias", alias
    for field, value in _item_fields(item).items():
        if isinstance(value, (dict, list)):
            continue
        text = _text(value)
        if text:
            yield f"field:{field}", text


def _forbidden_term_errors(
    items: list[Mapping[str, Any]],
    forbidden_terms: list[str],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for item in items:
        name = _item_name(item)
        for location, value in _search_values(item):
            for term in forbidden_terms:
                if term and term in value:
                    errors.append(
                        {
                            "type": "forbidden_term",
                            "name": name,
                            "term": term,
                            "location": location,
                        }
                    )
    return errors


def _table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if "|" not in stripped:
        return []
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]

    cells: list[str] = []
    cell: list[str] = []
    escaped = False
    for char in stripped:
        if char == "\\" and not escaped:
            escaped = True
            cell.append(char)
            continue
        if char == "|" and not escaped:
            cells.append("".join(cell).strip().replace("\\|", "|"))
            cell = []
            escaped = False
            continue
        cell.append(char)
        escaped = False
    cells.append("".join(cell).strip().replace("\\|", "|"))
    return cells


def _is_separator_cells(cells: list[str]) -> bool:
    if not cells:
        return False
    for cell in cells:
        compact = cell.replace(" ", "")
        if not compact or "-" not in compact or set(compact) - {"-", ":"}:
            return False
    return True


def _markdown_tables(markdown_text: str) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    lines = markdown_text.splitlines()
    index = 0
    while index < len(lines) - 1:
        header = _table_cells(lines[index])
        separator = _table_cells(lines[index + 1])
        if not header or not _is_separator_cells(separator):
            index += 1
            continue

        rows: list[list[str]] = []
        index += 2
        while index < len(lines):
            row = _table_cells(lines[index])
            if not row:
                break
            if _is_separator_cells(row):
                break
            rows.append(row)
            index += 1
        tables.append({"header": header, "rows": rows})
    return tables


def _derived_name_fields(items: list[Mapping[str, Any]]) -> list[str]:
    fields: list[str] = []
    for item in items:
        name = _item_name(item)
        if not name:
            continue
        for field, value in _item_fields(item).items():
            field_name = str(field)
            if _text(value) == name and field_name not in fields:
                fields.append(field_name)
    return fields


def _score_table(
    table: Mapping[str, Any],
    *,
    name_fields: list[str],
    required_fields: list[str],
    item_names: list[str],
) -> tuple[int, int, int]:
    header = [str(cell) for cell in table.get("header", [])]
    rows = table.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    header_set = set(header)
    score = 0
    score += 5 * sum(field in header_set for field in name_fields)
    score += 2 * sum(field in header_set for field in required_fields)

    row_name_hits = 0
    for name in item_names:
        if not name:
            continue
        if any(name in str(cell) for row in rows for cell in row):
            row_name_hits += 1
    score += 3 * row_name_hits
    return score, row_name_hits, len(rows)


def _select_main_table(
    markdown_text: str,
    items: list[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    tables = _markdown_tables(markdown_text)
    if not tables:
        return None

    name_fields = []
    for field in [
        *_configured_list(config.get("name_fields")),
        *_derived_name_fields(items),
    ]:
        if field not in name_fields:
            name_fields.append(field)
    required_fields = _configured_list(config.get("required_fields"))
    item_names = [_item_name(item) for item in items if _item_name(item)]

    return max(
        tables,
        key=lambda table: _score_table(
            table,
            name_fields=name_fields,
            required_fields=required_fields,
            item_names=item_names,
        ),
    )


def _expected_present_warnings(
    items: list[Mapping[str, Any]],
    expected: Mapping[str, Any],
) -> list[dict[str, Any]]:
    expected_present = _configured_list(expected.get("expected_present"))
    if not expected_present:
        return []
    confirmed_names = {_item_name(item) for item in items if _item_name(item)}
    missing = [name for name in expected_present if name not in confirmed_names]
    if not missing:
        return []
    return [{"type": "expected_present_missing", "names": missing}]


def audit_confirmed(
    confirmed: Mapping[str, Any],
    *,
    expected: Mapping[str, Any] | None,
    markdown_text: str | None,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    config = _as_mapping(config)
    expected = _as_mapping(expected)
    items = _confirmed_items(_as_mapping(confirmed))
    required_fields = _configured_list(config.get("required_fields"))
    blocking_errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    blocking_errors.extend(_duplicate_name_errors(items))
    if bool(config.get("check_alias_conflicts", True)):
        blocking_errors.extend(_alias_conflict_errors(items))
    if bool(config.get("require_source_spans", True)):
        blocking_errors.extend(_source_span_errors(items))
    blocking_errors.extend(_missing_required_field_errors(items, required_fields))
    blocking_errors.extend(
        _forbidden_term_errors(items, _configured_list(config.get("forbidden_terms")))
    )
    warnings.extend(_expected_present_warnings(items, expected))

    counts: dict[str, Any] = {
        "items": len(items),
        "blocking_errors": 0,
        "warnings": 0,
    }

    if markdown_text is not None and bool(config.get("check_markdown_row_count", True)):
        main_table = _select_main_table(markdown_text, items, config)
        markdown_rows = len(main_table.get("rows", [])) if main_table is not None else 0
        counts["markdown_rows"] = markdown_rows
        counts["markdown_tables"] = len(_markdown_tables(markdown_text))
        if markdown_rows != len(items):
            _add_error(
                blocking_errors,
                {
                    "type": "markdown_row_count_mismatch",
                    "confirmed_items": len(items),
                    "markdown_rows": markdown_rows,
                },
            )

    counts["blocking_errors"] = len(blocking_errors)
    counts["warnings"] = len(warnings)
    return {
        "passed": not blocking_errors,
        "counts": counts,
        "blocking_errors": blocking_errors,
        "warnings": warnings,
    }
