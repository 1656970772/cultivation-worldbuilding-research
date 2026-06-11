from pathlib import Path
from typing import Any


def _configured_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _table_headers(markdown: str) -> list[list[str]]:
    headers: list[list[str]] = []
    lines = markdown.splitlines()
    for index, line in enumerate(lines[:-1]):
        stripped = line.strip()
        separator = lines[index + 1].strip()
        if not _is_table_row(stripped) or not _is_separator_row(separator):
            continue
        headers.append(_table_cells(stripped))
    return headers


def _missing_columns(markdown: str, required_columns: list[str]) -> list[str]:
    if not required_columns:
        return []
    headers = _table_headers(markdown)
    for header in headers:
        if all(column in header for column in required_columns):
            return []
    present_columns = {column for header in headers for column in header}
    return [column for column in required_columns if column not in present_columns]


def _is_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def _table_cells(line: str) -> list[str]:
    return [cell.strip().replace("\\|", "|") for cell in line.strip("|").split("|")]


def _is_separator_row(line: str) -> bool:
    if not _is_table_row(line):
        return False
    cells = _table_cells(line)
    return bool(cells) and all(set(cell) <= {"-", ":"} and "-" in cell for cell in cells)


def validate_report(
    report_path: Path,
    required_columns: list[str],
    forbidden_names: list[str] | None = None,
) -> dict[str, Any]:
    blocking_errors: list[dict[str, Any]] = []
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
