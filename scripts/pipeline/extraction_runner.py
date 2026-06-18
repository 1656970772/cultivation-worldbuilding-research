from __future__ import annotations

import json
import math
from pathlib import Path
import time
from typing import Any, Callable

from scripts.pipeline.config_loader import load_yaml
from scripts.pipeline.document_composer import compose_document
from scripts.pipeline.renderer import render_profile_report
from scripts.pipeline.encoding import read_text_with_encoding
from scripts.pipeline.extraction_merge import merge_extractions
from scripts.pipeline.extraction_prompt import (
    build_example_specs,
    build_prompt_description,
    to_langextract_examples,
)
from scripts.pipeline.jsonl_io import write_jsonl_objects
from scripts.pipeline.minimax_provider import build_model_config
from scripts.pipeline.template_profile import build_template_profile


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "assets" / "default-config.yaml"

ExtractFn = Callable[..., Any]
ModelConfigFn = Callable[..., Any]
ComposeFn = Callable[..., str]
VisualizeFn = Callable[..., None]


def run_extraction(
    *,
    template_path: Path,
    source_file: Path,
    output_dir: Path,
    config_path: Path = DEFAULT_CONFIG,
    model_id: str | None = None,
    extraction_passes: int | None = None,
    max_workers: int | None = None,
    max_char_buffer: int | None = None,
    limit_chars: int | None = None,
    dry_run: bool | None = None,
    generate_visualization: bool | None = None,
    extract_fn: ExtractFn | None = None,
    build_model_config_fn: ModelConfigFn = build_model_config,
    compose_fn: ComposeFn = compose_document,
    visualize_fn: VisualizeFn | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    config = load_yaml(config_path)
    extraction_config = _mapping(config.get("extraction"))
    encoding_config = _mapping(config.get("encoding"))
    model_id = model_id or str(extraction_config.get("model_id") or "MiniMax-M2.7")
    base_url = str(extraction_config.get("base_url") or "")
    passes = int(extraction_passes or extraction_config.get("extraction_passes") or 3)
    workers = int(max_workers or extraction_config.get("max_workers") or 4)
    buffer = int(max_char_buffer or extraction_config.get("max_char_buffer") or 1000)
    if passes < 1:
        raise ValueError("extraction_passes must be at least 1")
    if workers < 1:
        raise ValueError("max_workers must be at least 1")
    if buffer < 1:
        raise ValueError("max_char_buffer must be at least 1")
    limit = _override_int(limit_chars, extraction_config.get("limit_chars"))
    dry = _override_bool(dry_run, extraction_config.get("dry_run"))
    visualize = _override_bool(generate_visualization, extraction_config.get("generate_visualization"))
    compose_enabled = _override_bool(None, extraction_config.get("compose_enabled", True))
    output_dir.mkdir(parents=True, exist_ok=True)

    text, source_meta = read_text_with_encoding(
        source_file,
        candidates=[str(item) for item in encoding_config.get("fallbacks", ["utf-8-sig", "utf-8", "gb18030"])],
    )
    original_char_count = len(text)
    truncated = bool(limit and limit > 0 and len(text) > limit)
    if truncated:
        text = text[:limit]

    profile = build_template_profile(template_path)
    readme_text = _read_readme(template_path.parent)
    prompt = build_prompt_description(profile, readme_text)
    example_specs = build_example_specs(profile)
    chunk_count = math.ceil(len(text) / buffer) if text else 0
    composition_call_count = 1 if compose_enabled else 0
    chars_per_token = float(extraction_config.get("chars_per_token_estimate") or 2)
    if chars_per_token <= 0:
        raise ValueError("chars_per_token_estimate must be greater than 0")

    summary = {
        "template": str(template_path),
        "source_file": str(source_file),
        "model_id": model_id,
        "dry_run": dry,
        "source": {
            **source_meta,
            "original_char_count": original_char_count,
            "effective_char_count": len(text),
            "truncated": truncated,
            "limit_chars": limit or 0,
        },
        "parameters": {
            "extraction_passes": passes,
            "max_workers": workers,
            "max_char_buffer": buffer,
            "generate_visualization": visualize,
            "base_url": base_url,
        },
        "estimates": {
            "chunk_count": chunk_count,
            "call_count": chunk_count * passes,
            "composition_call_count": composition_call_count,
            "total_call_count": chunk_count * passes + composition_call_count,
            "token_estimate": math.ceil(len(text) / chars_per_token),
        },
        "counts": {"raw_extractions": 0, "grounded_extractions": 0, "merged_items": 0},
        "elapsed_seconds": 0.0,
        "outputs": {},
    }
    if dry:
        summary["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        _write_summary(output_dir, extraction_config, summary)
        return summary

    if not example_specs:
        raise ValueError(
            f"Template {template_path} did not provide usable few-shot examples; "
            "add example rows/cards before running LangExtract."
        )

    if extract_fn is None:
        extract_fn = _default_extract
    model_config = build_model_config_fn(model_id=model_id, base_url=base_url or None)
    result = extract_fn(
        text_or_documents=text,
        prompt_description=prompt,
        examples=to_langextract_examples(example_specs),
        config=model_config,
        extraction_passes=passes,
        max_workers=workers,
        max_char_buffer=buffer,
    )
    records = _records_from_result(result, template_path, source_file)
    grounded = [record for record in records if record["char_interval"] is not None]
    merged = merge_extractions(grounded, identity_field=profile.name_field)

    grounded_path = output_dir / str(extraction_config.get("grounded_jsonl_name") or "grounded-extractions.jsonl")
    merged_path = output_dir / str(extraction_config.get("merged_json_name") or "merged-extractions.json")
    write_jsonl_objects(grounded_path, grounded)
    merged_path.write_text(json.dumps({"items": merged}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if visualize:
        visualization_path = _write_visualization(result, output_dir, extraction_config, visualize_fn)
    else:
        visualization_path = None

    report_name = _format_report_name(
        str(extraction_config.get("report_name_pattern") or "{template_stem}.md"),
        profile.template_name,
        source_file,
    )
    report_path = output_dir / report_name
    provider_config = dict(getattr(model_config, "provider_kwargs", {}) or {})
    if compose_enabled:
        report = compose_fn(
            profile=profile,
            merged_items=merged,
            readme_text=readme_text,
            model_id=model_id,
            provider_config=provider_config,
            generation_config={
                "temperature": extraction_config.get("compose_temperature"),
                "max_tokens": extraction_config.get("compose_max_tokens"),
                "timeout_seconds": extraction_config.get("compose_timeout_seconds"),
            },
        )
    else:
        report = render_profile_report(profile.template_name.removesuffix("模板"), merged, {"report_shape": profile.report_shape})
    report_path.write_text(report, encoding="utf-8")

    summary["counts"] = {
        "raw_extractions": len(records),
        "grounded_extractions": len(grounded),
        "merged_items": len(merged),
    }
    summary["outputs"] = {
        "grounded_jsonl": str(grounded_path),
        "merged_json": str(merged_path),
        "report": str(report_path),
    }
    if visualization_path is not None:
        summary["outputs"]["visualization_html"] = str(visualization_path)
    summary["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    _write_summary(output_dir, extraction_config, summary)
    return summary


def _records_from_result(result: Any, template_path: Path, source_file: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for extraction in getattr(result, "extractions", []) or []:
        interval = getattr(extraction, "char_interval", None)
        interval_dict = None
        if interval is not None and interval.start_pos is not None and interval.end_pos is not None:
            interval_dict = {"start_pos": interval.start_pos, "end_pos": interval.end_pos}
        records.append(
            {
                "template": str(template_path),
                "source_file": str(source_file),
                "extraction_class": getattr(extraction, "extraction_class", ""),
                "extraction_text": getattr(extraction, "extraction_text", ""),
                "attributes": getattr(extraction, "attributes", {}) or {},
                "char_interval": interval_dict,
            }
        )
    return records


def _default_extract(**kwargs: Any) -> Any:
    try:
        import langextract as lx
    except ImportError as exc:
        raise RuntimeError("Missing LangExtract dependency. Install langextract[openai].") from exc
    return lx.extract(**kwargs)


def _write_visualization(
    result: Any,
    output_dir: Path,
    extraction_config: dict[str, Any],
    visualize_fn: VisualizeFn | None,
) -> Path:
    output_path = output_dir / str(extraction_config.get("visualization_html_name") or "visualization.html")
    if visualize_fn is not None:
        visualize_fn(result=result, output_path=output_path)
        return output_path
    try:
        import langextract as lx
    except ImportError as exc:
        raise RuntimeError("Missing LangExtract dependency. Install langextract[openai].") from exc
    raw_name = str(extraction_config.get("extraction_jsonl_name") or "langextract-results.jsonl")
    lx.io.save_annotated_documents([result], output_dir=output_dir, output_name=raw_name, show_progress=False)
    html_content = lx.visualize(str(output_dir / raw_name))
    output_path.write_text(
        html_content.data if hasattr(html_content, "data") else str(html_content),
        encoding="utf-8",
    )
    return output_path


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _override_int(value: int | None, configured: Any) -> int:
    if value is not None:
        return int(value)
    return int(configured or 0)


def _override_bool(value: bool | None, configured: Any) -> bool:
    if value is not None:
        return bool(value)
    return bool(configured)


def _read_readme(template_dir: Path) -> str:
    readme = template_dir / "README.md"
    if not readme.exists():
        return ""
    return readme.read_text(encoding="utf-8-sig")


def _format_report_name(pattern: str, template_name: str, source_file: Path) -> str:
    template_stem = template_name.removesuffix("模板")
    return pattern.format(
        template_name=template_name,
        template_stem=template_stem,
        source_stem=source_file.stem,
    )


def _write_summary(output_dir: Path, extraction_config: dict[str, Any], summary: dict[str, Any]) -> None:
    path = output_dir / str(extraction_config.get("run_summary_name") or "run-summary.json")
    summary["outputs"]["run_summary"] = str(path)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
