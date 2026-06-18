from __future__ import annotations

from dataclasses import dataclass

from scripts.pipeline.template_profile import TemplateProfile


@dataclass(frozen=True)
class ExtractionSpec:
    extraction_class: str
    extraction_text: str
    attributes: dict[str, str]


@dataclass(frozen=True)
class ExampleSpec:
    text: str
    extractions: list[ExtractionSpec]


def build_prompt_description(profile: TemplateProfile, readme_text: str = "") -> str:
    fields = _profile_fields(profile)
    lines = [
        f"从当前文本块中抽取《{profile.template_name}》需要的所有信息。",
        "只抽取当前文本块中有原文依据的内容；不要编造，不要补全原文未说明的信息。",
        "每个 extraction_text 必须尽量使用原文中可定位的短语，并依赖 LangExtract 的 char_interval 溯源。",
        "如果某个字段没有依据，在 attributes 中写“原文未说明”或省略该字段，不要猜测。",
        f"抽取类别 extraction_class 固定为：{_extraction_class(profile)}。",
    ]
    if fields:
        lines.append("字段清单：" + "、".join(fields))
    if profile.report_shape:
        lines.append(f"报告形态：{profile.report_shape}。")
    if readme_text.strip():
        lines.extend(["", "模板目录元规则：", readme_text.strip()])
    return "\n".join(lines).strip() + "\n"


def build_example_specs(profile: TemplateProfile, max_examples: int = 5) -> list[ExampleSpec]:
    examples: list[ExampleSpec] = []
    extraction_class = _extraction_class(profile)
    for template_example in profile.examples[:max_examples]:
        attributes = dict(template_example.fields)
        extraction_text = template_example.title.strip()
        if not extraction_text:
            continue
        text = template_example.text
        if extraction_text not in text:
            text = f"{extraction_text}\n{text}".strip()
        examples.append(
            ExampleSpec(
                text=text,
                extractions=[
                    ExtractionSpec(
                        extraction_class=extraction_class,
                        extraction_text=extraction_text,
                        attributes=attributes,
                    )
                ],
            )
        )
    return examples


def to_langextract_examples(example_specs: list[ExampleSpec]):
    try:
        from langextract import data as lx_data
    except ImportError as exc:
        raise RuntimeError(
            "Missing LangExtract dependency. Install it with: pip install langextract[openai]"
        ) from exc
    return [
        lx_data.ExampleData(
            text=example.text,
            extractions=[
                lx_data.Extraction(
                    extraction_class=extraction.extraction_class,
                    extraction_text=extraction.extraction_text,
                    attributes=extraction.attributes,
                )
                for extraction in example.extractions
            ],
        )
        for example in example_specs
    ]


def _profile_fields(profile: TemplateProfile) -> list[str]:
    fields = [field.name for field in profile.fields]
    if fields:
        return fields
    for example in profile.examples:
        for name in example.fields:
            if name not in fields:
                fields.append(name)
    for section in profile.sections:
        for name in section.fields:
            if name not in fields:
                fields.append(name)
    return fields


def _extraction_class(profile: TemplateProfile) -> str:
    return profile.template_kind or profile.template_name.removesuffix("模板") or profile.report_shape
