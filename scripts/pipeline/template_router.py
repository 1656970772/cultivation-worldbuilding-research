from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from string import Formatter

from .config_loader import load_yaml
from .template_profile import build_template_profile


DEFAULT_PRESETS = Path(__file__).resolve().parents[2] / "assets" / "framework-presets.yaml"
OUTPUT_NAME_PLACEHOLDERS = ("work_title", "template_subject", "subject_type")
OUTPUT_NAME_PLACEHOLDER_ERROR = (
    "output_name_pattern supports placeholders: work_title, template_subject, subject_type"
)


def route_template(
    registry_path: Path,
    template_path: Path,
    user_request: str = "",
    presets_path: Path | None = None,
) -> dict:
    registry = load_yaml(registry_path)
    name = template_path.name
    templates = registry.get("templates", {})
    if not isinstance(templates, dict):
        raise ValueError("templates must be a mapping")

    if name in templates:
        route = dict(templates[name])
        route["template_name"] = name
        return route

    matches = [key for key in templates if key in user_request]
    if matches:
        matched = matches[0]
        route = dict(templates[matched])
        route["template_name"] = matched
        return route

    return _generic_route(template_path, presets_path or DEFAULT_PRESETS)


def _generic_route(template_path: Path, presets_path: Path) -> dict:
    presets = load_yaml(presets_path)
    profile = build_template_profile(template_path, presets_path=presets_path) if template_path.exists() else None
    shape = profile.report_shape if profile is not None else ""
    route_defaults = presets.get("route_defaults", {})
    primary_mode_by_shape = route_defaults.get("primary_mode_by_shape", {})
    primary_mode = primary_mode_by_shape.get(shape, shape or "generic")
    template_subject = _template_subject(template_path)
    subject_type = _subject_type(template_subject)
    output_pattern = _format_output_name_pattern(
        str(route_defaults.get("output_name_pattern", "{work_title}{template_subject}.md")),
        template_subject,
        subject_type,
    )

    return {
        "primary_mode": primary_mode,
        "secondary_modes": [],
        "subject_type": subject_type,
        "rule_pack": "",
        "output_name_pattern": output_pattern,
        "report_title_pattern": str(route_defaults.get("report_title_pattern", "《{work_title}》{subject_type}分析")),
        "required_columns": [field.name for field in profile.fields] if profile is not None else [],
        "template_name": template_path.name,
        "template_profile": asdict(profile) if profile is not None else {},
    }


def _template_subject(template_path: Path) -> str:
    stem = template_path.stem
    return stem.replace("模板", "")


def _subject_type(template_subject: str) -> str:
    return template_subject.removesuffix("分析") or template_subject


def _format_output_name_pattern(pattern: str, template_subject: str, subject_type: str) -> str:
    try:
        parsed = list(Formatter().parse(pattern))
    except ValueError as exc:
        raise ValueError(OUTPUT_NAME_PLACEHOLDER_ERROR) from exc

    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name not in OUTPUT_NAME_PLACEHOLDERS or format_spec or conversion:
            raise ValueError(OUTPUT_NAME_PLACEHOLDER_ERROR)

    try:
        return pattern.format(
            work_title="{work_title}",
            template_subject=template_subject,
            subject_type=subject_type,
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(OUTPUT_NAME_PLACEHOLDER_ERROR) from exc
