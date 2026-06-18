from pathlib import Path

from scripts.pipeline.extraction_prompt import (
    build_example_specs,
    build_prompt_description,
)
from scripts.pipeline.template_profile import build_template_profile


def test_table_rows_become_langextract_example_specs(tmp_path: Path):
    template = tmp_path / "丹药分析模板.md"
    template.write_text(
        """# 丹药分析模板

## 推荐结构

| 丹药名称 | 稀有度 | 功效 |
| --- | --- | --- |
| 聚气丹 | 常见 | 增加真气 |
| 筑基丹 | 稀有 | 辅助突破筑基 |
""",
        encoding="utf-8",
    )
    profile = build_template_profile(template)

    examples = build_example_specs(profile)

    assert [example.extractions[0].extraction_text for example in examples] == ["聚气丹", "筑基丹"]
    assert examples[0].extractions[0].extraction_class == "丹药"
    assert examples[0].extractions[0].attributes == {
        "丹药名称": "聚气丹",
        "稀有度": "常见",
        "功效": "增加真气",
    }


def test_card_examples_become_langextract_example_specs(tmp_path: Path):
    template = tmp_path / "功法术法神通模板.md"
    template.write_text(
        """# 功法术法神通模板

## 推荐结构

### 基础吐纳法

- 类别：功法
- 功效：辅助炼气期吸纳灵气
""",
        encoding="utf-8",
    )
    profile = build_template_profile(template)

    [example] = build_example_specs(profile)

    assert example.extractions[0].extraction_text == "基础吐纳法"
    assert example.extractions[0].extraction_class == "功法术法神通"
    assert example.extractions[0].attributes["类别"] == "功法"


def test_prompt_description_uses_profile_fields_and_meta_rules(tmp_path: Path):
    template = tmp_path / "丹药分析模板.md"
    template.write_text(
        """# 丹药分析模板

## 推荐结构

| 丹药名称 | 功效 |
| --- | --- |
| 聚气丹 | 增加真气 |
""",
        encoding="utf-8",
    )
    profile = build_template_profile(template)

    prompt = build_prompt_description(profile, readme_text="禁止编造；无依据写原文未说明。")

    assert "丹药名称" in prompt
    assert "功效" in prompt
    assert "禁止编造" in prompt
    assert "char_interval" in prompt
