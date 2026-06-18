from pathlib import Path

from scripts.pipeline.document_composer import build_composer_messages, compose_document
from scripts.pipeline.template_profile import build_template_profile


def test_composer_messages_include_structured_items_and_template_rules(tmp_path: Path):
    template = tmp_path / "丹药分析模板.md"
    template.write_text(
        "# 丹药分析模板\n\n## 推荐结构\n\n| 丹药名称 | 功效 |\n| --- | --- |\n| 聚气丹 | 增加真气 |\n",
        encoding="utf-8",
    )
    profile = build_template_profile(template)
    items = [{"name": "聚气丹", "fields": {"丹药名称": "聚气丹", "功效": "增加真气"}}]

    messages = build_composer_messages(profile, items, readme_text="禁止编造")

    payload = "\n".join(message["content"] for message in messages)
    assert "聚气丹" in payload
    assert "增加真气" in payload
    assert "禁止编造" in payload
    assert "原作事实 / 我的判断 / 待核验" in payload


def test_compose_document_uses_injected_chat_function(tmp_path: Path):
    template = tmp_path / "丹药分析模板.md"
    template.write_text("# 丹药分析模板\n", encoding="utf-8")
    profile = build_template_profile(template)
    calls = []

    def fake_chat(*, model_id, messages, provider_config, generation_config):
        calls.append((model_id, messages, provider_config, generation_config))
        return "<think>hidden</think>\n# 《凡人修仙传》丹药分析\n"

    markdown = compose_document(
        profile,
        [{"name": "聚气丹", "fields": {"丹药名称": "聚气丹"}}],
        readme_text="",
        model_id="MiniMax-M2.7",
        provider_config={"api_key": "key", "base_url": "https://example/v1"},
        chat_fn=fake_chat,
    )

    assert calls
    assert markdown == "# 《凡人修仙传》丹药分析\n"
