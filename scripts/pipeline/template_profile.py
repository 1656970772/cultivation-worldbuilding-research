from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from scripts.pipeline.config_loader import load_yaml


LOW_CONFIDENCE_QUESTIONS = [
    "这个模板最终应输出实体表、总览加卡片、案例集、流程链、决策链、关系链，还是职业闭环？",
    "哪些字段或小节必须出现，哪些输出形式禁止使用？",
]

FENCE_LABELS = {"", "markdown", "md"}


@dataclass(frozen=True)
class TemplateField:
    name: str
    source: str
    required: bool = True


@dataclass(frozen=True)
class TemplateSection:
    title: str
    kind: str
    fields: list[str]


@dataclass(frozen=True)
class TemplateTable:
    title: str
    columns: list[str]
    source: str
    rows: list[list[str]] = field(default_factory=list)


@dataclass(frozen=True)
class TemplateExample:
    title: str
    fields: dict[str, str]
    source: str
    text: str


@dataclass(frozen=True)
class TemplateProfile:
    template_path: str
    template_name: str
    template_kind: str
    report_shape: str
    sections: list[TemplateSection]
    tables: list[TemplateTable]
    fields: list[TemplateField]
    name_field: str
    examples: list[TemplateExample]
    confidence: float
    questions: list[str]
    forbidden_output_modes: list[str]


@dataclass(frozen=True)
class MarkdownSnapshot:
    headings: list[str]
    bullet_labels: list[str]
    tables: list[TemplateTable]
    recommended_tables: list[TemplateTable]
    table_sections: list[TemplateSection]
    card_sections: list[TemplateSection]
    body_text: str
    recommended_text: str
    examples: list[TemplateExample]


def load_shape_rules(presets_path: Path | None = None) -> dict[str, Any]:
    """Load template_shape_rules and shape_detection_keywords from framework-presets.yaml."""
    path = presets_path or Path(__file__).resolve().parents[2] / "assets" / "framework-presets.yaml"
    data = load_yaml(path)
    return {
        "parser": data.get("parser", {}),
        "template_catalog": data.get("template_catalog", {}),
        "template_shape_rules": data.get("template_shape_rules", {}),
        "shape_detection_keywords": data.get("shape_detection_keywords", {}),
        "validation_rules": data.get("validation_rules", {}),
    }


def build_template_profile(template_path: Path | str, presets_path: Path | None = None) -> TemplateProfile:
    """Read a template, parse Markdown structures, then classify report_shape from YAML rules."""
    path = Path(template_path)
    text = path.read_text(encoding="utf-8-sig")
    rules = load_shape_rules(presets_path)
    snapshot = _parse_markdown(text, rules)
    inferred_shape, inferred_confidence = _classify_shape(snapshot, rules)
    configured_shape = _configured_report_shape(path, rules)
    threshold = float(rules.get("validation_rules", {}).get("low_confidence_threshold", 0.6))
    if inferred_shape and inferred_confidence >= threshold:
        report_shape, confidence = inferred_shape, inferred_confidence
    elif configured_shape:
        report_shape, confidence = configured_shape, 1.0
    else:
        report_shape, confidence = inferred_shape, inferred_confidence

    tables = snapshot.recommended_tables or snapshot.tables
    field_tables = _field_source_tables(report_shape, tables)
    fields = _fields_from_tables(field_tables)
    questions = LOW_CONFIDENCE_QUESTIONS if confidence < threshold else []
    name_field = _detect_name_field(fields) if report_shape in {"entity_table", "overview_plus_cards"} else ""

    return TemplateProfile(
        template_path=str(path),
        template_name=path.stem,
        template_kind=_detect_template_kind(path.stem, snapshot.tables),
        report_shape=report_shape,
        sections=snapshot.table_sections + snapshot.card_sections,
        tables=tables,
        fields=fields,
        name_field=name_field,
        examples=snapshot.examples,
        confidence=confidence,
        questions=questions,
        forbidden_output_modes=_detect_forbidden_output_modes(text),
    )


def _parse_markdown(text: str, rules: dict[str, Any]) -> MarkdownSnapshot:
    lines = text.splitlines()
    headings = _extract_headings(lines)
    bullet_labels = _extract_bullet_labels(lines)
    parser_config = rules.get("parser", {})
    recommended_blocks = _extract_recommended_blocks(
        lines, _configured_terms(parser_config.get("recommended_structure_headings"))
    )
    recommended_text = "\n".join(recommended_blocks)
    recommended_tables = _extract_tables(recommended_text, "recommended_structure")
    body_tables = _extract_tables(text, "body")
    table_sections = _table_sections_from_tables(body_tables)
    card_sections = _extract_card_sections(lines, _card_heading_terms(rules))
    examples = _extract_examples(lines, recommended_tables or body_tables)
    return MarkdownSnapshot(
        headings=headings,
        bullet_labels=bullet_labels,
        tables=body_tables,
        recommended_tables=recommended_tables,
        table_sections=table_sections,
        card_sections=card_sections,
        body_text=text,
        recommended_text=recommended_text,
        examples=examples,
    )


def _extract_headings(lines: list[str]) -> list[str]:
    headings = []
    for line in lines:
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if match:
            headings.append(match.group(1).strip())
    return headings


def _extract_bullet_labels(lines: list[str]) -> list[str]:
    labels = []
    for line in lines:
        match = re.match(r"^\s*[-*+]\s*([^：:]+)[：:]", line)
        if match:
            labels.append(match.group(1).strip())
    return labels


def _extract_recommended_blocks(lines: list[str], recommended_headings: list[str]) -> list[str]:
    blocks = []
    current_heading = ""
    in_wanted_section = False
    in_fence = False
    fence_label = ""
    fence_lines: list[str] = []
    section_lines: list[str] = []

    for line in lines + ["# __END__"]:
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
        if heading and not in_fence:
            if in_wanted_section and section_lines:
                blocks.append("\n".join(section_lines))
            current_heading = heading.group(2).strip()
            in_wanted_section = _contains_any_text([current_heading], recommended_headings)
            section_lines = []
            continue

        fence = re.match(r"^\s*```\s*([A-Za-z0-9_-]*)\s*$", line)
        if fence:
            if not in_fence:
                in_fence = True
                fence_label = fence.group(1).lower()
                fence_lines = []
                continue
            if in_wanted_section and fence_label in FENCE_LABELS:
                blocks.append("\n".join(fence_lines))
            in_fence = False
            fence_label = ""
            fence_lines = []
            continue

        if in_fence:
            fence_lines.append(line)
        elif in_wanted_section:
            section_lines.append(line)

    return [block for block in blocks if block.strip()]


def _extract_tables(text: str, source: str) -> list[TemplateTable]:
    lines = text.splitlines()
    tables: list[TemplateTable] = []
    current_heading = ""
    for index, line in enumerate(lines):
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading:
            current_heading = heading.group(1).strip()
            continue
        if not _is_table_row(line):
            continue
        if index + 1 >= len(lines) or not _is_separator_row(lines[index + 1]):
            continue
        columns = _split_table_row(line)
        if columns:
            rows: list[list[str]] = []
            row_index = index + 2
            while row_index < len(lines) and _is_table_row(lines[row_index]):
                row = _split_table_row(lines[row_index])
                if row and not _is_separator_row(lines[row_index]):
                    rows.append(row)
                row_index += 1
            tables.append(TemplateTable(title=current_heading, columns=columns, source=source, rows=rows))
    return tables


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _is_separator_row(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def _split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _extract_card_sections(lines: list[str], card_headings: list[str]) -> list[TemplateSection]:
    sections: list[TemplateSection] = []
    current_title = ""
    current_fields: list[str] = []
    in_card = False

    for line in lines + ["# __END__"]:
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading:
            if in_card:
                sections.append(TemplateSection(current_title, "card", current_fields))
            current_title = heading.group(1).strip()
            current_fields = []
            in_card = _contains_any_text([current_title], card_headings)
            continue
        if in_card:
            label = re.match(r"^\s*[-*+]\s*([^：:]+)[：:]", line)
            if label:
                current_fields.append(label.group(1).strip())
    return sections


def _extract_examples(lines: list[str], tables: list[TemplateTable]) -> list[TemplateExample]:
    examples = _table_examples(tables)
    examples.extend(_card_examples(lines))
    return examples


def _table_examples(tables: list[TemplateTable]) -> list[TemplateExample]:
    examples: list[TemplateExample] = []
    for table in tables:
        if not table.columns:
            continue
        name_index = _name_column_index(table.columns)
        for row in table.rows:
            padded = row + [""] * max(0, len(table.columns) - len(row))
            fields = {
                column: value.strip()
                for column, value in zip(table.columns, padded)
                if value.strip()
            }
            title = padded[name_index].strip() if name_index < len(padded) else ""
            if not title or _looks_like_placeholder(title):
                continue
            text = "；".join(
                f"{column}：{value}"
                for column, value in zip(table.columns, padded)
                if value.strip()
            )
            examples.append(TemplateExample(title=title, fields=fields, source=table.source, text=text))
    return examples


def _card_examples(lines: list[str]) -> list[TemplateExample]:
    examples: list[TemplateExample] = []
    current_title = ""
    current_level = 0
    current_fields: dict[str, str] = {}
    current_lines: list[str] = []

    def flush() -> None:
        if not current_title or _looks_like_placeholder(current_title) or not current_fields:
            return
        text = "\n".join([current_title, *current_lines]).strip()
        examples.append(
            TemplateExample(
                title=_clean_example_title(current_title),
                fields=dict(current_fields),
                source="card",
                text=text,
            )
        )

    for line in lines + ["# __END__"]:
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            if current_title and level <= current_level:
                flush()
                current_fields = {}
                current_lines = []
            current_title = title
            current_level = level
            continue

        if not current_title:
            continue
        label = re.match(r"^\s*[-*+]\s*\*?\s*([^：:]+)[：:]\s*(.*?)\s*$", line)
        if label:
            key = label.group(1).strip().lstrip("*").strip()
            value = label.group(2).strip()
            if key and value:
                current_fields[key] = value
        if line.strip():
            current_lines.append(line.rstrip())

    return examples


def _name_column_index(columns: list[str]) -> int:
    for index, column in enumerate(columns):
        if "名称" in column or "名字" in column:
            return index
    return 0


def _clean_example_title(title: str) -> str:
    cleaned = re.sub(r"^案例\s*[0-9一二三四五六七八九十Nn]+\s*[：:]\s*", "", title).strip()
    return cleaned or title


def _looks_like_placeholder(value: str) -> bool:
    normalized = _normalize(value)
    instruction_terms = (
        "参考范围",
        "必须写什么",
        "适用范围",
        "前置声明",
        "推荐结构",
        "案例格式",
        "完整因果链案例",
        "完整人物关系变化链案例",
        "完整势力百科案例",
    )
    return (
        not normalized
        or any(term in value for term in instruction_terms)
        or "作品名" in value
        or "{名称}" in value
        or re.search(r"案例\s*[Nn]\s*[：:]", value) is not None
        or "因果链名称" in value
        or "示例" == normalized
        or normalized in {"案例n", "因果链名称"}
    )


def _table_sections_from_tables(tables: list[TemplateTable]) -> list[TemplateSection]:
    return [
        TemplateSection(table.title, "table", table.columns)
        for table in tables
        if table.title and not _is_module_table(table)
    ]


def _classify_shape(snapshot: MarkdownSnapshot, rules: dict[str, Any]) -> tuple[str, float]:
    shape_rules = rules.get("template_shape_rules", {})
    keywords = rules.get("shape_detection_keywords", {})
    scores = {shape: 0.0 for shape in shape_rules}

    for shape, config in shape_rules.items():
        features = _detect_features(snapshot, keywords.get(shape, {}))
        score = 0.0
        for feature in config.get("prefer_when", []):
            if features.get(feature):
                score += 2.0
        if config.get("requires_all") and all(features.get(item) for item in config["requires_all"]):
            score += 1.5
        if config.get("requires_any") and any(features.get(item) for item in config["requires_any"]):
            score += 1.0
        if config.get("table_column_min") and any(
            len(table.columns) >= int(config["table_column_min"]) for table in snapshot.recommended_tables
        ):
            score += 1.0
        score += _keyword_score(snapshot, keywords.get(shape, {}))
        scores[shape] = score

    if not scores:
        return "", 0.0
    best_shape = max(scores, key=scores.get)
    best_score = scores[best_shape]
    confidence = min(best_score / 5.0, 1.0)
    return best_shape, confidence


def _configured_report_shape(path: Path, rules: dict[str, Any]) -> str:
    expected_files = rules.get("template_catalog", {}).get("expected_files", {})
    if not isinstance(expected_files, dict):
        return ""
    template_dir = Path(str(rules.get("template_catalog", {}).get("template_dir", "")))
    if template_dir and not template_dir.is_absolute():
        template_dir = Path(__file__).resolve().parents[2] / template_dir
    in_configured_dir = template_dir.exists() and path.resolve().is_relative_to(template_dir.resolve())
    in_readme_catalog = (path.parent / "README.md").exists()
    if not in_configured_dir and not in_readme_catalog:
        return ""
    shape = expected_files.get(path.name, "")
    return str(shape) if shape and shape != "meta_rules" else ""


def _detect_features(snapshot: MarkdownSnapshot, keyword_config: dict[str, Any]) -> dict[str, bool]:
    tables = snapshot.tables + snapshot.recommended_tables
    text = "\n".join([snapshot.body_text, snapshot.recommended_text])
    has_keyword_heading = _keyword_matches(snapshot, keyword_config, "heading")
    has_keyword_bullet = _keyword_matches(snapshot, keyword_config, "bullets")
    has_keyword_column = _keyword_matches(snapshot, keyword_config, "columns")
    has_keyword_marker = _keyword_matches(snapshot, keyword_config, "markers")
    has_table_with_keyword_title = any(
        _contains_any_text([table.title], [str(value)])
        for table in tables
        for value in keyword_config.get("heading", [])
    )
    has_recommended_keyword_column = any(
        _contains_any_text(table.columns, [str(value)])
        for table in snapshot.recommended_tables
        for value in keyword_config.get("columns", [])
    )
    has_card = bool(snapshot.card_sections)
    return {
        "recommended_table_has_subject_name_field": bool(snapshot.recommended_tables and has_recommended_keyword_column),
        "overview_table_and_named_cards": has_table_with_keyword_title and has_card,
        "overview_table": has_table_with_keyword_title,
        "card_sections": has_card,
        "card_sections_without_overview": has_card and not has_table_with_keyword_title,
        "case_or_event_sections": has_keyword_heading,
        "case_sections": has_keyword_heading,
        "representative_events": has_keyword_heading,
        "narrative_log_entries": has_keyword_heading,
        "ordered_steps_or_chain_edges": bool(re.search(r"(?m)^\s*\d+\.", text)) or has_keyword_marker,
        "numbered_steps": bool(re.search(r"(?m)^\s*\d+\.", text)),
        "arrow_chain": has_keyword_marker,
        "phase_table": has_keyword_heading or has_keyword_column,
        "choice_or_condition_consequence_sections": has_keyword_heading or has_keyword_bullet,
        "decision_nodes": has_keyword_heading,
        "option_tables": has_keyword_heading or has_keyword_column,
        "condition_consequence_pairs": has_keyword_bullet,
        "node_edge_or_relation_sections": has_keyword_heading or has_keyword_column,
        "node_edge_table": has_keyword_column,
        "relation_matrix": has_keyword_heading,
        "upstream_downstream_edges": has_keyword_heading or has_keyword_column,
        "profession_inputs_outputs_growth_loop": has_keyword_heading or has_keyword_bullet,
        "input_output_sections": has_keyword_heading or has_keyword_bullet,
        "workflow_loop": has_keyword_heading,
        "growth_path": has_keyword_heading or has_keyword_bullet,
    }


def _keyword_matches(snapshot: MarkdownSnapshot, keyword_config: dict[str, Any], key: str) -> bool:
    channels = {
        "heading": snapshot.headings,
        "columns": [column for table in snapshot.tables + snapshot.recommended_tables for column in table.columns],
        "bullets": snapshot.bullet_labels,
        "markers": [snapshot.body_text, snapshot.recommended_text],
    }
    values = keyword_config.get(key, [])
    return isinstance(values, list) and _contains_any_text(channels.get(key, []), [str(value) for value in values])


def _keyword_score(snapshot: MarkdownSnapshot, keyword_config: dict[str, Any]) -> float:
    score = 0.0
    headings = snapshot.headings + [table.title for table in snapshot.tables + snapshot.recommended_tables]
    columns = [column for table in snapshot.tables + snapshot.recommended_tables for column in table.columns]
    channels = {
        "heading": headings,
        "columns": columns,
        "bullets": snapshot.bullet_labels,
        "markers": [snapshot.body_text, snapshot.recommended_text],
    }
    for key, values in keyword_config.items():
        haystack = channels.get(key, [])
        if not isinstance(values, list):
            continue
        matches = sum(1 for value in values if _contains_any_text(haystack, [str(value)]))
        if matches:
            score += min(matches, 3) * 0.5
    return score


def _configured_terms(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _card_heading_terms(rules: dict[str, Any]) -> list[str]:
    parser_terms = _configured_terms(rules.get("parser", {}).get("card_section_headings"))
    if parser_terms:
        return parser_terms
    keywords = rules.get("shape_detection_keywords", {})
    return _configured_terms(keywords.get("overview_plus_cards", {}).get("heading")) + _configured_terms(
        keywords.get("cards_only", {}).get("heading")
    )


def _fields_from_tables(tables: list[TemplateTable]) -> list[TemplateField]:
    if not tables:
        return []
    return [TemplateField(column, tables[0].source) for column in tables[0].columns]


def _field_source_tables(report_shape: str, tables: list[TemplateTable]) -> list[TemplateTable]:
    if report_shape == "overview_plus_cards":
        overview_tables = [table for table in tables if not _is_module_table(table)]
        if overview_tables:
            return overview_tables
    return tables


def _detect_name_field(fields: list[TemplateField]) -> str:
    for field in fields:
        if "名称" in field.name:
            return field.name
    return fields[0].name if fields else ""


def _detect_template_kind(template_name: str, tables: list[TemplateTable]) -> str:
    if any(_is_module_table(table) for table in tables):
        return "module_table"
    return template_name.removesuffix("模板").removesuffix("分析")


def _is_module_table(table: TemplateTable) -> bool:
    required_columns = {"模块", "必写内容", "项目用途"}
    return required_columns.issubset({_normalize(column) for column in table.columns})


def _detect_forbidden_output_modes(text: str) -> list[str]:
    modes = []
    aliases = {"表格": "table", "卡片": "cards"}
    for mode in ("表格", "卡片", "自由发挥"):
        if re.search(rf"(不要|禁止|不应)[^。\n]*{re.escape(mode)}", text):
            modes.append(mode)
            alias = aliases.get(mode)
            if alias:
                modes.append(alias)
    return modes


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    normalized = _normalize(text)
    return any(_normalize(needle) in normalized for needle in needles)


def _contains_any_text(values: list[str], needles: list[str]) -> bool:
    normalized_values = [_normalize(value) for value in values]
    return any(_normalize(needle) in value for needle in needles for value in normalized_values)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()
