from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from scripts.pipeline.analysis_framework import build_framework
from scripts.pipeline.config_loader import load_yaml
from scripts.pipeline.template_profile import build_template_profile


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRESETS = ROOT / "assets" / "framework-presets.yaml"
DEFAULT_PROMPT_CONTRACT = ROOT / "assets" / "batch-prompt-contract.yaml"
VALID_MODES = {"overwrite", "merge"}


def build_batch_plan(
    template_dir: Path,
    source_dir: Path,
    source_file: Path,
    mode: str = "overwrite",
    output_path: Path | None = None,
    framework_root: Path | None = None,
    presets_path: Path | None = None,
    prompt_contract_path: Path | None = None,
) -> dict[str, Any]:
    template_dir = Path(template_dir)
    source_dir = Path(source_dir)
    source_file = Path(source_file)
    presets_path = Path(presets_path) if presets_path is not None else DEFAULT_PRESETS
    prompt_contract_path = Path(prompt_contract_path) if prompt_contract_path is not None else DEFAULT_PROMPT_CONTRACT
    prompt_contract = load_prompt_contract(prompt_contract_path)
    framework_root = Path(framework_root) if framework_root is not None else source_dir / ".worldbuilding-framework"
    output_path = Path(output_path) if output_path is not None else source_dir / "batch-plan.json"

    normalized_mode = mode.lower()
    if normalized_mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {sorted(VALID_MODES)}: {mode}")
    if not template_dir.is_dir():
        raise FileNotFoundError(f"template_dir not found: {template_dir}")
    if not source_dir.is_dir():
        raise FileNotFoundError(f"source_dir not found: {source_dir}")
    if not source_file.is_file():
        raise FileNotFoundError(f"source_file not found: {source_file}")

    readme_path = template_dir / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8-sig") if readme_path.exists() else ""
    items = [
        build_batch_item(
            index=index,
            template_path=template_path,
            source_dir=source_dir,
            source_file=source_file,
            mode=normalized_mode,
            framework_root=framework_root,
            presets_path=presets_path,
            prompt_contract=prompt_contract,
            readme_path=readme_path if readme_path.exists() else None,
            readme_text=readme_text,
        )
        for index, template_path in enumerate(list_templates(template_dir), 1)
    ]
    return {
        "schema_version": 1,
        "template_dir": str(template_dir),
        "source_dir": str(source_dir),
        "source_file": str(source_file),
        "mode": normalized_mode,
        "output_path": str(output_path),
        "framework_root": str(framework_root),
        "prompt_contract": str(prompt_contract_path),
        "template_count": len(items),
        "items": items,
    }


def load_prompt_contract(path: Path) -> dict[str, Any]:
    contract = load_yaml(Path(path))
    list_keys = [
        "search_methods",
        "unknown_terms",
        "fact_labels",
        "execution_requirements",
        "forbidden_rules",
    ]
    required = ["parallel_rule", "quality_baseline", "mode_contracts", *list_keys]
    missing = [key for key in required if key not in contract]
    if missing:
        raise ValueError(f"batch prompt contract missing keys: {', '.join(missing)}")
    for key in list_keys:
        if not isinstance(contract[key], list):
            raise ValueError(f"batch prompt contract key must be a list: {key}")
    mode_contracts = _require_mapping(contract, "mode_contracts")
    _require_nested_keys(mode_contracts, "mode_contracts", ["overwrite", "merge_existing", "merge_new"])
    quality_baseline = _require_mapping(contract, "quality_baseline")
    _require_nested_keys(quality_baseline, "quality_baseline", ["reference", "expectation"])
    return contract


def list_templates(template_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(Path(template_dir).glob("*.md"), key=lambda item: item.name)
        if path.name.lower() != "readme.md"
    ]


def build_batch_item(
    index: int,
    template_path: Path,
    source_dir: Path,
    source_file: Path,
    mode: str,
    framework_root: Path,
    presets_path: Path,
    prompt_contract: dict[str, Any],
    readme_path: Path | None,
    readme_text: str,
) -> dict[str, Any]:
    output_path = derive_output_path(source_dir, template_path)
    framework_dir = framework_root / f"{index:03d}-{safe_name(template_path.stem)}"
    framework_outputs = build_framework(template_path, presets_path, framework_dir)
    profile = build_template_profile(template_path, presets_path=presets_path)
    template_text = template_path.read_text(encoding="utf-8-sig")
    output_exists = output_path.exists()
    return {
        "index": index,
        "template_path": str(template_path),
        "template_name": template_path.name,
        "report_shape": profile.report_shape,
        "confidence": profile.confidence,
        "questions": profile.questions,
        "output_path": str(output_path),
        "output_exists": output_exists,
        "mode": mode,
        "framework_dir": str(framework_dir),
        "framework_outputs": {key: str(value) for key, value in framework_outputs.items()},
        "subagent_prompt": build_subagent_prompt(
            template_path=template_path,
            template_text=template_text,
            readme_path=readme_path,
            readme_text=readme_text,
            source_file=source_file,
            output_path=output_path,
            report_shape=profile.report_shape,
            mode=mode,
            output_exists=output_exists,
            prompt_contract=prompt_contract,
        ),
    }


def derive_output_path(source_dir: Path, template_path: Path) -> Path:
    output_stem = template_path.stem.replace("模板", "")
    return source_dir / f"{output_stem}.md"


def safe_name(value: str) -> str:
    cleaned = re.sub(r'[\x00-\x1f<>:"/\\|?*]+', "-", value).strip(". ")
    return cleaned or "template"


def build_subagent_prompt(
    template_path: Path,
    template_text: str,
    readme_path: Path | None,
    readme_text: str,
    source_file: Path,
    output_path: Path,
    report_shape: str,
    mode: str,
    output_exists: bool,
    prompt_contract: dict[str, Any],
) -> str:
    mode_key = "overwrite" if mode == "overwrite" else "merge_existing" if output_exists else "merge_new"
    mode_contract = prompt_contract["mode_contracts"][mode_key]
    readme_label = str(readme_path) if readme_path is not None else "未提供 README.md"
    search_methods = "、".join(str(item) for item in prompt_contract.get("search_methods", []))
    unknown_terms = " / ".join(str(item) for item in prompt_contract["unknown_terms"])
    fact_labels = " / ".join(str(item) for item in prompt_contract["fact_labels"])
    quality = prompt_contract.get("quality_baseline", {})
    return f"""{prompt_contract.get("intro", "")}

{prompt_contract["parallel_rule"]}

任务输入：
- 模板路径：{template_path}
- 推断形状：{report_shape}
- 全局元规则来源：{readme_label}
- 原文路径：{source_file}
- 输出路径：{output_path}
- 写入模式：{mode}
- 可用检索方式：{search_methods}

执行要求：
{format_numbered(prompt_contract["execution_requirements"])}

配置规则：
- 字段无依据写法：{unknown_terms}
- 事实标签：{fact_labels}

禁止规则：
{format_bullets(prompt_contract["forbidden_rules"])}

质量基线：
- 参考：{quality.get("reference", "")}
- 要求：{quality.get("expectation", "")}

覆盖策略：
{mode_contract}

README.md 全局元规则：
```markdown
{readme_text}
```

模板全文：
```markdown
{template_text}
```
"""


def format_numbered(items: list[Any]) -> str:
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, 1))


def format_bullets(items: list[Any]) -> str:
    return "\n".join(f"- {item}" for item in items)


def write_batch_plan(output_path: Path, plan: dict[str, Any]) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def _require_mapping(contract: dict[str, Any], key: str) -> dict[str, Any]:
    value = contract[key]
    if not isinstance(value, dict):
        raise ValueError(f"batch prompt contract key must be a mapping: {key}")
    return value


def _require_nested_keys(value: dict[str, Any], prefix: str, required_keys: list[str]) -> None:
    missing = [f"{prefix}.{key}" for key in required_keys if key not in value]
    if missing:
        raise ValueError(f"batch prompt contract missing keys: {', '.join(missing)}")
