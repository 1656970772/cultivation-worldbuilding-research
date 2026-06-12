from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.pipeline.review_pack import normalize_candidate_name


ALLOWED_DECISIONS = {"confirmed", "rejected", "needs-review"}
DEFAULT_UNKNOWN_TEXT = "原文未说明"


def _configured_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value) else []


def _field_config(curation: dict) -> dict[str, Any]:
    fields = curation.get("fields", {})
    return fields if isinstance(fields, dict) else {}


def _required_fields(curation: dict) -> list[str]:
    return _configured_list(_field_config(curation).get("required"))


def _unknown_text(curation: dict) -> str:
    value = _field_config(curation).get("unknown_text", DEFAULT_UNKNOWN_TEXT)
    text = str(value).strip() if value is not None else ""
    return text or DEFAULT_UNKNOWN_TEXT


def _report_config(curation: dict, report_config: dict | None) -> dict[str, Any]:
    config = dict(report_config or {})
    required = _required_fields(curation)
    if "required_columns" not in config and required:
        config["required_columns"] = required
    if "unknown_text" not in config:
        config["unknown_text"] = _unknown_text(curation)
    return config


def _blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _summary(decision: dict, name: str) -> dict[str, Any]:
    item = {
        "review_id": str(decision.get("review_id", "")),
        "name": name,
    }
    if "notes" in decision:
        item["notes"] = str(decision.get("notes", ""))
    return item


def _blocking_error(error_type: str, message: str, decision: dict | None = None) -> dict[str, Any]:
    error = {"type": error_type, "message": message}
    if isinstance(decision, dict):
        if "review_id" in decision:
            error["review_id"] = str(decision.get("review_id", ""))
        if "name" in decision:
            error["name"] = str(decision.get("name", ""))
    return error


def _new_report() -> dict[str, Any]:
    return {
        "counts": {
            "confirmed": 0,
            "rejected": 0,
            "needs_review": 0,
            "blocking_errors": 0,
        },
        "confirmed": [],
        "rejected": [],
        "needs_review": [],
        "blocking_errors": [],
    }


def _add_blocking_error(report: dict[str, Any], error: dict[str, Any]) -> None:
    report["blocking_errors"].append(error)
    report["counts"]["blocking_errors"] = len(report["blocking_errors"])


def _decision_name(decision: dict, entry: dict | None) -> str:
    decision_name = normalize_candidate_name(str(decision.get("name", "")))
    if decision_name:
        return decision_name
    if entry is None:
        return ""
    return normalize_candidate_name(str(entry.get("name", "")))


def _aliases(decision: dict, entry: dict | None, name: str) -> list[str]:
    values: list[str] = []
    if entry is not None:
        values.extend(_configured_list(entry.get("aliases")))
    values.extend(_configured_list(decision.get("aliases")))
    return sorted(
        {
            normalize_candidate_name(alias)
            for alias in values
            if normalize_candidate_name(alias)
            and normalize_candidate_name(alias) != name
        }
    )


def _normalized_field_value(field_name: str, value: Any, item_name: str, unknown_text: str) -> str:
    if _blank(value):
        return item_name if field_name.endswith("名称") else unknown_text
    return str(value)


def _decision_fields(
    decision: dict,
    item_name: str,
    required_fields: list[str],
    unknown_text: str,
) -> dict[str, str]:
    raw_fields = decision.get("fields", {})
    if not isinstance(raw_fields, dict):
        raw_fields = {}

    fields: dict[str, str] = {}
    for key, value in raw_fields.items():
        field_name = str(key)
        fields[field_name] = _normalized_field_value(
            field_name,
            value,
            item_name,
            unknown_text,
        )

    for field_name in required_fields:
        if field_name not in fields or _blank(fields[field_name]):
            fields[field_name] = _normalized_field_value(
                field_name,
                None,
                item_name,
                unknown_text,
            )
    return fields


def _merge_fields(
    target: dict[str, str],
    incoming: dict[str, str],
    unknown_text: str,
) -> None:
    for key, value in incoming.items():
        if key not in target or _blank(target[key]):
            target[key] = value
            continue
        if target[key] == unknown_text and not _blank(value) and value != unknown_text:
            target[key] = value


def _append_unique_dicts(target: list[dict], incoming: list[dict]) -> None:
    for item in incoming:
        if item not in target:
            target.append(item)


def _finalize_report(report: dict[str, Any]) -> None:
    report["counts"]["confirmed"] = len(report["confirmed"])
    report["counts"]["rejected"] = len(report["rejected"])
    report["counts"]["needs_review"] = len(report["needs_review"])
    report["counts"]["blocking_errors"] = len(report["blocking_errors"])


def merge_reviewed_entries(
    review_entries: list[dict],
    decisions: list[dict],
    curation: dict,
    report_config: dict,
) -> tuple[dict, dict]:
    required_fields = _required_fields(curation)
    unknown_text = _unknown_text(curation)
    entry_by_id = {
        str(entry.get("review_id", "")): entry
        for entry in review_entries
        if isinstance(entry, dict) and str(entry.get("review_id", ""))
    }
    report = _new_report()
    confirmed_by_name: dict[str, dict[str, Any]] = {}

    for decision in decisions:
        if not isinstance(decision, dict):
            _add_blocking_error(
                report,
                _blocking_error("invalid_decision", "decision must be an object"),
            )
            continue

        decision_value = str(decision.get("decision", "")).strip()
        if decision_value not in ALLOWED_DECISIONS:
            _add_blocking_error(
                report,
                _blocking_error(
                    "invalid_decision",
                    f"decision must be one of {sorted(ALLOWED_DECISIONS)}",
                    decision,
                ),
            )
            continue

        review_id = str(decision.get("review_id", ""))
        entry = entry_by_id.get(review_id)
        name = _decision_name(decision, entry)
        summary = _summary(decision, name)

        if decision_value == "rejected":
            report["rejected"].append(summary)
            continue
        if decision_value == "needs-review":
            report["needs_review"].append(summary)
            continue

        if entry is None:
            _add_blocking_error(
                report,
                _blocking_error(
                    "missing_review_entry",
                    f"confirmed decision has no matching review entry: {review_id}",
                    decision,
                ),
            )
            continue

        source_spans = entry.get("source_spans")
        if not isinstance(source_spans, list) or not source_spans:
            _add_blocking_error(
                report,
                _blocking_error(
                    "missing_source_spans",
                    f"confirmed item missing source_spans: {name}",
                    decision,
                ),
            )
            continue

        report["confirmed"].append(summary)
        fields = _decision_fields(decision, name, required_fields, unknown_text)
        if name not in confirmed_by_name:
            confirmed_by_name[name] = {
                "status": "confirmed",
                "name": name,
                "aliases": _aliases(decision, entry, name),
                "fields": fields,
                "source_spans": list(source_spans),
            }
            continue

        item = confirmed_by_name[name]
        item["aliases"] = sorted(
            set(item["aliases"]).union(_aliases(decision, entry, name))
        )
        _merge_fields(item["fields"], fields, unknown_text)
        _append_unique_dicts(item["source_spans"], list(source_spans))

    _finalize_report(report)
    if report["blocking_errors"]:
        first = report["blocking_errors"][0]
        raise ValueError(str(first["message"]))

    confirmed = {
        "work_title": str(curation.get("work_title", "")),
        "report_config": _report_config(curation, report_config),
        "items": list(confirmed_by_name.values()),
    }
    return confirmed, report


def read_decisions_jsonl(path: Path) -> list[dict]:
    decisions: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(f"JSONL line must be a JSON object: {path}:{line_number}")
        decisions.append(item)
    return decisions


def write_confirmed_outputs(
    confirmed: dict,
    report: dict,
    confirmed_path: Path,
    report_path: Path,
) -> None:
    confirmed_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    confirmed_path.write_text(
        json.dumps(confirmed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
