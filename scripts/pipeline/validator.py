from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    ok: bool
    messages: list[str]


def _configured_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _table_headers(markdown: str) -> list[list[str]]:
    return [table["header"] for table in _markdown_tables(markdown)]


def _markdown_tables(markdown: str) -> list[dict[str, list[list[str]] | list[str]]]:
    tables: list[dict[str, list[list[str]] | list[str]]] = []
    lines = markdown.splitlines()
    index = 0
    while index < len(lines) - 1:
        header = lines[index].strip()
        separator = lines[index + 1].strip()
        if not _is_table_row(header) or not _is_separator_row(separator):
            index += 1
            continue
        rows: list[list[str]] = []
        index += 2
        while index < len(lines) and _is_table_row(lines[index].strip()):
            rows.append(_table_cells(lines[index].strip()))
            index += 1
        tables.append({"header": _table_cells(header), "rows": rows})
    return tables


def _missing_columns(markdown: str, required_columns: list[str]) -> list[str]:
    if not required_columns:
        return []
    headers = _table_headers(markdown)
    for header in headers:
        if all(column in header for column in required_columns):
            return []
    closest_header = max(
        headers,
        key=lambda header: sum(column in header for column in required_columns),
        default=[],
    )
    return [column for column in required_columns if column not in closest_header]


def _is_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def _table_cells(line: str) -> list[str]:
    return [cell.strip().replace("\\|", "|") for cell in line.strip("|").split("|")]


def _is_separator_row(line: str) -> bool:
    if not _is_table_row(line):
        return False
    cells = _table_cells(line)
    return bool(cells) and all(set(cell) <= {"-", ":"} and "-" in cell for cell in cells)


def _duplicate_names(markdown: str) -> list[str]:
    duplicates: list[str] = []
    seen: set[str] = set()
    for table in _markdown_tables(markdown):
        header = table["header"]
        if "丹药名称" not in header:
            continue
        name_index = header.index("丹药名称")
        for row in table["rows"]:
            if name_index >= len(row):
                continue
            name = row[name_index]
            if not name:
                continue
            if name in seen and name not in duplicates:
                duplicates.append(name)
            seen.add(name)
    return duplicates


def _nested_dict(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key, {})
    return value if isinstance(value, dict) else {}


def _route_value(route: dict[str, Any], key: str) -> Any:
    if key in route:
        return route[key]
    validation_rules = _nested_dict(route, "validation_rules")
    if key in validation_rules:
        return validation_rules[key]
    output = _nested_dict(route, "output")
    if key in output:
        return output[key]
    return None


def _route_policy(route: dict[str, Any], key: str, default: str = "fail") -> str:
    value = _route_value(route, key)
    if value in (None, ""):
        return default
    return str(value).lower()


def _policy_blocks(policy: str) -> bool:
    return policy not in {"warn", "warning", "ignore", "off", "none"}


def _add_policy_message(
    messages: list[str],
    blocking_messages: list[str],
    message: str,
    policy: str,
) -> None:
    if policy in {"ignore", "off", "none"}:
        return
    messages.append(message)
    if _policy_blocks(policy):
        blocking_messages.append(message)


def _forbidden_table_modes(route: dict[str, Any]) -> list[str]:
    modes = _configured_list(_route_value(route, "forbidden_output_modes"))
    return [mode for mode in modes if "table" in mode.lower() or "表格" in mode]


def _field_label(line: str) -> str | None:
    stripped = line.strip()
    for marker in ("- ", "* "):
        if stripped.startswith(marker):
            stripped = stripped[len(marker) :].strip()
            break
    else:
        if ". " in stripped and stripped.split(". ", 1)[0].isdigit():
            stripped = stripped.split(". ", 1)[1].strip()
        else:
            return None
    for separator in ("：", ":"):
        if separator in stripped:
            label, value = stripped.split(separator, 1)
            if value.strip():
                return label.strip()
    return None


def _heading_label(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("#"):
        return None
    title = stripped.lstrip("#").strip()
    for separator in ("：", ":"):
        if separator in title:
            label, value = title.split(separator, 1)
            if value.strip():
                return label.strip()
    return None


def _markdown_entries(markdown: str) -> list[set[str]]:
    entries: list[set[str]] = []
    current: set[str] | None = None
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            current = set()
            heading_label = _heading_label(stripped)
            if heading_label:
                current.add(heading_label)
            entries.append(current)
            continue
        label = _field_label(stripped)
        if label is None:
            continue
        if current is None:
            current = set()
            entries.append(current)
        current.add(label)
    return entries


def _missing_required_table_fields(
    markdown: str,
    required_fields: list[str],
) -> list[str]:
    missing: list[str] = []
    for table in _markdown_tables(markdown):
        header = table["header"]
        rows = table["rows"]
        for field in required_fields:
            if field not in header:
                if field not in missing:
                    missing.append(field)
                continue
            field_index = header.index(field)
            for row in rows:
                if field_index >= len(row) or not row[field_index].strip():
                    if field not in missing:
                        missing.append(field)
                    break
    return missing


def _missing_required_entry_fields(
    markdown: str,
    required_fields: list[str],
) -> list[str]:
    entries = _markdown_entries(markdown)
    if not entries:
        return required_fields
    missing: list[str] = []
    for entry in entries:
        for field in required_fields:
            if field not in entry and field not in missing:
                missing.append(field)
    return missing


def _profile_duplicate_names(markdown: str) -> list[str]:
    names: list[str] = []
    for table in _markdown_tables(markdown):
        header = table["header"]
        name_columns = [name for name in ("名称", "丹药名称") if name in header]
        if not name_columns:
            continue
        name_index = header.index(name_columns[0])
        for row in table["rows"]:
            if name_index < len(row) and row[name_index].strip():
                names.append(row[name_index].strip())
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            title = stripped.lstrip("#").strip()
            if title:
                names.append(title)
    duplicates: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)
    return duplicates


def _validate_profile_report(markdown: str, route: dict[str, Any]) -> ValidationResult:
    messages: list[str] = []
    blocking_messages: list[str] = []
    if _markdown_tables(markdown):
        for mode in _forbidden_table_modes(route):
            policy = _route_policy(route, "forbidden_output_mode_policy", "fail")
            _add_policy_message(
                messages,
                blocking_messages,
                f"forbidden output mode: {mode}",
                policy,
            )

    required_fields = _configured_list(_route_value(route, "required_fields"))
    if required_fields:
        policy = _route_policy(route, "missing_required_field_policy", "fail")
        if _markdown_tables(markdown):
            missing_fields = _missing_required_table_fields(markdown, required_fields)
        else:
            missing_fields = _missing_required_entry_fields(markdown, required_fields)
        for field in missing_fields:
            _add_policy_message(
                messages,
                blocking_messages,
                f"missing required field: {field}",
                policy,
            )

    duplicates = _profile_duplicate_names(markdown)
    if duplicates:
        policy = _route_policy(route, "duplicate_name_policy", "fail")
        for name in duplicates:
            _add_policy_message(
                messages,
                blocking_messages,
                f"duplicate name: {name}",
                policy,
            )

    return ValidationResult(ok=not blocking_messages, messages=messages)


def validate_report(
    report_path: Path | str,
    required_columns: list[str] | dict[str, Any] | None = None,
    forbidden_names: list[str] | None = None,
    *,
    route: dict[str, Any] | None = None,
    curation: dict[str, Any] | None = None,
) -> dict[str, Any] | ValidationResult:
    profile_route = route or curation
    if profile_route is None and isinstance(required_columns, dict):
        profile_route = required_columns
        required_columns = None
    if profile_route is not None:
        markdown = (
            report_path.read_text(encoding="utf-8")
            if isinstance(report_path, Path)
            else str(report_path)
        )
        return _validate_profile_report(markdown, profile_route)

    blocking_errors: list[dict[str, Any]] = []
    if not isinstance(report_path, Path):
        report_path = Path(report_path)
    if not report_path.exists():
        blocking_errors.append({"type": "missing_report", "path": str(report_path)})
        return {
            "passed": False,
            "blocking_errors": blocking_errors,
            "coverage_warnings": {},
        }

    markdown = report_path.read_text(encoding="utf-8")
    missing = _missing_columns(markdown, _configured_list(required_columns))
    if missing:
        blocking_errors.append(
            {"type": "missing_required_columns", "columns": missing}
        )
    found_forbidden = [
        name for name in _configured_list(forbidden_names) if name and name in markdown
    ]
    if found_forbidden:
        blocking_errors.append(
            {"type": "forbidden_names_present", "names": found_forbidden}
        )
    duplicate_names = _duplicate_names(markdown)
    if duplicate_names:
        blocking_errors.append(
            {"type": "duplicate_names", "duplicate_names": duplicate_names}
        )
    return {
        "passed": not blocking_errors,
        "blocking_errors": blocking_errors,
        "coverage_warnings": {},
    }


def validate_expected_present(
    confirmed_report: dict[str, Any],
    expected_config: dict[str, Any],
) -> dict[str, Any]:
    confirmed_names = {
        str(item.get("name"))
        for item in confirmed_report.get("items", [])
        if item.get("status", "confirmed") == "confirmed" and item.get("name")
    }
    missing = [
        name
        for name in _configured_list(expected_config.get("expected_present"))
        if name not in confirmed_names
    ]
    return {
        "passed": True,
        "blocking_errors": [],
        "coverage_warnings": {
            "expected_present_missing": missing,
        },
    }
