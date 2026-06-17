from pathlib import Path

import pytest

from scripts.pipeline.analysis_framework import build_framework
from scripts.pipeline.config_loader import load_yaml
from scripts.pipeline.template_profile import build_template_profile


TEMPLATE_DIR = Path("E:/AI_Projects/CultivationWorld/docs/世界观参考/模板")
PRESETS = Path("assets/framework-presets.yaml")


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

    assert profile.report_shape == "overview_plus_cards"
    assert profile.sections


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

    assert event_profile.report_shape == "process_chain"
    assert ai_profile.report_shape == "decision_chain"


def test_real_template_shapes_follow_expected_files_config():
    expected_files = load_yaml(PRESETS)["template_catalog"]["expected_files"]
    names = [name for name, expected_shape in expected_files.items() if expected_shape != "meta_rules"]

    for name in names:
        profile = build_template_profile(require_template(name), presets_path=PRESETS)
        assert profile.report_shape == expected_files[name], name


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
