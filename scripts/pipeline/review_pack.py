import json
import re
from pathlib import Path
from typing import Any

from scripts.pipeline.config_loader import load_yaml


_NAME_STRIP_CHARS = (
    " \t\r\n"
    "\"'`"
    "“”‘’"
    "《》〈〉"
    "（）()"
    "【】[]"
    "{}"
    "，。；;：:、,.!?！？"
)


def load_curation_pack(path: Path) -> dict:
    return load_yaml(path)


def normalize_candidate_name(name: str) -> str:
    value = str(name or "").strip(_NAME_STRIP_CHARS)
    return re.sub(r"\s+", "", value)


def _configured_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value) else []


def _review_config(curation: dict) -> dict:
    review = curation.get("review", {})
    return review if isinstance(review, dict) else {}


def _field_config(curation: dict) -> dict:
    fields = curation.get("fields", {})
    return fields if isinstance(fields, dict) else {}


def _review_prefix(curation: dict) -> str:
    pack = str(curation.get("curation_pack", "review")).strip()
    if pack.startswith("entity-"):
        pack = pack.removeprefix("entity-")
    value = re.sub(r"[^A-Za-z0-9_-]+", "-", pack).strip("-_")
    return value or "review"


def _rejected_names(curation: dict) -> set[str]:
    review = _review_config(curation)
    names = set(_configured_list(review.get("reject_exact")))
    names.update(_configured_list(review.get("noise_exact")))
    names.update(_configured_list(curation.get("noise_exact")))
    return {normalize_candidate_name(name) for name in names}


def _is_rejected_name(name: str, curation: dict) -> bool:
    if name in _rejected_names(curation):
        return True
    return any(
        re.fullmatch(pattern, name)
        for pattern in _configured_list(_review_config(curation).get("reject_name_patterns"))
    )


def _status_suggestion(name: str, curation: dict) -> str:
    if _is_rejected_name(name, curation):
        return "rejected"
    return "needs-review"


def _empty_fields(name: str, curation: dict) -> dict[str, str]:
    fields = _field_config(curation)
    required = _configured_list(fields.get("required"))
    unknown = str(fields.get("unknown_text", ""))
    values = {field: unknown for field in required}
    for field in required:
        if field.endswith("名称"):
            values[field] = name
            break
    return values


def _candidate_name(candidate: dict) -> str:
    return normalize_candidate_name(str(candidate.get("name", "")))


def _evidence_name(item: dict) -> str:
    return normalize_candidate_name(str(item.get("name", "")))


def _source_span(evidence: dict) -> dict:
    span = evidence.get("source_span")
    if isinstance(span, dict):
        start_char = span.get("start_char")
        end_char = span.get("end_char")
    else:
        start_char = evidence.get("start_char")
        end_char = evidence.get("end_char")
    source = {
        "segment_id": str(evidence.get("segment_id", "")),
        "start_char": int(start_char) if start_char is not None else None,
        "end_char": int(end_char) if end_char is not None else None,
    }
    for key in ("title", "line", "summary", "local_span"):
        if key in evidence:
            source[key] = evidence[key]
    return source


def _span_sort_key(span: dict) -> tuple[str, int, int]:
    start = span.get("start_char")
    end = span.get("end_char")
    return (
        str(span.get("segment_id", "")),
        int(start) if start is not None else -1,
        int(end) if end is not None else -1,
    )


def _source_spans_for_name(
    name: str,
    evidence_by_name: dict[str, list[dict]],
) -> list[dict]:
    spans = [_source_span(item) for item in evidence_by_name.get(name, [])]
    spans.sort(key=_span_sort_key)
    return spans


def build_review_entries(
    candidates: list[dict],
    evidence: list[dict],
    curation: dict,
) -> list[dict]:
    grouped_candidates: dict[str, list[dict]] = {}
    for candidate in candidates:
        name = _candidate_name(candidate)
        if not name:
            continue
        grouped_candidates.setdefault(name, []).append(candidate)

    evidence_by_name: dict[str, list[dict]] = {}
    for item in evidence:
        name = _evidence_name(item)
        if not name:
            continue
        evidence_by_name.setdefault(name, []).append(item)

    review = _review_config(curation)
    max_evidence = int(review.get("max_evidence_per_entry", 0) or 0)
    prefix = _review_prefix(curation)
    entries: list[dict] = []
    for index, name in enumerate(sorted(grouped_candidates), start=1):
        candidate_group = grouped_candidates[name]
        source_spans = _source_spans_for_name(name, evidence_by_name)
        segments = sorted(
            {
                str(span["segment_id"])
                for span in source_spans
                if str(span.get("segment_id", ""))
            }
        )
        aliases = sorted(
            {
                normalize_candidate_name(str(candidate.get("name", "")))
                for candidate in candidate_group
                if normalize_candidate_name(str(candidate.get("name", ""))) != name
            }
        )
        entries.append(
            {
                "review_id": f"{prefix}-{index:06d}",
                "name": name,
                "aliases": aliases,
                "status_suggestion": _status_suggestion(name, curation),
                "evidence_count": len(evidence_by_name.get(name, [])),
                "candidate_count": len(candidate_group),
                "segments": segments,
                "source_spans": source_spans,
                "evidence_display_limit": max_evidence,
                "omitted_evidence_count": max(0, len(source_spans) - max_evidence)
                if max_evidence > 0
                else 0,
                "fields": _empty_fields(name, curation),
            }
        )
    return entries


def write_review_pack(
    entries: list[dict],
    jsonl_path: Path,
    markdown_path: Path,
) -> None:
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    lines = ["# Review Pack", ""]
    for entry in entries:
        lines.extend(
            [
                f"## {entry['review_id']} {entry['name']}",
                "",
                f"- status_suggestion: {entry['status_suggestion']}",
                f"- evidence_count: {entry['evidence_count']}",
                f"- candidate_count: {entry['candidate_count']}",
            ]
        )
        if entry.get("aliases"):
            lines.append(f"- aliases: {', '.join(entry['aliases'])}")
        fields = entry.get("fields", {})
        if isinstance(fields, dict) and fields:
            lines.extend(["", "### Fields", ""])
            for field, value in fields.items():
                lines.append(f"- {field}: {value}")
        lines.extend(["", "### Evidence", ""])
        source_spans = list(entry.get("source_spans", []))
        display_limit = int(entry.get("evidence_display_limit", 0) or 0)
        displayed_spans = (
            source_spans[:display_limit]
            if display_limit > 0
            else source_spans
        )
        for span in displayed_spans:
            segment_id = span.get("segment_id", "")
            start_char = span.get("start_char")
            end_char = span.get("end_char")
            title = span.get("title", "")
            line = span.get("line", "")
            summary = span.get("summary", "")
            line_text = f"- {segment_id}:{start_char}-{end_char}"
            if title:
                line_text += f" title {title}"
            if line != "":
                line_text += f" line {line}"
            if summary:
                line_text += f" - {summary}"
            lines.append(line_text)
        omitted_count = max(0, len(source_spans) - len(displayed_spans))
        if omitted_count:
            lines.append(f"- omitted_evidence_count: {omitted_count}")
        lines.append("")
    markdown_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
