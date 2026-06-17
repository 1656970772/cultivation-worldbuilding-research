from pathlib import Path

from scripts.pipeline.template_profile import build_template_profile


ROOT = Path(__file__).resolve().parents[1]
PRESETS = ROOT / "assets" / "framework-presets.yaml"


def write_template(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_weapon_profile_prefers_recommended_structure_code_block(tmp_path):
    template = write_template(
        tmp_path,
        "武器分析模板.md",
        """# 武器分析模板

## 推荐结构

```markdown
| 武器名称 | 形制 | 稀有度 | 功效 | 用途 | 制作材料 | 制作/获得方式 | 使用者/势力 | 限制/损耗 | 适用境界 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 示例 | 剑 | 稀有 | 破防 | 战斗 | 玄铁 | 炼制 | 青云宗 | 耗灵 | 筑基 |
```

## 字段说明

正文里的表格不应覆盖推荐结构。

| 字段 | 说明 |
| --- | --- |
| 证据 | 原文依据 |
""",
    )

    profile = build_template_profile(template, PRESETS)

    assert profile.template_name == "武器分析模板"
    assert profile.report_shape == "entity_table"
    assert [field.name for field in profile.fields] == [
        "武器名称",
        "形制",
        "稀有度",
        "功效",
        "用途",
        "制作材料",
        "制作/获得方式",
        "使用者/势力",
        "限制/损耗",
        "适用境界",
    ]
    assert profile.name_field == "武器名称"
    assert profile.tables[0].source == "recommended_structure"
    assert profile.confidence >= 0.8
    assert profile.questions == []


def test_overview_plus_cards_profile_from_module_table(tmp_path):
    template = write_template(
        tmp_path,
        "势力模块模板.md",
        """# 势力模块模板

## 模块清单

| 模块 | 必写内容 | 项目用途 |
| --- | --- | --- |
| 势力总览 | 势力名称、类型、参考用途、证据 | 总览 |

## 势力总览

| 势力名称 | 类型 | 参考用途 | 证据 |
| --- | --- | --- | --- |
| 青云宗 | 宗门 | 势力总览 | 第三章 |

## 设定卡：{名称}

- 类型：宗门
- 来源：正文
- 证据：章节锚点
""",
    )

    profile = build_template_profile(template, PRESETS)

    assert profile.template_kind == "module_table"
    assert profile.report_shape == "overview_plus_cards"
    assert profile.name_field == "势力名称"
    assert [table.title for table in profile.tables] == ["模块清单", "势力总览"]
    assert [(section.title, section.kind, section.fields) for section in profile.sections] == [
        ("势力总览", "table", ["势力名称", "类型", "参考用途", "证据"]),
        ("设定卡：{名称}", "card", ["类型", "来源", "证据"]),
    ]


def test_process_and_decision_profiles_are_not_forced_to_tables(tmp_path):
    process_template = write_template(
        tmp_path,
        "角色AI行为参考模板.md",
        """# 角色AI行为参考模板

## 行为参考流程

1. 观察局势：记录环境与敌我状态
2. 选择动作：按倾向与约束筛选行为
3. 执行反馈：记录结果与下一轮状态

也可写作 观察 -> 选择 -> 执行。
""",
    )
    decision_template = write_template(
        tmp_path,
        "角色决策链模板.md",
        """# 角色决策链模板

## 决策节点

- 条件：敌方压制
- 代价：消耗灵力
- 后果：拉开距离
- 约束：不可伤及同门
""",
    )

    process_profile = build_template_profile(process_template, PRESETS)
    decision_profile = build_template_profile(decision_template, PRESETS)

    assert process_profile.report_shape == "process_chain"
    assert process_profile.tables == []
    assert process_profile.name_field == ""
    assert decision_profile.report_shape == "decision_chain"
    assert decision_profile.tables == []
    assert decision_profile.name_field == ""


def test_low_confidence_profile_asks_required_questions(tmp_path):
    template = write_template(
        tmp_path,
        "自由摘录模板.md",
        """# 自由摘录模板

请根据原文整理有价值的信息，不要自由发挥。
""",
    )

    profile = build_template_profile(template, PRESETS)

    assert profile.confidence < 0.6
    assert profile.questions == [
        "这个模板最终应输出实体表、总览加卡片、案例集、流程链、决策链、关系链，还是职业闭环？",
        "哪些字段或小节必须出现，哪些输出形式禁止使用？",
    ]
    assert profile.forbidden_output_modes == ["自由发挥"]


def test_parser_uses_custom_preset_labels_for_recommended_blocks_and_cards(tmp_path):
    presets = write_template(
        tmp_path,
        "custom-presets.yaml",
        """parser:
  recommended_structure_headings: [蓝图]
  card_section_headings: [条目页]
template_shape_rules:
  overview_plus_cards:
    prefer_when: [overview_table_and_named_cards]
    requires_all: [overview_table, card_sections]
shape_detection_keywords:
  overview_plus_cards:
    heading: [概览, 条目页]
    columns: [对象名称, 类型, 证据]
validation_rules:
  low_confidence_threshold: 0.6
""",
    )
    template = write_template(
        tmp_path,
        "自定义模板.md",
        """# 自定义模板

## 蓝图

```md
| 对象名称 | 类型 | 证据 |
| --- | --- | --- |
| 示例 | 条目 | 第一章 |
```

## 概览

| 对象名称 | 类型 | 证据 |
| --- | --- | --- |
| 示例 | 条目 | 第一章 |

## 条目页：{对象名称}

- 类型：条目
- 证据：第一章
""",
    )

    profile = build_template_profile(template, presets)

    assert profile.report_shape == "overview_plus_cards"
    assert profile.tables[0].source == "recommended_structure"
    assert ("条目页：{对象名称}", "card", ["类型", "证据"]) in [
        (section.title, section.kind, section.fields) for section in profile.sections
    ]
