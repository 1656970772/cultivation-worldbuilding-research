from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class DecisionRecord:
    path: str
    line: int
    shard: str | None
    data: dict[str, Any]


@dataclass(frozen=True)
class ReviewWorkflowConfig:
    entries_per_shard: int
    part_dir: str
    require_complete_parts: bool
    draft_mode: str
    allowed_decisions: Sequence[str]
    require_all_review_ids: bool
    expected_present_blocking: bool
    require_confirmed_source_spans: bool
    forbidden_confirmed_names: Sequence[str]
    required_field_policy: str
    checksum_algorithm: str


def resolve_review_workflow(curation: Mapping[str, Any]) -> ReviewWorkflowConfig:
    workflow = curation.get("review_workflow") or {}
    validation = curation.get("decision_validation") or {}

    if not isinstance(workflow, Mapping):
        raise ValueError("review_workflow must be a mapping")
    if not isinstance(validation, Mapping):
        raise ValueError("decision_validation must be a mapping")

    entries_per_shard = int(workflow.get("entries_per_shard", 60))
    if entries_per_shard < 1:
        raise ValueError("review_workflow.entries_per_shard must be >= 1")

    part_dir = str(workflow.get("part_dir", "review-decisions.parts")).strip()
    if not part_dir:
        raise ValueError("review_workflow.part_dir must not be empty")

    require_complete_parts = bool(workflow.get("require_complete_parts", True))
    draft_mode = str(workflow.get("draft_mode", "scaffold")).strip()
    if draft_mode not in {"scaffold", "suggestions", "auto-safe"}:
        raise ValueError("review_workflow.draft_mode must be scaffold, suggestions, or auto-safe")

    allowed_raw = validation.get("allowed_decisions", ["confirmed", "rejected", "needs-review"])
    if not isinstance(allowed_raw, Sequence) or isinstance(allowed_raw, (str, bytes)):
        raise ValueError("decision_validation.allowed_decisions must be a list")
    allowed_decisions = tuple(str(item).strip() for item in allowed_raw if str(item).strip())
    if not allowed_decisions:
        raise ValueError("decision_validation.allowed_decisions must not be empty")

    required_field_policy = str(validation.get("required_field_policy", "fill_unknown")).strip()
    if required_field_policy not in {"fill_unknown", "warn", "block"}:
        raise ValueError("decision_validation.required_field_policy must be fill_unknown, warn, or block")

    checksum_algorithm = str(workflow.get("checksum_algorithm", "sha256")).strip().lower()
    if checksum_algorithm != "sha256":
        raise ValueError("review_workflow.checksum_algorithm currently supports sha256")

    return ReviewWorkflowConfig(
        entries_per_shard=entries_per_shard,
        part_dir=part_dir,
        require_complete_parts=require_complete_parts,
        draft_mode=draft_mode,
        allowed_decisions=allowed_decisions,
        require_all_review_ids=bool(validation.get("require_all_review_ids", True)),
        expected_present_blocking=bool(validation.get("expected_present_blocking", False)),
        require_confirmed_source_spans=bool(
            validation.get("require_confirmed_source_spans", True)
        ),
        forbidden_confirmed_names=tuple(
            _string_list(validation.get("forbidden_confirmed_names"))
        ),
        required_field_policy=required_field_policy,
        checksum_algorithm=checksum_algorithm,
    )


def load_decision_records(path: Path, *, shard: str | None = None) -> list[DecisionRecord]:
    records: list[DecisionRecord] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                data = {"__invalid_json__": str(exc)}
            else:
                if isinstance(parsed, dict):
                    data = parsed
                else:
                    data = {"__non_object_line__": parsed}
            records.append(
                DecisionRecord(
                    path=str(path),
                    line=line_number,
                    shard=shard,
                    data=data,
                )
            )
    return records


def validate_decisions(
    review_entries: Sequence[Mapping[str, Any]],
    decisions: Sequence[Mapping[str, Any]],
    curation: Mapping[str, Any],
    expected: Mapping[str, Any] | None,
) -> dict[str, Any]:
    records = [
        DecisionRecord(
            path="<memory>",
            line=index,
            shard=None,
            data=dict(decision),
        )
        for index, decision in enumerate(decisions, 1)
    ]
    return validate_decision_records(review_entries, records, curation, expected)


def validate_decision_records(
    review_entries: Sequence[Mapping[str, Any]],
    decision_records: Sequence[DecisionRecord],
    curation: Mapping[str, Any],
    expected: Mapping[str, Any] | None,
) -> dict[str, Any]:
    workflow = resolve_review_workflow(curation)
    expected = expected or {}
    review_by_id = _review_entries_by_id(review_entries)
    required_fields = _required_fields(curation, review_entries)
    blocking_errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    repair_hints: list[dict[str, Any]] = []
    seen_records: dict[str, DecisionRecord] = {}
    seen_review_ids: set[str] = set()
    confirmed_names: set[str] = set()
    decision_counts = {decision: 0 for decision in workflow.allowed_decisions}
    forbidden_names = set(workflow.forbidden_confirmed_names) | set(
        _string_list(expected.get("forbidden_names"))
    )

    def add_blocking(error_type: str, record: DecisionRecord | None = None, **extra: Any) -> None:
        blocking_errors.append(_issue(error_type, record, **extra))

    def add_warning(warning_type: str, record: DecisionRecord | None = None, **extra: Any) -> None:
        warnings.append(_issue(warning_type, record, **extra))

    for record in decision_records:
        data = record.data
        if "__invalid_json__" in data:
            add_blocking("invalid_json", record, detail=data["__invalid_json__"])
            continue
        if "__non_object_line__" in data:
            add_blocking(
                "invalid_jsonl_object",
                record,
                value=data["__non_object_line__"],
            )
            continue

        review_id = _clean_string(data.get("review_id"))
        if review_id is None:
            add_blocking("missing_review_id", record)
            continue

        if review_id in seen_records:
            add_blocking(
                "duplicate_review_id",
                record,
                review_id=review_id,
                first_path=seen_records[review_id].path,
                first_line=seen_records[review_id].line,
            )
        else:
            seen_records[review_id] = record
        seen_review_ids.add(review_id)

        review_entry = review_by_id.get(review_id)
        if review_entry is None:
            add_blocking("extra_review_id", record, review_id=review_id)

        decision = _clean_string(data.get("decision"))
        if decision not in workflow.allowed_decisions:
            add_blocking(
                "invalid_decision",
                record,
                review_id=review_id,
                decision=decision,
                allowed_decisions=list(workflow.allowed_decisions),
            )
            continue

        decision_counts[decision] = decision_counts.get(decision, 0) + 1
        if decision != "confirmed":
            continue

        name = _clean_string(data.get("name"))
        if name is None:
            add_blocking("missing_confirmed_name", record, review_id=review_id)
        else:
            confirmed_names.add(name)
            if name in forbidden_names:
                add_blocking(
                    "forbidden_confirmed_name",
                    record,
                    review_id=review_id,
                    name=name,
                )

        if (
            workflow.require_confirmed_source_spans
            and review_entry is not None
            and not _has_review_source_spans(review_entry)
        ):
            add_blocking("missing_confirmed_source_spans", record, review_id=review_id)

        fields = data.get("fields")
        if fields is None:
            fields = {}
            data["fields"] = fields
        if not isinstance(fields, dict):
            add_blocking("invalid_fields", record, review_id=review_id)
            continue

        for field_name in required_fields:
            if _field_missing(fields, field_name):
                if workflow.required_field_policy == "block":
                    add_blocking(
                        "missing_required_field",
                        record,
                        review_id=review_id,
                        field=field_name,
                    )
                else:
                    if workflow.required_field_policy == "fill_unknown":
                        fields[field_name] = "unknown"
                    add_warning(
                        "missing_required_field",
                        record,
                        review_id=review_id,
                        field=field_name,
                        policy=workflow.required_field_policy,
                    )

    if workflow.require_all_review_ids:
        for review_id in sorted(set(review_by_id) - seen_review_ids):
            add_blocking("missing_review_id", review_id=review_id)

    expected_present = set(_string_list(expected.get("expected_present")))
    for name in sorted(expected_present - confirmed_names):
        if workflow.expected_present_blocking:
            add_blocking("expected_present_missing", name=name)
        else:
            add_warning("expected_present_missing", name=name)

    for error_type in sorted(_types(blocking_errors + warnings)):
        repair_hints.append(
            {
                "type": error_type,
                "hint": _repair_hint(error_type),
            }
        )

    counts = {
        "review_entries": len(review_entries),
        "decision_records": len(decision_records),
        "review_ids_seen": len(seen_review_ids),
        "blocking_errors": len(blocking_errors),
        "warnings": len(warnings),
        **decision_counts,
    }
    return {
        "passed": not blocking_errors,
        "counts": counts,
        "blocking_errors": blocking_errors,
        "warnings": warnings,
        "repair_hints": repair_hints,
    }


def _review_entries_by_id(
    review_entries: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    for entry in review_entries:
        review_id = _clean_string(entry.get("review_id"))
        if review_id is not None:
            by_id[review_id] = entry
    return by_id


def _required_fields(
    curation: Mapping[str, Any],
    review_entries: Sequence[Mapping[str, Any]],
) -> list[str]:
    fields_config = curation.get("fields")
    if isinstance(fields_config, Mapping):
        configured = _string_list(fields_config.get("required"))
        if configured:
            return configured

    fallback: list[str] = []
    seen: set[str] = set()
    for entry in review_entries:
        fields = entry.get("fields")
        if not isinstance(fields, Mapping):
            continue
        for key in fields:
            name = str(key)
            if name not in seen:
                fallback.append(name)
                seen.add(name)
    return fallback


def _has_review_source_spans(review_entry: Mapping[str, Any]) -> bool:
    source_spans = review_entry.get("source_spans")
    return (
        isinstance(source_spans, list)
        and bool(source_spans)
        and all(isinstance(item, dict) for item in source_spans)
    )


def _field_missing(fields: Mapping[str, Any], field_name: str) -> bool:
    if field_name not in fields:
        return True
    value = fields[field_name]
    return value is None or (isinstance(value, str) and not value.strip())


def _issue(
    issue_type: str,
    record: DecisionRecord | None = None,
    **extra: Any,
) -> dict[str, Any]:
    issue = {"type": issue_type, **extra}
    if record is not None:
        issue["path"] = record.path
        issue["line"] = record.line
        if record.shard is not None:
            issue["shard"] = record.shard
        review_id = _clean_string(record.data.get("review_id"))
        if review_id is not None and "review_id" not in issue:
            issue["review_id"] = review_id
    return issue


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [text for item in value if (text := _clean_string(item)) is not None]
    text = _clean_string(value)
    return [] if text is None else [text]


def _types(items: Sequence[Mapping[str, Any]]) -> set[str]:
    return {str(item.get("type")) for item in items}


def _repair_hint(issue_type: str) -> str:
    hints = {
        "invalid_json": "Fix malformed JSONL decision lines.",
        "invalid_jsonl_object": "Use one JSON object per decision line.",
        "invalid_decision": "Choose one of the configured allowed decision values.",
        "missing_review_id": "Add decisions for required review_id values or disable complete coverage.",
        "duplicate_review_id": "Keep exactly one decision per review_id.",
        "extra_review_id": "Remove decisions that do not exist in the review pack.",
        "missing_confirmed_name": "Confirmed decisions must include a non-empty name.",
        "missing_confirmed_source_spans": "Confirmed items must trace back to review pack source_spans.",
        "invalid_fields": "Decision fields must be an object when present.",
        "missing_required_field": "Fill every required curation field before merge.",
        "forbidden_confirmed_name": "Remove or reject forbidden expected names.",
        "expected_present_missing": "Review expected names that were not confirmed.",
    }
    return hints.get(issue_type, "Review the decision validation issue.")
