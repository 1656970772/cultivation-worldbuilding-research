from pathlib import Path
from typing import Any, Callable


ProfileRenderer = Callable[[str, list[dict[str, Any]], dict[str, Any]], list[str]]


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


def _validate_confirmed_source_spans(items: list[dict[str, Any]]) -> None:
    for item in items:
        source_spans = item.get("source_spans")
        if not isinstance(source_spans, list) or not source_spans:
            raise ValueError(
                f"confirmed item missing source_spans: {item.get('name', '')}"
            )


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


def _entry_name(entry: dict[str, Any], unknown_text: str = "") -> str:
    name = entry.get("name")
    if name not in (None, ""):
        return str(name)
    fields = entry.get("fields", {})
    if isinstance(fields, dict):
        for key in ("名称", "事件", "阶段", "节点", "职业/技艺"):
            value = fields.get(key)
            if value not in (None, ""):
                return str(value)
    return unknown_text


def _field_lines(entry: dict[str, Any], unknown_text: str = "") -> list[str]:
    fields = entry.get("fields", {})
    if not isinstance(fields, dict):
        return []
    return [
        f"- {key}：{_markdown_cell(value, unknown_text)}"
        for key, value in fields.items()
    ]


def _profile_table_lines(entries: list[dict[str, Any]], unknown_text: str) -> list[str]:
    columns = _derive_columns(entries)
    if "名称" not in columns:
        columns = ["名称"] + columns
    table_entries: list[dict[str, Any]] = []
    for entry in entries:
        fields = entry.get("fields", {})
        if not isinstance(fields, dict):
            fields = {}
        fields = {"名称": _entry_name(entry, unknown_text), **fields}
        table_entries.append({**entry, "fields": fields})
    return _table_lines(table_entries, columns, unknown_text)


def _forbids_table(route: dict[str, Any]) -> bool:
    modes = _configured_list(route.get("forbidden_output_modes"))
    return any("table" in mode.lower() or "表格" in mode for mode in modes)


def _block_names(route: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for block in route.get("render_blocks", []):
        if isinstance(block, dict):
            name = block.get("name") or block.get("id") or block.get("block")
        else:
            name = block
        if name not in (None, ""):
            names.append(str(name))
    return names


def _render_cards_section(
    heading: str,
    entries: list[dict[str, Any]],
    unknown_text: str,
) -> list[str]:
    lines = ["", heading]
    for entry in entries:
        lines.extend(["", f"### {_entry_name(entry, unknown_text)}"])
        lines.extend(_field_lines(entry, unknown_text))
    return lines


def _render_entity_table(
    title: str,
    entries: list[dict[str, Any]],
    route: dict[str, Any],
) -> list[str]:
    unknown_text = str(route.get("unknown_text", ""))
    if _forbids_table(route):
        return _render_cards_section("## 条目详情", entries, unknown_text)
    return ["", "## 实体表", *_profile_table_lines(entries, unknown_text)]


def _render_overview_plus_cards(
    title: str,
    entries: list[dict[str, Any]],
    route: dict[str, Any],
) -> list[str]:
    unknown_text = str(route.get("unknown_text", ""))
    lines: list[str] = []
    if not _forbids_table(route):
        lines.extend(["", "## 总览", *_profile_table_lines(entries, unknown_text)])
    lines.extend(_render_cards_section("## 条目详情", entries, unknown_text))
    return lines


def _render_cards_only(
    title: str,
    entries: list[dict[str, Any]],
    route: dict[str, Any],
) -> list[str]:
    return _render_cards_section("## 条目详情", entries, str(route.get("unknown_text", "")))


def _render_case_collection(
    title: str,
    entries: list[dict[str, Any]],
    route: dict[str, Any],
) -> list[str]:
    unknown_text = str(route.get("unknown_text", ""))
    blocks = _block_names(route)
    lines: list[str] = []
    if not blocks or "case_index" in blocks or "case_cards" in blocks:
        lines.extend(["", "## 案例索引"])
        lines.extend(f"- {_entry_name(entry, unknown_text)}" for entry in entries)
    if not blocks or "cases" in blocks or "case_cards" in blocks:
        lines.extend(_render_cards_section("## 案例详情", entries, unknown_text))
    return lines


def _render_chain(
    heading: str,
    entries: list[dict[str, Any]],
    route: dict[str, Any],
) -> list[str]:
    return _render_cards_section(heading, entries, str(route.get("unknown_text", "")))


def _render_process_chain(
    title: str,
    entries: list[dict[str, Any]],
    route: dict[str, Any],
) -> list[str]:
    return _render_chain("## 流程步骤", entries, route)


def _render_decision_chain(
    title: str,
    entries: list[dict[str, Any]],
    route: dict[str, Any],
) -> list[str]:
    return _render_chain("## 决策节点", entries, route)


def _render_relationship_chain(
    title: str,
    entries: list[dict[str, Any]],
    route: dict[str, Any],
) -> list[str]:
    return _render_chain("## 关系链", entries, route)


def _render_profession_workflow(
    title: str,
    entries: list[dict[str, Any]],
    route: dict[str, Any],
) -> list[str]:
    return _render_chain("## 职业闭环", entries, route)


RENDER_STRATEGIES: dict[str, ProfileRenderer] = {
    "entity_table": _render_entity_table,
    "overview_plus_cards": _render_overview_plus_cards,
    "cards_only": _render_cards_only,
    "case_collection": _render_case_collection,
    "process_chain": _render_process_chain,
    "decision_chain": _render_decision_chain,
    "relationship_chain": _render_relationship_chain,
    "profession_workflow": _render_profession_workflow,
}


def render_profile_report(
    title: str,
    entries: list[dict[str, Any]],
    route: dict[str, Any] | None = None,
) -> str:
    route = route if isinstance(route, dict) else {}
    shape = str(route.get("report_shape") or route.get("render_strategy") or "cards_only")
    renderer = RENDER_STRATEGIES.get(shape)
    lines = [f"# {title}"]
    if renderer is None:
        lines.append(f"> 警告：未知报告形态 `{shape}`，已使用 cards_only 渲染。")
        renderer = _render_cards_only
    lines.extend(renderer(title, entries, route))
    return "\n".join(lines).rstrip() + "\n"


def _strategy_route(
    report_config: dict[str, Any],
    route_config: dict[str, Any] | None,
    default_config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    shape = _config_value("report_shape", report_config, route_config, default_config)
    strategy = _config_value(
        "render_strategy",
        report_config,
        route_config,
        default_config,
    )
    if not shape and not strategy:
        return None
    route: dict[str, Any] = {}
    for config in (default_config, route_config, report_config):
        if isinstance(config, dict):
            route.update(config)
            route.update(_nested_output(config))
    return route


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
    confirmed_report: dict[str, Any] | None = None,
    output_path: Path | None = None,
    route_config: dict[str, Any] | None = None,
    default_config: dict[str, Any] | None = None,
    *,
    title: str | None = None,
    entries: list[dict[str, Any]] | None = None,
    route: dict[str, Any] | None = None,
) -> str | None:
    if title is not None or entries is not None or route is not None:
        return render_profile_report(title or "", entries or [], route)
    if confirmed_report is None or output_path is None:
        raise TypeError("render_report requires confirmed_report and output_path")
    report_config = confirmed_report.get("report_config", {})
    items = _confirmed_items(confirmed_report)
    _validate_confirmed_source_spans(items)
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

    title_text = _report_title(confirmed_report, route_config, default_config)
    strategy_route = _strategy_route(report_config, route_config, default_config)
    if strategy_route is None:
        lines = [f"# {title_text}", ""]
        lines.extend(_table_lines(items, columns, unknown_text))
    else:
        strategy_route.setdefault("unknown_text", unknown_text)
        lines = render_profile_report(title_text, items, strategy_route).rstrip().split("\n")
    if evidence_in_final_report:
        lines.extend(_evidence_lines(items, unknown_text))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
