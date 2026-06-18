from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "extracting-worldbuilding" / "SKILL.md"


def test_skill_documents_template_batch_orchestration():
    text = SKILL.read_text(encoding="utf-8")

    assert "batch-plan.json" in text
    assert "每个模板一个独立 subagent" in text
    assert "并行" in text
    assert "禁止一个 agent 串跑多篇文档" in text
    assert "README.md" in text
    assert "文件名 = 模板名删除“模板”二字" in text


def test_skill_documents_subagent_prompt_contract():
    text = SKILL.read_text(encoding="utf-8")

    for required in [
        "模板全文",
        "全局元规则",
        "原文路径",
        "输出路径",
        "原文未说明",
        "待核验",
        "原作事实",
        "我的判断",
    ]:
        assert required in text


def test_skill_documents_overwrite_and_merge_modes():
    text = SKILL.read_text(encoding="utf-8")

    assert "默认 overwrite" in text
    assert "Mode merge" in text
    assert "本次变更摘要" in text
    assert ".bak" in text
    assert "目标文档尚不存在" in text
    assert "首次生成" in text
    assert "不需要 .bak" in text


def test_skill_documents_quality_baseline_and_python_downgrade():
    text = SKILL.read_text(encoding="utf-8")

    assert "凡人修仙传/法宝妖兽丹药分析.md" in text
    assert "candidate/evidence 抽取仅为 entity_table 类模板" in text
    assert "叙事 / 关系 / 流程类模板" in text
    assert "不调用 LLM" in text
    assert "不管理 API key" in text
    assert "不管理并发" in text
