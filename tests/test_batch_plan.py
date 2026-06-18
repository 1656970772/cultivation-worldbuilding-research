import json
from pathlib import Path

import pytest
import yaml

from scripts.pipeline.batch_plan import build_batch_plan, load_prompt_contract, safe_name, write_batch_plan


ROOT = Path(__file__).resolve().parents[1]
PROMPT_CONTRACT = ROOT / "assets" / "batch-prompt-contract.yaml"


def write_template(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_prompt_contract_is_configured_in_yaml():
    contract = load_prompt_contract(PROMPT_CONTRACT)

    assert contract["parallel_rule"] == "每个模板一个独立 subagent；你只能处理本 prompt 中的这一个模板，禁止一个 agent 串跑多篇文档。多个同类任务会由调用方并行派发。"
    assert "overwrite" in contract["mode_contracts"]
    assert "merge_existing" in contract["mode_contracts"]
    assert "merge_new" in contract["mode_contracts"]
    assert contract["quality_baseline"]["reference"] == "凡人修仙传/法宝妖兽丹药分析.md"
    assert "原文未说明" in contract["unknown_terms"]
    assert "原作事实" in contract["fact_labels"]
    assert "禁止为补齐境界、丹方、关系、流程或案例而编造内容。" in contract["forbidden_rules"]


def test_build_batch_plan_creates_one_item_per_template(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    source_dir = tmp_path / "凡人修仙传"
    source_dir.mkdir()
    source_file = write_template(source_dir / "凡人修仙传.txt", "韩立服下黄龙丹。")
    write_template(template_dir / "README.md", "# 元规则\n\n- 区分原作事实 / 我的判断 / 待核验\n")
    write_template(
        template_dir / "丹药分析模板.md",
        "# 丹药分析模板\n\n## 推荐结构\n\n| 丹药名称 | 功效 | 证据 |\n| --- | --- | --- |\n| 黄龙丹 | 增进修为 | 第一章 |\n",
    )
    write_template(
        template_dir / "事件因果链（长程因果图）模板.md",
        "# 事件因果链（长程因果图）模板\n\n## 推荐结构\n\n1. 起因：\n2. 发展：\n3. 结果：\n\n起因 -> 发展 -> 结果\n",
    )

    plan = build_batch_plan(
        template_dir=template_dir,
        source_dir=source_dir,
        source_file=source_file,
        mode="overwrite",
        framework_root=source_dir / ".worldbuilding-framework",
    )

    assert plan["schema_version"] == 1
    assert plan["mode"] == "overwrite"
    assert plan["template_count"] == 2
    assert [Path(item["template_path"]).name for item in plan["items"]] == [
        "丹药分析模板.md",
        "事件因果链（长程因果图）模板.md",
    ]
    assert [Path(item["output_path"]).name for item in plan["items"]] == [
        "丹药分析.md",
        "事件因果链（长程因果图）.md",
    ]
    assert plan["items"][0]["report_shape"] == "entity_table"
    assert plan["items"][1]["report_shape"] == "process_chain"
    assert "每个模板一个独立 subagent" in plan["items"][0]["subagent_prompt"]
    assert "丹药分析模板.md" in plan["items"][0]["subagent_prompt"]
    assert "事件因果链（长程因果图）模板.md" not in plan["items"][0]["subagent_prompt"]
    assert "区分原作事实 / 我的判断 / 待核验" in plan["items"][0]["subagent_prompt"]
    assert "字段无依据写法：原文未说明 / 待核验" in plan["items"][0]["subagent_prompt"]
    assert "事实标签：原作事实 / 我的判断 / 待核验" in plan["items"][0]["subagent_prompt"]
    assert "禁止为补齐境界、丹方、关系、流程或案例而编造内容。" in plan["items"][0]["subagent_prompt"]


def test_build_batch_plan_merge_mode_records_existing_output_and_merge_rules(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    source_dir = tmp_path / "凡人修仙传"
    source_dir.mkdir()
    source_file = write_template(source_dir / "凡人修仙传.txt", "韩立服下黄龙丹。")
    write_template(template_dir / "README.md", "# 元规则\n")
    write_template(
        template_dir / "丹药分析模板.md",
        "# 丹药分析模板\n\n## 推荐结构\n\n| 丹药名称 | 功效 | 证据 |\n| --- | --- | --- |\n",
    )
    write_template(source_dir / "丹药分析.md", "# 旧丹药分析\n\n人工整理内容。\n")

    plan = build_batch_plan(
        template_dir=template_dir,
        source_dir=source_dir,
        source_file=source_file,
        mode="merge",
        framework_root=source_dir / ".worldbuilding-framework",
    )

    [item] = plan["items"]
    assert item["mode"] == "merge"
    assert item["output_exists"] is True
    assert "先读取旧文档" in item["subagent_prompt"]
    assert "本次变更摘要" in item["subagent_prompt"]
    assert ".bak" in item["subagent_prompt"]


def test_build_batch_plan_merge_mode_without_existing_output_uses_merge_new_contract(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    source_dir = tmp_path / "凡人修仙传"
    source_dir.mkdir()
    source_file = write_template(source_dir / "凡人修仙传.txt", "韩立服下黄龙丹。")
    write_template(template_dir / "README.md", "# 元规则\n")
    write_template(
        template_dir / "丹药分析模板.md",
        "# 丹药分析模板\n\n## 推荐结构\n\n| 丹药名称 | 功效 | 证据 |\n| --- | --- | --- |\n",
    )

    plan = build_batch_plan(
        template_dir=template_dir,
        source_dir=source_dir,
        source_file=source_file,
        mode="merge",
        framework_root=source_dir / ".worldbuilding-framework",
    )

    [item] = plan["items"]
    assert item["output_exists"] is False
    assert "首次生成" in item["subagent_prompt"]
    assert "不需要 `.bak`" in item["subagent_prompt"]


def test_build_batch_plan_strips_bom_from_prompt_and_framework_readme_rules(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    source_dir = tmp_path / "凡人修仙传"
    source_dir.mkdir()
    source_file = write_template(source_dir / "凡人修仙传.txt", "韩立服下黄龙丹。")
    write_template(template_dir / "README.md", "\ufeff# 元规则\n\n- 区分原作事实 / 我的判断 / 待核验\n")
    write_template(
        template_dir / "丹药分析模板.md",
        "\ufeff# 丹药分析模板\n\n## 推荐结构\n\n| 丹药名称 | 功效 | 证据 |\n| --- | --- | --- |\n",
    )

    plan = build_batch_plan(
        template_dir=template_dir,
        source_dir=source_dir,
        source_file=source_file,
        framework_root=source_dir / ".worldbuilding-framework",
    )

    [item] = plan["items"]
    assert "\ufeff" not in item["subagent_prompt"]
    assert "```markdown\n# 元规则" in item["subagent_prompt"]
    assert "```markdown\n# 丹药分析模板" in item["subagent_prompt"]
    curation = yaml.safe_load(Path(item["framework_outputs"]["curation"]).read_text(encoding="utf-8"))
    assert "区分原作事实 / 我的判断 / 待核验" in curation["meta_rules"]


def test_build_batch_plan_records_existing_framework_outputs_under_item_dir(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    source_dir = tmp_path / "凡人修仙传"
    source_dir.mkdir()
    framework_root = source_dir / ".worldbuilding-framework"
    source_file = write_template(source_dir / "凡人修仙传.txt", "韩立服下黄龙丹。")
    write_template(template_dir / "README.md", "# 元规则\n")
    write_template(
        template_dir / "丹药分析模板.md",
        "# 丹药分析模板\n\n## 推荐结构\n\n| 丹药名称 | 功效 | 证据 |\n| --- | --- | --- |\n",
    )

    plan = build_batch_plan(
        template_dir=template_dir,
        source_dir=source_dir,
        source_file=source_file,
        framework_root=framework_root,
    )

    [item] = plan["items"]
    item_framework_dir = framework_root / "001-丹药分析模板"
    assert Path(item["framework_dir"]) == item_framework_dir
    assert item["framework_outputs"]
    for path_text in item["framework_outputs"].values():
        path = Path(path_text)
        assert path.exists()
        assert path.is_relative_to(item_framework_dir)


def test_build_batch_plan_rejects_unknown_mode(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_file = write_template(source_dir / "source.txt", "正文")

    with pytest.raises(ValueError, match="mode must be one of"):
        build_batch_plan(template_dir, source_dir, source_file, mode="append")


def test_write_batch_plan_writes_utf8_json(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source_file = write_template(source_dir / "凡人修仙传.txt", "正文")
    write_template(template_dir / "README.md", "# 元规则\n")
    write_template(
        template_dir / "世界观设定模板.md",
        "# 世界观设定模板\n\n## 推荐结构\n\n| 名称 | 类型 | 证据 |\n| --- | --- | --- |\n\n## 设定卡：{名称}\n- 类型：\n- 证据：\n",
    )
    output = tmp_path / "batch-plan.json"

    plan = build_batch_plan(template_dir, source_dir, source_file)
    write_batch_plan(output, plan)

    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["items"][0]["template_name"] == "世界观设定模板.md"


def test_load_prompt_contract_rejects_missing_nested_mode_contract(tmp_path):
    contract_path = tmp_path / "bad-contract.yaml"
    contract_path.write_text(
        """
version: 1
parallel_rule: "每个模板一个独立 subagent"
search_methods: [rg]
unknown_terms: [原文未说明]
fact_labels: [原作事实]
execution_requirements: ["阅读模板"]
forbidden_rules: ["禁止编造"]
quality_baseline:
  reference: "参考.md"
  expectation: "对标质量"
mode_contracts:
  overwrite: "覆盖"
  merge_existing: "合并旧文档"
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="mode_contracts.merge_new"):
        load_prompt_contract(contract_path)


def test_safe_name_replaces_control_characters():
    assert safe_name("丹药\n分析\t模板:name") == "丹药-分析-模板-name"
