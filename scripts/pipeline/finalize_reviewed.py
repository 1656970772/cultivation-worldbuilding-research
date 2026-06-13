from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.pipeline.config_loader import load_yaml
from scripts.pipeline.confirmed_audit import audit_confirmed
from scripts.pipeline.decision_validator import (
    load_decision_records,
    validate_decision_records,
)
from scripts.pipeline.jsonl_io import read_jsonl_objects
from scripts.pipeline.merge_reviewed import (
    merge_reviewed_entries,
    write_confirmed_outputs,
)
from scripts.pipeline.renderer import render_report
from scripts.pipeline.validator import validate_expected_present, validate_report


CONFIRMED_ITEMS_NAME = "confirmed-items.json"
CURATION_REPORT_NAME = "curation-report.json"
DECISION_VALIDATION_REPORT_NAME = "decision-validation-report.json"
VALIDATION_REPORT_NAME = "validation-report.json"
CONFIRMED_AUDIT_REPORT_NAME = "confirmed-audit-report.json"


PIPELINE_STEPS = [
    "validate-decisions",
    "merge-reviewed",
    "render",
    "validate",
    "audit-confirmed",
]


def finalize_reviewed(
    *,
    workdir: Path,
    review_pack: Path,
    decisions: Path,
    curation: Path,
    default_config: Path,
    expected: Path | None,
    template: Path | None,
    route: Path | None,
    output_report: Path | None,
    run_manifest: Path,
) -> dict[str, Any]:
    workdir = Path(workdir)
    review_pack = Path(review_pack)
    decisions = Path(decisions)
    curation = Path(curation)
    default_config = Path(default_config)
    expected = Path(expected) if expected is not None else None
    template = Path(template) if template is not None else None
    route = Path(route) if route is not None else None
    run_manifest = Path(run_manifest)

    decision_validation_report = workdir / DECISION_VALIDATION_REPORT_NAME
    confirmed_path = workdir / CONFIRMED_ITEMS_NAME
    curation_report_path = workdir / CURATION_REPORT_NAME
    validation_report_path = workdir / VALIDATION_REPORT_NAME
    audit_report_path = workdir / CONFIRMED_AUDIT_REPORT_NAME

    counts = _empty_counts()
    steps: list[dict[str, Any]] = []
    produced_outputs: set[str] = set()

    def finish(
        *,
        passed: bool,
        failed_step: str | None = None,
        report_path: Path | None = output_report,
    ) -> dict[str, Any]:
        outputs = _output_records(
            decision_validation=decision_validation_report,
            confirmed=confirmed_path,
            curation_report=curation_report_path,
            report=report_path,
            validation=validation_report_path,
            audit=audit_report_path,
            run_manifest=run_manifest,
            produced_outputs=produced_outputs,
        )
        manifest = _build_manifest(
            review_pack=review_pack,
            decisions=decisions,
            curation=curation,
            default_config=default_config,
            expected=expected,
            template=template,
            route=route,
            outputs=outputs,
            counts=counts,
            steps=steps,
            passed=passed,
            failed_step=failed_step,
        )
        _write_json(run_manifest, manifest)
        return _result(
            passed=passed,
            run_manifest=run_manifest,
            confirmed=confirmed_path,
            report=report_path,
            audit=audit_report_path,
            failed_step=failed_step,
            produced_outputs=produced_outputs,
        )

    try:
        curation_config = load_yaml(curation)
        default_config_data = load_yaml(default_config)
        expected_config = load_yaml(expected) if expected is not None else None
        route_config = _load_optional_json(route)
        review_entries = read_jsonl_objects(review_pack)
        decision_records = load_decision_records(decisions)
    except Exception as exc:  # noqa: BLE001 - convert setup errors into reports.
        prepare_result = _exception_report("prepare", exc)
        _record_step(steps, "prepare", prepare_result)
        _add_issue_counts(counts, prepare_result)
        return finish(passed=False, failed_step="prepare")

    decision_rows = [record.data for record in decision_records]
    counts.update(_initial_counts(review_entries, decision_rows))

    decision_validation = validate_decision_records(
        review_entries,
        decision_records,
        curation_config,
        expected_config,
    )
    _write_json(decision_validation_report, decision_validation)
    produced_outputs.add("decision_validation")
    _record_step(steps, "validate-decisions", decision_validation)
    _add_issue_counts(counts, decision_validation)
    if not decision_validation["passed"]:
        return finish(passed=False, failed_step="validate-decisions")

    report_config = {}
    if curation_config.get("subject_type"):
        report_config["subject_type"] = curation_config["subject_type"]
    try:
        confirmed, curation_report = merge_reviewed_entries(
            review_entries,
            decision_rows,
            curation_config,
            report_config,
        )
    except Exception as exc:  # noqa: BLE001 - convert pipeline step errors into reports.
        curation_report = _exception_report("merge-reviewed", exc)
        _write_json(curation_report_path, curation_report)
        produced_outputs.add("curation_report")
        _record_step(steps, "merge-reviewed", curation_report)
        _add_issue_counts(counts, curation_report)
        return finish(passed=False, failed_step="merge-reviewed")

    write_confirmed_outputs(
        confirmed,
        curation_report,
        confirmed_path,
        curation_report_path,
    )
    produced_outputs.update({"confirmed", "curation_report"})
    counts["confirmed_items"] = len(confirmed.get("items", []))
    _record_step(steps, "merge-reviewed", curation_report)
    _add_issue_counts(counts, curation_report)
    if curation_report["counts"].get("blocking_errors", 0):
        return finish(passed=False, failed_step="merge-reviewed")

    try:
        report_path = output_report or _derive_report_path(
            workdir,
            confirmed,
            route_config,
            default_config_data,
        )
    except Exception as exc:  # noqa: BLE001 - convert output path errors into reports.
        render_result = _exception_report("render", exc)
        _record_step(steps, "render", render_result)
        _add_issue_counts(counts, render_result)
        return finish(passed=False, failed_step="render", report_path=output_report)

    try:
        render_report(
            confirmed,
            report_path,
            route_config=route_config,
            default_config=default_config_data,
        )
    except Exception as exc:  # noqa: BLE001 - convert pipeline step errors into reports.
        render_result = _exception_report("render", exc)
        _record_step(steps, "render", render_result)
        _add_issue_counts(counts, render_result)
        return finish(passed=False, failed_step="render", report_path=report_path)
    render_result = {"passed": True, "counts": {}, "blocking_errors": [], "warnings": []}
    produced_outputs.add("report")
    _record_step(steps, "render", render_result)

    validation_result = _validate_final_report(
        report_path,
        confirmed,
        expected_config,
        route_config,
        default_config_data,
    )
    _write_json(validation_report_path, validation_result)
    produced_outputs.add("validation")
    _record_step(steps, "validate", validation_result)
    _add_issue_counts(counts, validation_result)
    if not validation_result["passed"]:
        return finish(passed=False, failed_step="validate", report_path=report_path)

    try:
        audit_config = _confirmed_audit_config(curation_config)
        audit_config["required_fields"] = _derive_confirmed_audit_required_fields(
            confirmed,
            curation_config,
        )
        audit_result = audit_confirmed(
            confirmed,
            expected=expected_config,
            markdown_text=report_path.read_text(encoding="utf-8-sig"),
            config=audit_config,
        )
    except Exception as exc:  # noqa: BLE001 - convert audit errors into reports.
        audit_result = _exception_report("audit-confirmed", exc)
        _write_json(audit_report_path, audit_result)
        produced_outputs.add("audit")
        _record_step(steps, "audit-confirmed", audit_result)
        _add_issue_counts(counts, audit_result)
        return finish(
            passed=False,
            failed_step="audit-confirmed",
            report_path=report_path,
        )
    _write_json(audit_report_path, audit_result)
    produced_outputs.add("audit")
    _record_step(steps, "audit-confirmed", audit_result)
    _add_issue_counts(counts, audit_result)
    if not audit_result["passed"]:
        return finish(
            passed=False,
            failed_step="audit-confirmed",
            report_path=report_path,
        )

    return finish(passed=True, report_path=report_path)


def merge_validation_results(
    report_result: Mapping[str, Any],
    expected_result: Mapping[str, Any],
) -> dict[str, Any]:
    blocking_errors = [
        *_configured_issue_list(report_result.get("blocking_errors")),
        *_configured_issue_list(expected_result.get("blocking_errors")),
    ]
    coverage_warnings = _merge_warning_maps(
        _mapping(report_result.get("coverage_warnings")),
        _mapping(expected_result.get("coverage_warnings")),
    )
    warnings = [
        *_configured_issue_list(report_result.get("warnings")),
        *_configured_issue_list(expected_result.get("warnings")),
    ]
    merged = dict(report_result)
    merged["blocking_errors"] = blocking_errors
    merged["coverage_warnings"] = coverage_warnings
    if warnings:
        merged["warnings"] = warnings
    merged["passed"] = (
        bool(report_result.get("passed", not blocking_errors))
        and bool(expected_result.get("passed", True))
        and not blocking_errors
    )
    return merged


def _validate_final_report(
    report_path: Path,
    confirmed: dict[str, Any],
    expected: dict[str, Any] | None,
    route_config: dict[str, Any] | None,
    default_config: dict[str, Any] | None,
) -> dict[str, Any]:
    required_columns = _configured_list(
        _config_value("required_columns", expected, route_config, default_config)
    )
    forbidden_names = _configured_list(_config_value("forbidden_names", expected))
    result = validate_report(report_path, required_columns, forbidden_names)
    if expected and expected.get("expected_present"):
        result = merge_validation_results(
            result,
            validate_expected_present(confirmed, expected),
        )
    return result


def _empty_counts() -> dict[str, int]:
    return {
        "review_entries": 0,
        "decisions": 0,
        "confirmed_decisions": 0,
        "confirmed_items": 0,
        "blocking_errors": 0,
        "warnings": 0,
    }


def _initial_counts(
    review_entries: list[dict[str, Any]],
    decision_rows: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "review_entries": len(review_entries),
        "decisions": len(decision_rows),
        "confirmed_decisions": sum(
            1 for row in decision_rows if str(row.get("decision", "")).strip() == "confirmed"
        ),
        "confirmed_items": 0,
        "blocking_errors": 0,
        "warnings": 0,
    }


def _record_step(
    steps: list[dict[str, Any]],
    name: str,
    report: Mapping[str, Any],
) -> None:
    step = {
        "name": name,
        "passed": _report_passed(report),
        "counts": dict(_mapping(report.get("counts"))),
    }
    if "blocking_errors" in report:
        step["blocking_errors"] = _list_details(report.get("blocking_errors"))
    if "warnings" in report:
        step["warnings"] = _list_details(report.get("warnings"))
    coverage_warnings = _mapping(report.get("coverage_warnings"))
    if coverage_warnings:
        step["coverage_warnings"] = dict(coverage_warnings)
    steps.append(step)


def _list_details(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [dict(item) if isinstance(item, Mapping) else item for item in value]


def _report_passed(report: Mapping[str, Any]) -> bool:
    if "passed" in report:
        return bool(report["passed"])
    return _blocking_error_count(report) == 0


def _add_issue_counts(counts: dict[str, int], report: Mapping[str, Any]) -> None:
    counts["blocking_errors"] += _blocking_error_count(report)
    counts["warnings"] += _warning_count(report)


def _blocking_error_count(report: Mapping[str, Any]) -> int:
    blocking_errors = report.get("blocking_errors")
    if isinstance(blocking_errors, list):
        return len(blocking_errors)
    counts = report.get("counts")
    if isinstance(counts, Mapping):
        return int(counts.get("blocking_errors", 0))
    return 0


def _warning_count(report: Mapping[str, Any]) -> int:
    warnings = report.get("warnings")
    total = len(warnings) if isinstance(warnings, list) else 0
    total += _coverage_warning_count(_mapping(report.get("coverage_warnings")))
    if total:
        return total
    counts = report.get("counts")
    if isinstance(counts, Mapping):
        return int(counts.get("warnings", 0))
    return 0


def _coverage_warning_count(coverage: Mapping[str, Any]) -> int:
    total = 0
    for value in coverage.values():
        if isinstance(value, list):
            total += len(value)
        elif value:
            total += 1
    return total


def _build_manifest(
    *,
    review_pack: Path,
    decisions: Path,
    curation: Path,
    default_config: Path,
    expected: Path | None,
    template: Path | None,
    route: Path | None,
    outputs: Mapping[str, Any],
    counts: Mapping[str, int],
    steps: list[dict[str, Any]],
    passed: bool,
    failed_step: str | None,
) -> dict[str, Any]:
    inputs = {
        "review_pack": _path_record(review_pack),
        "decisions": _path_record(decisions),
        "curation": _path_record(curation),
        "default_config": _path_record(default_config),
        "expected": _path_record(expected),
        "template": _path_record(template),
        "route": _path_record(route),
    }
    manifest = {
        "schema_version": 1,
        "inputs": inputs,
        "outputs": dict(outputs),
        "counts": dict(counts),
        "checksums": {
            "inputs": _checksums(inputs),
            "outputs": _checksums(outputs),
        },
        "steps": steps,
        "passed": passed,
    }
    if failed_step is not None:
        manifest["failed_step"] = failed_step
    return manifest


def _result(
    *,
    passed: bool,
    run_manifest: Path,
    confirmed: Path,
    report: Path | None,
    audit: Path,
    failed_step: str | None,
    produced_outputs: set[str],
) -> dict[str, Any]:
    result = {
        "passed": passed,
        "run_manifest": str(run_manifest),
        "confirmed": _produced_path_string("confirmed", confirmed, produced_outputs),
        "report": _produced_path_string("report", report, produced_outputs),
        "audit": _produced_path_string("audit", audit, produced_outputs),
    }
    if failed_step is not None:
        result["failed_step"] = failed_step
    return result


def _output_records(
    *,
    decision_validation: Path,
    confirmed: Path,
    curation_report: Path,
    report: Path | None,
    validation: Path,
    audit: Path,
    run_manifest: Path,
    produced_outputs: set[str],
) -> dict[str, Any]:
    return {
        "decision_validation": _output_record(
            decision_validation,
            "decision_validation" in produced_outputs,
        ),
        "confirmed": _output_record(confirmed, "confirmed" in produced_outputs),
        "curation_report": _output_record(
            curation_report,
            "curation_report" in produced_outputs,
        ),
        "report": _output_record(report, "report" in produced_outputs),
        "validation": _output_record(validation, "validation" in produced_outputs),
        "audit": _output_record(audit, "audit" in produced_outputs),
        "run_manifest": _run_manifest_record(run_manifest),
    }


def _output_record(path: Path | None, produced: bool) -> dict[str, Any] | None:
    record = _path_record(path, include_sha256=produced)
    if record is None:
        return None
    record["produced"] = produced
    return record


def _path_record(
    path: Path | None,
    *,
    include_sha256: bool = True,
) -> dict[str, Any] | None:
    if path is None:
        return None
    exists = path.exists()
    return {
        "path": str(path),
        "exists": exists,
        "sha256": (
            _sha256(path) if include_sha256 and exists and path.is_file() else None
        ),
    }


def _run_manifest_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": True,
        "sha256": None,
    }


def _produced_path_string(
    name: str,
    path: Path | None,
    produced_outputs: set[str],
) -> str | None:
    if name not in produced_outputs or path is None or not path.exists():
        return None
    return str(path)


def _checksums(records: Mapping[str, Any]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for name, record in records.items():
        if (
            isinstance(record, Mapping)
            and record.get("sha256")
            and record.get("produced", True)
        ):
            checksums[name] = str(record["sha256"])
    return checksums


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(data), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def _derive_report_path(
    workdir: Path,
    confirmed_report: dict[str, Any],
    route_config: dict[str, Any] | None,
    default_config: dict[str, Any] | None,
) -> Path:
    report_config = _mapping(confirmed_report.get("report_config"))
    work_title = str(confirmed_report.get("work_title") or "report")
    subject_type = str(
        _config_value("subject_type", report_config, route_config, default_config) or ""
    )
    pattern = _config_value(
        "output_name_pattern",
        report_config,
        route_config,
        default_config,
    )
    if pattern:
        return workdir / str(pattern).format(
            work_title=work_title,
            subject_type=subject_type,
        )
    return workdir / f"{work_title}.md"


def _config_value(key: str, *configs: Mapping[str, Any] | None) -> Any:
    for config in configs:
        if not isinstance(config, Mapping):
            continue
        if key in config:
            return config[key]
        output = config.get("output", {})
        if isinstance(output, Mapping) and key in output:
            return output[key]
    return None


def _confirmed_audit_config(curation: Mapping[str, Any] | None) -> dict[str, Any]:
    if curation is None:
        return {}
    if "confirmed_audit" not in curation:
        return {}
    config = curation["confirmed_audit"]
    if not isinstance(config, dict):
        raise ValueError("confirmed_audit must be a mapping")
    return dict(config)


def _derive_confirmed_audit_required_fields(
    confirmed: Mapping[str, Any],
    curation: Mapping[str, Any] | None,
) -> list[str]:
    if curation is not None:
        fields = _mapping(curation.get("fields"))
        required_fields = _non_empty_configured_list(fields.get("required"))
        if required_fields:
            return required_fields
    report_config = _mapping(confirmed.get("report_config"))
    return _configured_list(report_config.get("required_columns"))


def _non_empty_configured_list(value: Any) -> list[str]:
    return [item for item in _configured_list(value) if item.strip()]


def _configured_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _configured_issue_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _merge_warning_maps(
    base: Mapping[str, Any],
    extra: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if key not in merged:
            merged[key] = value
            continue
        existing = merged[key]
        if isinstance(existing, list) and isinstance(value, list):
            merged[key] = [*existing, *[item for item in value if item not in existing]]
        else:
            merged[key] = value
    return merged


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _exception_report(step: str, exc: Exception) -> dict[str, Any]:
    return {
        "passed": False,
        "counts": {"blocking_errors": 1, "warnings": 0},
        "blocking_errors": [
            {
                "type": f"{step}_failed",
                "message": str(exc),
            }
        ],
        "warnings": [],
    }
