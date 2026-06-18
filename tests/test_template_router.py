from pathlib import Path

import pytest

from scripts.pipeline.config_loader import load_yaml
from scripts.pipeline.template_router import route_template


ROOT = Path(__file__).resolve().parents[1]


def test_routes_registry_direct_hit_without_reading_template(tmp_path):
    registry = tmp_path / "template-registry.yaml"
    registry.write_text(
        "\n".join(
            [
                "templates:",
                "  丹药分析模板.md:",
                "    primary_mode: entity",
                "    secondary_modes: [economy]",
                "    subject_type: 丹药",
                '    output_name_pattern: "{work_title}registry.md"',
                "    required_columns: [丹药名称]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    route = route_template(registry, tmp_path / "丹药分析模板.md", "")

    assert route["primary_mode"] == "entity"
    assert route["secondary_modes"] == ["economy"]
    assert route["subject_type"] == "丹药"
    assert route["output_name_pattern"] == "{work_title}registry.md"
    assert route["required_columns"] == ["丹药名称"]
    assert route["template_name"] == "丹药分析模板.md"


def test_routes_registry_request_match_when_template_name_misses(tmp_path):
    registry = tmp_path / "template-registry.yaml"
    registry.write_text(
        "\n".join(
            [
                "templates:",
                "  丹药分析模板.md:",
                "    primary_mode: entity",
                "    subject_type: 丹药",
                '    output_name_pattern: "{work_title}matched.md"',
                "    required_columns: [丹药名称, 功效]",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    route = route_template(registry, tmp_path / "未知模板.md", "请使用丹药分析模板.md 梳理设定")

    assert route["primary_mode"] == "entity"
    assert route["subject_type"] == "丹药"
    assert route["output_name_pattern"] == "{work_title}matched.md"
    assert route["required_columns"] == ["丹药名称", "功效"]
    assert route["template_name"] == "丹药分析模板.md"


def test_routes_missing_template_uses_generic_fallback(tmp_path):
    registry = tmp_path / "template-registry.yaml"
    registry.write_text("templates: {}\n", encoding="utf-8")

    route = route_template(registry, tmp_path / "缺失分析模板.md", "")

    assert route["primary_mode"] == "generic"
    assert route["required_columns"] == []
    assert route["template_profile"] == {}
    assert route["template_name"] == "缺失分析模板.md"


def test_route_output_pattern_rejects_unknown_placeholder(tmp_path):
    registry = tmp_path / "template-registry.yaml"
    registry.write_text("templates: {}\n", encoding="utf-8")
    presets = tmp_path / "framework-presets.yaml"
    presets.write_text(
        "\n".join(
            [
                "route_defaults:",
                '  output_name_pattern: "{work_title}{unknown}.md"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="output_name_pattern supports placeholders: work_title, template_subject, subject_type",
    ):
        route_template(registry, tmp_path / "缺失分析模板.md", "", presets_path=presets)


def test_route_output_pattern_rejects_nested_format_spec_placeholder(tmp_path):
    registry = tmp_path / "template-registry.yaml"
    registry.write_text("templates: {}\n", encoding="utf-8")
    presets = tmp_path / "framework-presets.yaml"
    presets.write_text(
        "\n".join(
            [
                "route_defaults:",
                '  output_name_pattern: "{work_title:{width}}.md"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="output_name_pattern supports placeholders"):
        route_template(registry, tmp_path / "缺失分析模板.md", "", presets_path=presets)


def test_routes_template_from_profile_when_registry_has_no_active_template(tmp_path):
    registry = tmp_path / "template-registry.yaml"
    registry.write_text("templates: {}\n", encoding="utf-8")
    template = tmp_path / "丹药分析模板.md"
    template.write_text(
        """# 丹药分析模板

## 推荐结构

| 丹药名称 | 稀有度 | 功效 | 来源 | 证据 |
| --- | --- | --- | --- | --- |
| 示例 | 常见 | 增进修为 | 原文 | 第一章 |
""",
        encoding="utf-8",
    )

    route = route_template(registry, template, "")

    assert route["primary_mode"] == "entity"
    assert route["subject_type"] == "丹药"
    assert route["output_name_pattern"] == "{work_title}丹药分析.md"
    assert route["report_title_pattern"] == "《{work_title}》{subject_type}分析"
    assert route["required_columns"] == ["丹药名称", "稀有度", "功效", "来源", "证据"]
    assert route["template_name"] == "丹药分析模板.md"
    assert route["template_profile"]["report_shape"] == "entity_table"


@pytest.mark.parametrize("content", ["false", "0", "null", ""])
def test_load_yaml_rejects_falsey_non_mapping_root(tmp_path, content):
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="YAML root must be a mapping"):
        load_yaml(path)
