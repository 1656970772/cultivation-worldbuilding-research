from __future__ import annotations

import json
import re
from typing import Any, Callable

from scripts.pipeline.template_profile import TemplateProfile


ChatFn = Callable[..., str]


def build_composer_messages(
    profile: TemplateProfile,
    merged_items: list[dict[str, Any]],
    readme_text: str = "",
) -> list[dict[str, str]]:
    system = (
        "你是世界观资料整理助手。只能基于给定结构化抽取结果成文，"
        "必须区分原作事实 / 我的判断 / 待核验；没有依据写“原文未说明”。"
    )
    payload = {
        "template_name": profile.template_name,
        "template_kind": profile.template_kind,
        "report_shape": profile.report_shape,
        "fields": [field.name for field in profile.fields],
        "sections": [
            {"title": section.title, "kind": section.kind, "fields": section.fields}
            for section in profile.sections
        ],
        "items": merged_items,
    }
    user_parts = [
        "请按模板推荐结构写成最终 Markdown 文档。",
        "不得编造抽取结果中不存在的原作事实。",
        "模板目录元规则：",
        readme_text.strip() or "无",
        "结构化抽取结果 JSON：",
        json.dumps(payload, ensure_ascii=False, indent=2),
    ]
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_parts)},
    ]


def compose_document(
    profile: TemplateProfile,
    merged_items: list[dict[str, Any]],
    *,
    readme_text: str = "",
    model_id: str,
    provider_config: dict[str, Any],
    generation_config: dict[str, Any] | None = None,
    chat_fn: ChatFn | None = None,
) -> str:
    messages = build_composer_messages(profile, merged_items, readme_text)
    if chat_fn is None:
        chat_fn = _openai_chat
    content = chat_fn(
        model_id=model_id,
        messages=messages,
        provider_config=provider_config,
        generation_config=generation_config or {},
    )
    return _strip_thinking(content).strip() + "\n"


def _openai_chat(
    *,
    model_id: str,
    messages: list[dict[str, str]],
    provider_config: dict[str, Any],
    generation_config: dict[str, Any],
) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Missing OpenAI client dependency from langextract[openai].") from exc
    client = OpenAI(
        api_key=str(provider_config.get("api_key", "")),
        base_url=str(provider_config.get("base_url", "")),
        timeout=float(generation_config.get("timeout_seconds") or 120),
    )
    request: dict[str, Any] = {"model": model_id, "messages": messages}
    if generation_config.get("temperature") is not None:
        request["temperature"] = float(generation_config["temperature"])
    if generation_config.get("max_tokens"):
        request["max_tokens"] = int(generation_config["max_tokens"])
    response = client.chat.completions.create(**request)
    return response.choices[0].message.content or ""


def _strip_thinking(content: str) -> str:
    return re.sub(r"(?is)<think>.*?</think>\s*", "", content).strip()
