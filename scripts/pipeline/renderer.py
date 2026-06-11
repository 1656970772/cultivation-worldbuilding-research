from pathlib import Path
from typing import Any


def _configured_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _nested_output(config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    output = config.get("output", {})
    return output if isinstance(output, dict) else {}


def _config_value(key: str, *configs: dict[str, Any] | None) -> Any:
    for config in configs:
        if not isinstance(config, dict):
            continue
        if key in config:
            return config[key]
        output = _nested_output(config)
        if key in output:
            return output[key]
    return None


def _confirmed_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in report.get("items", [])
        if item.get("status", "confirmed") == "confirmed"
    ]


def _derive_columns(items: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    for item in items:
        fields = item.get("fields", {})
        if not isinstance(fields, dict):
            continue
        for key in fields:
            if key not in columns:
                columns.append(str(key))
    return columns


def _format_configured_text(template: str, work_title: str, subject_type: str) -> str:
    return template.format(work_title=work_title, subject_type=subject_type)


def _report_title(
    report: dict[str, Any],
    route_config: dict[str, Any] | None,
    default_config: dict[str, Any] | None,
) -> str:
    report_config = report.get("report_config", {})
    work_title = str(report.get("work_title", ""))
    subject_type = str(
        _config_value("subject_type", report_config, route_config, default_config) or ""
    )
    title = _config_value("report_title", report_config, route_config, default_config)
    if title:
        return str(title)
    pattern = _config_value(
        "report_title_pattern",
        report_config,
        route_config,
        default_config,
    )
    if pattern:
        return _format_configured_text(str(pattern), work_title, subject_type)
    return work_title


def _markdown_cell(value: Any, unknown_text: str) -> str:
    text = unknown_text if value in (None, "") else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _table_lines(
    items: list[dict[str, Any]],
    columns: list[str],
    unknown_text: str,
) -> list[str]:
    if not columns:
        return []
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for item in items:
        fields = item.get("fields", {})
        if not isinstance(fields, dict):
            fields = {}
        values = [_markdown_cell(fields.get(column), unknown_text) for column in columns]
        lines.append("| " + " | ".join(values) + " |")
    return lines


def _evidence_lines(items: list[dict[str, Any]], unknown_text: str) -> list[str]:
    lines: list[str] = ["", "## 证据"]
    for item in items:
        name = str(item.get("name", unknown_text))
        for span in item.get("source_spans", []):
            if not isinstance(span, dict):
                continue
            line = span.get("line", unknown_text)
            segment_id = span.get("segment_id", unknown_text)
            summary = _markdown_cell(span.get("summary"), unknown_text)
            lines.append(f"- {name}（{segment_id}:{line}）：{summary}")
    return lines


def render_report(
    confirmed_report: dict[str, Any],
    output_path: Path,
    route_config: dict[str, Any] | None = None,
    default_config: dict[str, Any] | None = None,
) -> None:
    report_config = confirmed_report.get("report_config", {})
    items = _confirmed_items(confirmed_report)
    unknown_text = str(
        _config_value("unknown_text", report_config, route_config, default_config) or ""
    )
    columns = _configured_list(
        _config_value("required_columns", report_config, route_config, default_config)
    )
    if not columns:
        columns = _derive_columns(items)
    evidence_in_final_report = bool(
        _config_value(
            "evidence_in_final_report",
            report_config,
            route_config,
            default_config,
        )
    )

    lines = [f"# {_report_title(confirmed_report, route_config, default_config)}", ""]
    lines.extend(_table_lines(items, columns, unknown_text))
    if evidence_in_final_report:
        lines.extend(_evidence_lines(items, unknown_text))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
