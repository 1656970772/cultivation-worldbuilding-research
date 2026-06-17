from pathlib import Path
import json

import yaml

from scripts.pipeline.analysis_framework import generate_framework, load_framework_presets


ROOT = Path(__file__).resolve().parents[1]
PRESETS = ROOT / "assets" / "framework-presets.yaml"


def test_presets_include_required_config_sections():
    presets = load_framework_presets(PRESETS)

    assert {
        "template_catalog",
        "template_shapes",
        "template_shape_rules",
        "shape_detection_keywords",
        "subject_aliases",
        "candidate_strategies",
        "render_blocks",
        "validation_rules",
    }.issubset(presets)
    assert presets["template_catalog"]["expected_files"]["README.md"] == "meta_rules"
    assert presets["template_catalog"]["expected_files"]["事件因果链（长程因果图）模板.md"] == "process_chain"
    assert presets["template_catalog"]["expected_files"]["角色AI行为参考模板.md"] == "decision_chain"
    assert presets["template_catalog"]["expected_files"]["功法术法神通模板.md"] == "cards_only"
    assert {"case_collection", "cards_only", "decision_chain", "relationship_chain", "profession_workflow"}.issubset(
        presets["template_shapes"]
    )
    assert all(isinstance(shape_config, dict) for shape_config in presets["template_shapes"].values())
    assert {"case_collection", "cards_only"}.issubset(presets["template_shape_rules"])
    assert {"case_collection", "cards_only"}.issubset(presets["shape_detection_keywords"])


def test_generate_framework_uses_profile_and_config(tmp_path):
    template = tmp_path / "事件因果链（长程因果图）模板.md"
    template.write_text(
        """# 事件因果链（长程因果图）模板

## 因果链

1. 触发事件：记录起点与证据
2. 中间环节：追踪影响扩散
3. 长程结果：整理最终变化

触发 -> 扩散 -> 结果
""",
        encoding="utf-8",
    )
    framework_dir = tmp_path / "framework"

    outputs = generate_framework(
        template_path=template,
        framework_dir=framework_dir,
        presets_path=PRESETS,
        work_title="凡人修仙传",
        user_request="抽取事件因果链",
    )

    route = json.loads((framework_dir / "route.json").read_text(encoding="utf-8"))
    rule_pack = yaml.safe_load((framework_dir / "rule-pack.yaml").read_text(encoding="utf-8"))
    curation = yaml.safe_load((framework_dir / "curation.yaml").read_text(encoding="utf-8"))

    assert outputs == {
        "route": str(framework_dir / "route.json"),
        "rule_pack": str(framework_dir / "rule-pack.yaml"),
        "curation": str(framework_dir / "curation.yaml"),
        "summary": str(framework_dir / "framework-summary.json"),
    }
    assert route["template_profile"]["report_shape"] == "process_chain"
    assert route["render_strategy"] == "process_chain"
    assert "process_step" in rule_pack["candidate_strategies"]
    assert "template_shape_rules" in rule_pack
    assert "shape_detection_keywords" in rule_pack
    assert curation["validation_rules"]["require_source_spans"] is True
    assert "meta_rules" in route
    assert "meta_rules" in curation
    assert curation["forbidden_output_modes"] == []


def test_low_confidence_writes_only_summary_with_questions(tmp_path):
    template = tmp_path / "自由摘录模板.md"
    template.write_text(
        """# 自由摘录模板

请根据原文整理有价值的信息。
""",
        encoding="utf-8",
    )
    framework_dir = tmp_path / "framework"

    outputs = generate_framework(
        template_path=template,
        framework_dir=framework_dir,
        presets_path=PRESETS,
        work_title="凡人修仙传",
        user_request="自由摘录",
    )
    summary = json.loads((framework_dir / "framework-summary.json").read_text(encoding="utf-8"))

    assert outputs == {"summary": str(framework_dir / "framework-summary.json")}
    assert summary["questions"] == [
        "这个模板最终应输出实体表、总览加卡片、案例集、流程链、决策链、关系链，还是职业闭环？",
        "哪些字段或小节必须出现，哪些输出形式禁止使用？",
    ]
    assert "fields" not in summary
    assert not (framework_dir / "route.json").exists()
    assert not (framework_dir / "rule-pack.yaml").exists()
    assert not (framework_dir / "curation.yaml").exists()


def test_low_confidence_removes_stale_managed_outputs(tmp_path):
    high_confidence_template = tmp_path / "事件因果链（长程因果图）模板.md"
    high_confidence_template.write_text(
        """# 事件因果链（长程因果图）模板

## 因果链

1. 起因：记录证据
2. 发展：追踪变化
3. 结果：汇总影响

起因 -> 发展 -> 结果
""",
        encoding="utf-8",
    )
    low_confidence_template = tmp_path / "未知模板.md"
    low_confidence_template.write_text(
        """# 未知模板

请根据原文整理有价值的信息。
""",
        encoding="utf-8",
    )
    framework_dir = tmp_path / "framework"

    generate_framework(
        template_path=high_confidence_template,
        framework_dir=framework_dir,
        presets_path=PRESETS,
        work_title="凡人修仙传",
        user_request="抽取事件因果链",
    )

    assert (framework_dir / "route.json").exists()
    assert (framework_dir / "rule-pack.yaml").exists()
    assert (framework_dir / "curation.yaml").exists()

    generate_framework(
        template_path=low_confidence_template,
        framework_dir=framework_dir,
        presets_path=PRESETS,
        work_title="凡人修仙传",
        user_request="自由摘录",
    )
    summary = json.loads((framework_dir / "framework-summary.json").read_text(encoding="utf-8"))

    assert summary["questions"] == [
        "这个模板最终应输出实体表、总览加卡片、案例集、流程链、决策链、关系链，还是职业闭环？",
        "哪些字段或小节必须出现，哪些输出形式禁止使用？",
    ]
    assert not (framework_dir / "route.json").exists()
    assert not (framework_dir / "rule-pack.yaml").exists()
    assert not (framework_dir / "curation.yaml").exists()


def test_missing_readme_uses_empty_meta_defaults(tmp_path):
    template = tmp_path / "事件因果链（长程因果图）模板.md"
    template.write_text(
        """# 事件因果链（长程因果图）模板

## 因果链

1. 起因：记录证据
2. 发展：追踪变化
3. 结果：汇总影响

起因 -> 发展 -> 结果
""",
        encoding="utf-8",
    )
    framework_dir = tmp_path / "framework"

    generate_framework(
        template_path=template,
        framework_dir=framework_dir,
        presets_path=PRESETS,
        work_title="凡人修仙传",
        user_request="抽取事件因果链",
    )

    route = json.loads((framework_dir / "route.json").read_text(encoding="utf-8"))
    curation = yaml.safe_load((framework_dir / "curation.yaml").read_text(encoding="utf-8"))

    assert route["meta_rules"] == []
    assert curation["meta_rules"] == []
    assert curation["forbidden_output_modes"] == []
