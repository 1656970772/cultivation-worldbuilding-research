from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import re
from typing import Any

import yaml

from scripts.pipeline.config_loader import load_yaml
from scripts.pipeline.template_profile import build_template_profile


def load_framework_presets(path: Path) -> dict[str, Any]:
    return load_yaml(path)


def parse_template_readme(readme_path: Path) -> dict[str, Any]:
    defaults: dict[str, Any] = {"source": "", "meta_rules": [], "forbidden_output_modes": []}
    if not readme_path.exists():
        return defaults

    text = readme_path.read_text(encoding="utf-8")
    meta_rules = _collect_list_items(text, ("规则", "元规则", "Meta Rules"))
    forbidden = _collect_list_items(text, ("禁止", "Forbidden", "不得"))
    if not forbidden:
        forbidden = _detect_forbidden_output_modes(text)
    meta_rules = _dedupe(meta_rules + _readme_rule_tags(text))
    return {"source": str(readme_path), "meta_rules": meta_rules, "forbidden_output_modes": forbidden}


def build_framework(template_path: Path, presets_path: Path, output_dir: Path) -> dict[str, Path]:
    presets = load_framework_presets(presets_path)
    template_dir = Path(str(presets.get("template_catalog", {}).get("template_dir", "")))
    if not template_dir.is_absolute():
        template_dir = presets_path.parent / template_dir
    readme_path = template_dir / "README.md"
    if not readme_path.exists():
        readme_path = template_path.parent / "README.md"
    readme_rules = parse_template_readme(readme_path)
    profile = build_template_profile(template_path, presets_path=presets_path)
    profile_data = asdict(profile)
    threshold = float(presets.get("validation_rules", {}).get("low_confidence_threshold", 0.6))

    if profile.confidence < threshold:
        _remove_managed_outputs(output_dir)
        summary_path = write_framework_summary(
            output_dir,
            _summary(template_path, presets, profile_data, readme_rules, questions=profile.questions),
        )
        return {"summary": summary_path}

    shape_config = _shape_config(presets, profile.report_shape)
    route = {
        "template_profile": profile_data,
        "report_shape": profile.report_shape,
        "render_strategy": shape_config.get("render_strategy", profile.report_shape),
        "render_blocks": _selected_render_blocks(presets, shape_config),
        "required_fields": _required_fields(profile_data, shape_config),
        "name_field": profile.name_field or shape_config.get("name_field", ""),
        "meta_rules_source": readme_rules["source"],
        "meta_rules": readme_rules["meta_rules"],
    }
    rule_pack = {
        "subject_aliases": presets.get("subject_aliases", {}),
        "candidate_strategies": _selected_candidate_strategies(presets, shape_config),
        "template_shape_rules": {
            profile.report_shape: presets.get("template_shape_rules", {}).get(profile.report_shape, {})
        },
        "shape_detection_keywords": {
            profile.report_shape: presets.get("shape_detection_keywords", {}).get(profile.report_shape, {})
        },
    }
    curation = {
        "fields": _curation_fields(profile_data, shape_config),
        "validation_rules": _validation_rules(presets, readme_rules),
        "forbidden_output_modes": _dedupe(
            list(profile.forbidden_output_modes) + list(readme_rules["forbidden_output_modes"])
        ),
        "review_workflow": shape_config.get("review_workflow", ""),
        "meta_rules": readme_rules["meta_rules"],
    }
    summary = _summary(template_path, presets, profile_data, readme_rules, questions=profile.questions)

    return {
        "route": write_route_json(output_dir, route),
        "rule_pack": write_rule_pack_yaml(output_dir, rule_pack),
        "curation": write_curation_yaml(output_dir, curation),
        "summary": write_framework_summary(output_dir, summary),
    }


def generate_framework(
    template_path: Path,
    framework_dir: Path,
    presets_path: Path,
    work_title: str,
    user_request: str,
) -> dict[str, str]:
    outputs = build_framework(template_path, presets_path, framework_dir)
    summary_path = outputs.get("summary")
    if summary_path and summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["work_title"] = work_title
        summary["user_request"] = user_request
        write_framework_summary(framework_dir, summary)
    return {key: str(path) for key, path in outputs.items()}


def write_route_json(output_dir: Path, route: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "route.json"
    path.write_text(json.dumps(route, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_yaml(output_dir: Path, filename: str, data: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def write_rule_pack_yaml(output_dir: Path, rule_pack: dict[str, Any]) -> Path:
    return _write_yaml(output_dir, "rule-pack.yaml", rule_pack)


def write_curation_yaml(output_dir: Path, curation: dict[str, Any]) -> Path:
    return _write_yaml(output_dir, "curation.yaml", curation)


def write_framework_summary(output_dir: Path, summary: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "framework-summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _remove_managed_outputs(output_dir: Path) -> None:
    for filename in ("route.json", "rule-pack.yaml", "curation.yaml"):
        path = output_dir / filename
        if path.exists():
            path.unlink()


def _shape_config(presets: dict[str, Any], report_shape: str) -> dict[str, Any]:
    config = presets.get("template_shapes", {}).get(report_shape, {})
    return config if isinstance(config, dict) else {}


def _selected_render_blocks(presets: dict[str, Any], shape_config: dict[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    configured_blocks = presets.get("render_blocks", {})
    for name in shape_config.get("render_blocks", []):
        blocks.extend(configured_blocks.get(name, []))
    return blocks


def _selected_candidate_strategies(presets: dict[str, Any], shape_config: dict[str, Any]) -> dict[str, Any]:
    strategies = presets.get("candidate_strategies", {})
    return {name: strategies[name] for name in shape_config.get("candidate_strategies", []) if name in strategies}


def _required_fields(profile_data: dict[str, Any], shape_config: dict[str, Any]) -> list[str]:
    profile_fields = [field["name"] for field in profile_data.get("fields", [])]
    return profile_fields or list(shape_config.get("required_fields", []))


def _curation_fields(profile_data: dict[str, Any], shape_config: dict[str, Any]) -> list[str]:
    profile_fields = [field["name"] for field in profile_data.get("fields", [])]
    return profile_fields or list(shape_config.get("fields", []))


def _validation_rules(presets: dict[str, Any], readme_rules: dict[str, Any]) -> dict[str, Any]:
    validation = dict(presets.get("validation_rules", {}))
    validation["meta_rules"] = _dedupe(
        list(readme_rules.get("meta_rules", []))
        + list(readme_rules.get("forbidden_output_modes", []))
        + list(validation.get("meta_rules", []))
    )
    return validation


def _summary(
    template_path: Path,
    presets: dict[str, Any],
    profile_data: dict[str, Any],
    readme_rules: dict[str, Any],
    questions: list[str],
) -> dict[str, Any]:
    expected_files = presets.get("template_catalog", {}).get("expected_files", {})
    return {
        "template": str(template_path),
        "template_name": template_path.name,
        "report_shape": profile_data.get("report_shape", ""),
        "confidence": profile_data.get("confidence", 0.0),
        "template_catalog_count": len(expected_files) if isinstance(expected_files, dict) else 0,
        "questions": questions,
        "meta_rules_count": len(readme_rules.get("meta_rules", [])),
    }


def _collect_list_items(text: str, heading_terms: tuple[str, ...]) -> list[str]:
    items: list[str] = []
    in_section = False
    for line in text.splitlines():
        heading = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if heading:
            title = heading.group(1)
            in_section = any(term.lower() in title.lower() for term in heading_terms)
            continue
        if not in_section:
            continue
        item = re.match(r"^\s*[-*+]\s+(.+?)\s*$", line)
        if item:
            items.append(item.group(1).strip())
            continue
        stripped = line.strip()
        if stripped and not stripped.startswith("|") and not stripped.startswith("```"):
            items.append(stripped)
    return items


def _detect_forbidden_output_modes(text: str) -> list[str]:
    modes = []
    for mode in ("表格", "卡片", "自由发挥"):
        if re.search(rf"(不要|禁止|不应|不得)[^。\n]*{re.escape(mode)}", text):
            modes.append(mode)
    return modes


def _readme_rule_tags(text: str) -> list[str]:
    tags: list[str] = []
    if "没有来源" in text or "无来源" in text:
        tags.append("forbid_unsourced_impressions")
    if "指纹" in text or "golden" in text.lower():
        tags.append("forbid_fingerprint_golden_claims")
    return tags


def _dedupe(values: list[Any]) -> list[Any]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
