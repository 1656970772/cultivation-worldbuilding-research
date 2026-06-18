from pathlib import Path

import pytest

from scripts.pipeline.analysis_framework import build_framework
from scripts.pipeline.config_loader import load_yaml
from scripts.pipeline.template_profile import build_template_profile


TEMPLATE_DIR = Path("E:/AI_Projects/CultivationWorld/docs/世界观参考/模板")
PRESETS = Path("assets/framework-presets.yaml")

VALID_SHAPES = {
    "entity_table",
    "overview_plus_cards",
    "cards_only",
    "case_collection",
    "process_chain",
    "decision_chain",
    "relationship_chain",
    "profession_workflow",
}

EXPECTED_SHAPES = {
    "丹药分析模板.md": "entity_table",
    "材料分析模板.md": "entity_table",
    "法宝分析模板.md": "entity_table",
    "武器分析模板.md": "entity_table",
    "妖兽分析模板.md": "entity_table",
    "灵根体质血脉模板.md": "entity_table",
    "功法术法神通模板.md": "cards_only",
    "记忆情绪与执念模板.md": "cards_only",
    "事件因果链（长程因果图）模板.md": "process_chain",
    "境界提升与功法分析模板.md": "process_chain",
    "角色修炼历程模板.md": "process_chain",
    "人物关系与事件分析模板.md": "relationship_chain",
    "妖兽与修士关系分析模板.md": "relationship_chain",
    "角色AI行为参考模板.md": "decision_chain",
    "炼丹师模板.md": "profession_workflow",
    "炼器师模板.md": "profession_workflow",
    "阵法师模板.md": "profession_workflow",
    "符师模板.md": "profession_workflow",
    "拍卖坊市与交易模板.md": "case_collection",
    "冲突事件分析模板.md": "case_collection",
    "相遇剧情与对话设计模板.md": "case_collection",
    "动态事件与机会点模板.md": "case_collection",
    "秘境遗迹与机缘模板.md": "case_collection",
    "夺舍设定分析模板.md": "case_collection",
    "邪修分析模板.md": "case_collection",
    "世界观设定模板.md": "overview_plus_cards",
    "势力设定模板.md": "overview_plus_cards",
    "建筑设施与场所功能模板.md": "overview_plus_cards",
    "世界状态与灾变模板.md": "overview_plus_cards",
    "散修生存方式模板.md": "overview_plus_cards",
    "宗门任务体系模板.md": "overview_plus_cards",
    "信息传播与情报模板.md": "overview_plus_cards",
    "有限视角与叙事日志模板.md": "overview_plus_cards",
    "战斗与保命机制模板.md": "overview_plus_cards",
    "物资产出与消耗模板.md": "overview_plus_cards",
    "出门游历流程分析模板.md": "overview_plus_cards",
    "时间行动与事件耗时模板.md": "overview_plus_cards",
}


def require_template(name: str) -> Path:
    path = TEMPLATE_DIR / name
    if not path.exists():
        pytest.skip(f"template not found: {path}")
    return path


def test_real_weapon_template_uses_recommended_structure():
    profile = build_template_profile(require_template("武器分析模板.md"))

    assert profile.report_shape == "entity_table"
    assert profile.name_field
    assert profile.fields
    assert profile.confidence >= 0.6


def test_real_overview_plus_cards_template():
    candidates = ["势力设定模板.md", "世界观设定模板.md"]
    path = next((TEMPLATE_DIR / name for name in candidates if (TEMPLATE_DIR / name).exists()), None)
    if path is None:
        pytest.skip("overview plus cards template not found")

    profile = build_template_profile(path)

    assert profile.report_shape in VALID_SHAPES
    assert profile.fields or profile.sections


def test_real_card_template_for_profession_or_method():
    candidates = ["功法术法神通模板.md", "炼丹师模板.md"]
    path = next((TEMPLATE_DIR / name for name in candidates if (TEMPLATE_DIR / name).exists()), None)
    if path is None:
        pytest.skip("card template not found")

    profile = build_template_profile(path)

    assert profile.report_shape in {"cards_only", "overview_plus_cards", "profession_workflow"}
    assert profile.fields or profile.sections


def test_real_chain_template_for_event_or_ai():
    event_path = require_template("事件因果链（长程因果图）模板.md")
    ai_path = require_template("角色AI行为参考模板.md")

    event_profile = build_template_profile(event_path)
    ai_profile = build_template_profile(ai_path)

    assert event_profile.report_shape in VALID_SHAPES
    assert ai_profile.report_shape in VALID_SHAPES
    assert event_profile.confidence >= 0.6
    assert ai_profile.confidence >= 0.6


def test_expected_files_config_matches_catalog_table():
    expected_files = load_yaml(PRESETS)["template_catalog"]["expected_files"]
    catalog_shapes = {name: shape for name, shape in expected_files.items() if shape != "meta_rules"}

    assert expected_files["README.md"] == "meta_rules"
    assert catalog_shapes == EXPECTED_SHAPES
    assert all(shape in VALID_SHAPES | {"meta_rules"} for shape in expected_files.values())


def test_real_templates_resolve_to_a_valid_shape():
    if not TEMPLATE_DIR.exists():
        pytest.skip(f"template dir not found: {TEMPLATE_DIR}")

    for name in EXPECTED_SHAPES:
        path = TEMPLATE_DIR / name
        if not path.exists():
            # External template directories may be partial on local machines.
            continue
        profile = build_template_profile(path, presets_path=PRESETS)
        assert profile.report_shape in VALID_SHAPES, name


def test_readme_meta_rules_are_applied(tmp_path: Path):
    template_path = require_template("武器分析模板.md")
    output_dir = tmp_path / "framework"

    written = build_framework(
        template_path,
        presets_path=Path("assets/framework-presets.yaml"),
        output_dir=output_dir,
    )

    route_text = written["route"].read_text(encoding="utf-8")
    curation_text = written["curation"].read_text(encoding="utf-8")

    assert "README.md" in route_text
    assert "meta_rules" in route_text
    assert "总览表只是索引，不是正文替代" in curation_text
    assert "forbid_unsourced_impressions" in curation_text
    assert "forbid_fingerprint_golden_claims" in curation_text


def test_forbidden_table_template_records_forbidden_mode(tmp_path: Path):
    template = tmp_path / "禁止表格模板.md"
    template.write_text(
        "# 禁止表格模板\n\n禁止输出表格，请使用卡片。\n\n```markdown\n## 要素卡片：{名称}\n- 来源：\n```",
        encoding="utf-8",
    )

    profile = build_template_profile(template)

    assert "table" in profile.forbidden_output_modes
    assert profile.report_shape == "cards_only"
