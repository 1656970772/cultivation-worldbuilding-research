from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pipeline.candidate_extractor import extract_candidates_from_text
from scripts.pipeline.config_loader import load_yaml
from scripts.pipeline.decision_draft import draft_decisions
from scripts.pipeline.decision_validator import (
    load_decision_records,
    resolve_review_workflow,
    validate_decision_records,
)
from scripts.pipeline.encoding import read_text_with_encoding
from scripts.pipeline.evidence_builder import build_evidence_pack
from scripts.pipeline.jsonl_io import write_jsonl_objects
from scripts.pipeline.merge_reviewed import (
    merge_reviewed_entries,
    read_decisions_jsonl,
    write_confirmed_outputs,
)
from scripts.pipeline.renderer import render_report
from scripts.pipeline.review_pack import (
    build_review_entries,
    load_curation_pack,
    write_review_pack,
)
from scripts.pipeline.review_shards import split_review_pack
from scripts.pipeline.rule_pack import load_rule_pack
from scripts.pipeline.segmenter import segment_text, write_jsonl
from scripts.pipeline.template_router import route_template
from scripts.pipeline.validator import validate_expected_present, validate_report


DEFAULT_CONFIG = ROOT / "assets" / "default-config.yaml"
DEFAULT_TEMPLATE_REGISTRY = ROOT / "assets" / "template-registry.yaml"
INSPECT_REPORT_NAME = "inspect-report.json"
ROUTE_REPORT_NAME = "route-report.json"
EVIDENCE_PACK_NAME = "evidence-pack.jsonl"
REVIEW_PACK_JSONL_NAME = "review-pack.jsonl"
REVIEW_PACK_MD_NAME = "review-pack.md"
REVIEW_DECISIONS_DRAFT_NAME = "review-decisions.draft.jsonl"
CONFIRMED_ITEMS_NAME = "confirmed-items.json"
CURATION_REPORT_NAME = "curation-report.json"
VALIDATION_REPORT_NAME = "validation-report.json"
DECISION_VALIDATION_REPORT_NAME = "decision-validation-report.json"


def _path(value: str | Path | None) -> Path | None:
    if value is None:
        return None
    return Path(value)


def _workdir(args: argparse.Namespace) -> Path:
    return Path(args.workdir)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not path.exists():
        raise FileNotFoundError(path)
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(f"JSONL line must be an object: {path}:{line_number}")
        items.append(item)
    return items


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    write_jsonl(items, path)


def _stdout_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False))


def _markdown_table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_markdown_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def _is_markdown_separator_row(line: str) -> bool:
    if not _is_markdown_table_row(line):
        return False
    cells = _markdown_table_cells(line)
    return bool(cells) and all(
        set(cell) <= {"-", ":", " "} and "-" in cell
        for cell in cells
    )


def _template_columns(template_path: Path | None) -> list[str]:
    if template_path is None:
        return []
    lines = template_path.read_text(encoding="utf-8").splitlines()
    for index in range(len(lines) - 1):
        header = lines[index].strip()
        separator = lines[index + 1].strip()
        if _is_markdown_table_row(header) and _is_markdown_separator_row(separator):
            return [cell for cell in _markdown_table_cells(header) if cell]
    return []


def _configured_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _nested_output(config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    output = config.get("output", {})
    return output if isinstance(output, dict) else {}


def _config_value(key: str, *configs: dict[str, Any] | None) -> Any:
    for config in configs:
        if not isinstance(config, dict):
            continue
        if key in config:
            return config[key]
        output = _nested_output(config)
        if key in output:
            return output[key]
    return None


def _load_optional_yaml(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return load_yaml(path)


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return _read_json(path)


def _derive_report_path(
    workdir: Path,
    confirmed_report: dict[str, Any],
    route_config: dict[str, Any] | None,
    default_config: dict[str, Any] | None,
) -> Path:
    report_config = confirmed_report.get("report_config", {})
    work_title = str(confirmed_report.get("work_title") or "report")
    subject_type = str(
        _config_value("subject_type", report_config, route_config, default_config)
        or ""
    )
    pattern = _config_value(
        "output_name_pattern",
        report_config,
        route_config,
        default_config,
    )
    if pattern:
        name = str(pattern).format(work_title=work_title, subject_type=subject_type)
    else:
        name = f"{work_title}.md"
    return workdir / name


def _default_route_path(workdir: Path) -> Path | None:
    path = workdir / ROUTE_REPORT_NAME
    return path if path.exists() else None


def _default_confirmed_path(workdir: Path) -> Path | None:
    path = workdir / "confirmed.json"
    return path if path.exists() else None


def cmd_inspect(args: argparse.Namespace) -> int:
    config = load_yaml(Path(args.config))
    template_path = _path(args.template)
    text, meta = read_text_with_encoding(
        Path(args.source),
        encoding=args.encoding,
        candidates=config.get("encoding", {}).get("fallbacks", []),
    )
    result = {
        "source": str(Path(args.source)),
        "encoding": meta["encoding"],
        "confidence": meta["confidence"],
        "line_count": meta["line_count"],
        "char_count": meta["char_count"],
        "replacement_count": meta["replacement_count"],
        "preview": text[: int(args.preview_chars)],
        "template_columns_found": _template_columns(template_path),
    }
    if template_path is not None:
        result["template"] = str(template_path)
    output = _path(args.output) or (_workdir(args) / INSPECT_REPORT_NAME)
    _write_json(output, result)
    _stdout_json({"output": str(output), **result})
    return 0


def cmd_segment(args: argparse.Namespace) -> int:
    config = load_yaml(Path(args.config))
    segmentation = config.get("segmentation", {})
    text, meta = read_text_with_encoding(
        Path(args.source),
        encoding=args.encoding,
        candidates=config.get("encoding", {}).get("fallbacks", []),
    )
    segments = segment_text(
        text,
        _configured_list(segmentation.get("chapter_patterns")),
        int(segmentation.get("max_chars_per_segment", 6000)),
        int(segmentation.get("overlap_chars", 300)),
    )
    output = _path(args.output) or (_workdir(args) / "segments.jsonl")
    _write_jsonl(output, segments)
    _stdout_json(
        {
            "output": str(output),
            "segments": len(segments),
            "encoding": meta["encoding"],
        }
    )
    return 0


def cmd_route_template(args: argparse.Namespace) -> int:
    route = route_template(
        Path(args.template_registry),
        Path(args.template),
        args.user_request,
    )
    output = _path(args.output) or (_workdir(args) / ROUTE_REPORT_NAME)
    _write_json(output, route)
    _stdout_json({"output": str(output), "template_name": route["template_name"]})
    return 0


def cmd_extract_candidates(args: argparse.Namespace) -> int:
    rules = load_rule_pack(Path(args.mode_rule), Path(args.rule_pack))
    segments_path = _path(args.segments) or (_workdir(args) / "segments.jsonl")
    segments = _read_jsonl(segments_path)
    candidates: list[dict[str, Any]] = []
    for segment in segments:
        candidates.extend(
            extract_candidates_from_text(
                str(segment.get("text", "")),
                rules,
                segment_id=str(segment.get("segment_id")),
                segment_start_char=int(segment.get("start_char", 0)),
            )
        )
    output = _path(args.output) or (_workdir(args) / "candidates.jsonl")
    _write_jsonl(output, candidates)
    _stdout_json({"output": str(output), "candidates": len(candidates)})
    return 0


def cmd_build_evidence(args: argparse.Namespace) -> int:
    workdir = _workdir(args)
    segments = _read_jsonl(_path(args.segments) or (workdir / "segments.jsonl"))
    candidates = _read_jsonl(_path(args.candidates) or (workdir / "candidates.jsonl"))
    evidence = build_evidence_pack(
        candidates,
        segments,
        context_chars=int(args.context_chars),
    )
    output = _path(args.output) or (workdir / EVIDENCE_PACK_NAME)
    _write_jsonl(output, evidence)
    _stdout_json({"output": str(output), "evidence": len(evidence)})
    return 0


def cmd_make_review_pack(args: argparse.Namespace) -> int:
    workdir = _workdir(args)
    candidates = _read_jsonl(
        _path(args.candidates) or (workdir / "candidates.jsonl")
    )
    evidence = _read_jsonl(_path(args.evidence) or (workdir / EVIDENCE_PACK_NAME))
    curation = load_curation_pack(Path(args.curation))
    entries = build_review_entries(candidates, evidence, curation)
    output_jsonl = _path(args.output_jsonl) or (workdir / REVIEW_PACK_JSONL_NAME)
    output_md = _path(args.output_md) or (workdir / REVIEW_PACK_MD_NAME)
    write_review_pack(entries, output_jsonl, output_md)
    _stdout_json(
        {
            "output_jsonl": str(output_jsonl),
            "output_md": str(output_md),
            "entries": len(entries),
        }
    )
    return 0


def cmd_split_review_pack(args: argparse.Namespace) -> int:
    workdir = _workdir(args)
    workflow = None
    if args.curation is not None:
        workflow = resolve_review_workflow(load_yaml(Path(args.curation)))

    entries_per_shard = args.entries_per_shard
    if entries_per_shard is None:
        entries_per_shard = workflow.entries_per_shard if workflow is not None else 60

    review_pack = _path(args.review_pack) or (workdir / REVIEW_PACK_JSONL_NAME)
    if args.parts_dir is not None:
        parts_dir = Path(args.parts_dir)
    elif workflow is not None:
        parts_dir = workdir / workflow.part_dir
    else:
        parts_dir = workdir / "review-decisions.parts"
    manifest_path = _path(args.manifest)

    manifest = split_review_pack(
        review_pack,
        parts_dir,
        entries_per_shard=entries_per_shard,
        manifest_path=manifest_path,
    )
    output_manifest = manifest_path or (parts_dir / "review-shard-manifest.json")
    _stdout_json(
        {
            "manifest": str(output_manifest),
            "parts_dir": str(parts_dir),
            "shards": len(manifest["shards"]),
            "total_entries": manifest["total_entries"],
        }
    )
    return 0


def cmd_draft_decisions(args: argparse.Namespace) -> int:
    workdir = _workdir(args)
    curation = load_yaml(Path(args.curation)) if args.curation else {}
    workflow = resolve_review_workflow(curation)
    review_pack = _path(args.review_pack) or (workdir / REVIEW_PACK_JSONL_NAME)
    mode = args.mode or workflow.draft_mode
    output = _path(args.output) or (workdir / REVIEW_DECISIONS_DRAFT_NAME)
    review_entries = _read_jsonl(review_pack)
    review_workflow = curation.get("review_workflow") or {}
    if not isinstance(review_workflow, dict):
        raise ValueError("review_workflow must be a mapping")
    decisions = draft_decisions(
        review_entries,
        mode=mode,
        allowed_auto_safe=bool(review_workflow.get("allow_auto_safe_draft", False)),
    )
    write_jsonl_objects(output, decisions)
    _stdout_json({"output": str(output), "count": len(decisions), "mode": mode})
    return 0


def cmd_merge_reviewed(args: argparse.Namespace) -> int:
    workdir = _workdir(args)
    review_pack = _path(args.review_pack) or (workdir / REVIEW_PACK_JSONL_NAME)
    review_entries = _read_jsonl(review_pack)
    decisions = read_decisions_jsonl(Path(args.decisions))
    curation = load_curation_pack(Path(args.curation))
    report_config = {}
    if curation.get("subject_type"):
        report_config["subject_type"] = curation["subject_type"]
    confirmed, report = merge_reviewed_entries(
        review_entries,
        decisions,
        curation,
        report_config,
    )
    output_confirmed = _path(args.output_confirmed) or (workdir / CONFIRMED_ITEMS_NAME)
    output_report = _path(args.output_report) or (workdir / CURATION_REPORT_NAME)
    write_confirmed_outputs(confirmed, report, output_confirmed, output_report)
    _stdout_json(
        {
            "output_confirmed": str(output_confirmed),
            "output_report": str(output_report),
            "confirmed": len(confirmed.get("items", [])),
            "report": report,
        }
    )
    return 0


def cmd_validate_decisions(args: argparse.Namespace) -> int:
    workdir = _workdir(args)
    review_pack = _path(args.review_pack) or (workdir / REVIEW_PACK_JSONL_NAME)
    output = _path(args.output) or (workdir / DECISION_VALIDATION_REPORT_NAME)
    review_entries = _read_jsonl(review_pack)
    decision_records = load_decision_records(Path(args.decisions))
    curation = load_yaml(Path(args.curation))
    expected = _load_optional_yaml(_path(args.expected))
    report = validate_decision_records(
        review_entries,
        decision_records,
        curation,
        expected,
    )
    _write_json(output, report)
    _stdout_json(
        {
            "output": str(output),
            "passed": report["passed"],
            "counts": report["counts"],
        }
    )
    return 0 if report["passed"] else 1


def cmd_render(args: argparse.Namespace) -> int:
    workdir = _workdir(args)
    confirmed = _read_json(Path(args.confirmed))
    route = _load_optional_json(_path(args.route) or _default_route_path(workdir))
    defaults = _load_optional_yaml(_path(args.default_config))
    output = _path(args.output) or _derive_report_path(
        workdir,
        confirmed,
        route,
        defaults,
    )
    render_report(confirmed, output, route_config=route, default_config=defaults)
    _stdout_json({"output": str(output)})
    return 0


def _merge_coverage_warnings(
    base: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    coverage = dict(merged.get("coverage_warnings", {}))
    coverage.update(extra.get("coverage_warnings", {}))
    merged["coverage_warnings"] = coverage
    return merged


def cmd_validate(args: argparse.Namespace) -> int:
    workdir = _workdir(args)
    expected = _load_optional_yaml(_path(args.expected))
    route = _load_optional_json(_path(args.route) or _default_route_path(workdir))
    defaults = _load_optional_yaml(_path(args.default_config))
    confirmed_path = _path(args.confirmed) or _default_confirmed_path(workdir)
    confirmed = _load_optional_json(confirmed_path)
    report_path = _path(args.report)
    if report_path is None:
        if confirmed is None:
            report_path = workdir / "report.md"
        else:
            report_path = _derive_report_path(workdir, confirmed, route, defaults)

    required_columns = _configured_list(
        _config_value("required_columns", expected, route, defaults)
    )
    forbidden_names = _configured_list(
        _config_value("forbidden_names", expected)
    )
    result = validate_report(report_path, required_columns, forbidden_names)

    if expected and expected.get("expected_present") and confirmed:
        result = _merge_coverage_warnings(
            result,
            validate_expected_present(confirmed, expected),
        )

    output = _path(args.output) or (workdir / VALIDATION_REPORT_NAME)
    _write_json(output, result)
    _stdout_json({"output": str(output), **result})
    return 0 if result["passed"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the configurable worldbuilding extraction pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_workdir(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--workdir",
            type=Path,
            default=Path.cwd(),
            help="Directory for default pipeline inputs and outputs.",
        )

    def add_ignored_path_args(
        command: argparse.ArgumentParser,
        *option_strings: str,
    ) -> None:
        for option_string in option_strings:
            command.add_argument(option_string, type=Path, help=argparse.SUPPRESS)

    inspect = subparsers.add_parser("inspect", help="Inspect source text encoding.")
    add_workdir(inspect)
    inspect.add_argument("--source", "--input", dest="source", required=True, type=Path)
    inspect.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    inspect.add_argument("--template", type=Path)
    inspect.add_argument("--encoding")
    inspect.add_argument("--preview-chars", type=int, default=200)
    inspect.add_argument("--output", type=Path)
    inspect.set_defaults(func=cmd_inspect)

    segment = subparsers.add_parser("segment", help="Split source text into segments.")
    add_workdir(segment)
    segment.add_argument("--source", "--input", dest="source", required=True, type=Path)
    segment.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    segment.add_argument("--encoding")
    segment.add_argument("--output", type=Path)
    add_ignored_path_args(segment, "--template")
    segment.set_defaults(func=cmd_segment)

    route = subparsers.add_parser(
        "route-template",
        help="Resolve template metadata from the registry.",
    )
    add_workdir(route)
    route.add_argument("--template", required=True, type=Path)
    route.add_argument(
        "--template-registry",
        "--registry",
        dest="template_registry",
        type=Path,
        default=DEFAULT_TEMPLATE_REGISTRY,
    )
    route.add_argument("--user-request", "--request", dest="user_request", default="")
    add_ignored_path_args(route, "--config", "--input")
    route.add_argument("--output", type=Path)
    route.set_defaults(func=cmd_route_template)

    extract = subparsers.add_parser(
        "extract-candidates",
        help="Extract candidates from segments.",
    )
    add_workdir(extract)
    extract.add_argument("--mode-rule", required=True, type=Path)
    extract.add_argument("--rule-pack", required=True, type=Path)
    extract.add_argument("--segments", type=Path)
    add_ignored_path_args(extract, "--config", "--input", "--template")
    extract.add_argument("--output", type=Path)
    extract.set_defaults(func=cmd_extract_candidates)

    evidence = subparsers.add_parser(
        "build-evidence",
        help="Build evidence entries from candidates and segments.",
    )
    add_workdir(evidence)
    evidence.add_argument("--segments", type=Path)
    evidence.add_argument("--candidates", type=Path)
    evidence.add_argument("--context-chars", type=int, default=80)
    add_ignored_path_args(evidence, "--config", "--input", "--template")
    evidence.add_argument("--output", type=Path)
    evidence.set_defaults(func=cmd_build_evidence)

    review = subparsers.add_parser(
        "make-review-pack",
        help="Build review entries for curation.",
    )
    add_workdir(review)
    review.add_argument("--candidates", type=Path)
    review.add_argument("--evidence", type=Path)
    review.add_argument("--curation", required=True, type=Path)
    review.add_argument("--output-jsonl", type=Path)
    review.add_argument("--output-md", type=Path)
    review.set_defaults(func=cmd_make_review_pack)

    split_review = subparsers.add_parser(
        "split-review-pack",
        help="Split review pack entries into review shards.",
    )
    add_workdir(split_review)
    split_review.add_argument("--review-pack", type=Path)
    split_review.add_argument("--curation", type=Path)
    split_review.add_argument("--entries-per-shard", type=int)
    split_review.add_argument("--parts-dir", type=Path)
    split_review.add_argument("--manifest", type=Path)
    split_review.set_defaults(func=cmd_split_review_pack)

    draft = subparsers.add_parser(
        "draft-decisions",
        help="Draft review decisions from a review pack.",
    )
    add_workdir(draft)
    draft.add_argument("--review-pack", type=Path)
    draft.add_argument("--curation", type=Path)
    draft.add_argument(
        "--mode",
        choices=["scaffold", "suggestions", "auto-safe"],
    )
    draft.add_argument("--output", type=Path)
    draft.set_defaults(func=cmd_draft_decisions)

    merge = subparsers.add_parser(
        "merge-reviewed",
        help="Merge reviewed decisions into confirmed curation outputs.",
    )
    add_workdir(merge)
    merge.add_argument("--review-pack", type=Path)
    merge.add_argument("--decisions", required=True, type=Path)
    merge.add_argument("--curation", required=True, type=Path)
    merge.add_argument("--output-confirmed", type=Path)
    merge.add_argument("--output-report", type=Path)
    merge.set_defaults(func=cmd_merge_reviewed)

    validate_decisions = subparsers.add_parser(
        "validate-decisions",
        help="Validate review decision JSONL before merge.",
    )
    add_workdir(validate_decisions)
    validate_decisions.add_argument("--review-pack", type=Path)
    validate_decisions.add_argument("--decisions", required=True, type=Path)
    validate_decisions.add_argument("--curation", required=True, type=Path)
    validate_decisions.add_argument("--expected", type=Path)
    validate_decisions.add_argument("--output", type=Path)
    validate_decisions.set_defaults(func=cmd_validate_decisions)

    render = subparsers.add_parser("render", help="Render a confirmed report.")
    add_workdir(render)
    render.add_argument("--confirmed", required=True, type=Path)
    render.add_argument("--route", type=Path)
    render.add_argument(
        "--default-config",
        "--config",
        dest="default_config",
        type=Path,
        default=DEFAULT_CONFIG,
    )
    add_ignored_path_args(render, "--template", "--registry")
    render.add_argument("--output", type=Path)
    render.set_defaults(func=cmd_render)

    validate = subparsers.add_parser("validate", help="Validate a rendered report.")
    add_workdir(validate)
    validate.add_argument("--report", type=Path)
    validate.add_argument("--expected", type=Path)
    validate.add_argument("--confirmed", type=Path)
    validate.add_argument("--route", type=Path)
    validate.add_argument(
        "--default-config",
        "--config",
        dest="default_config",
        type=Path,
        default=DEFAULT_CONFIG,
    )
    validate.add_argument("--output", type=Path)
    validate.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func: Callable[[argparse.Namespace], int] = args.func
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
