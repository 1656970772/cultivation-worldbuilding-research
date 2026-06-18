from __future__ import annotations

from typing import Any, Mapping


def merge_extractions(
    records: list[Mapping[str, Any]],
    identity_field: str = "",
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        attributes = record.get("attributes", {})
        fields = dict(attributes) if isinstance(attributes, dict) else {}
        name = str(fields.get(identity_field) or record.get("extraction_text") or "").strip()
        if not name:
            continue
        item = merged.setdefault(name, {"name": name, "fields": {}, "source_spans": []})
        for key, value in fields.items():
            _merge_field(item["fields"], str(key), _field_value(value))
        interval = record.get("char_interval", {})
        if isinstance(interval, dict):
            start = interval.get("start_pos")
            end = interval.get("end_pos")
            if start is not None and end is not None:
                item["source_spans"].append(
                    {
                        "start_char": start,
                        "end_char": end,
                        "summary": str(record.get("extraction_text") or name),
                    }
                )
    return list(merged.values())


def _merge_field(fields: dict[str, str], key: str, value: str) -> None:
    if not value:
        return
    current = fields.get(key)
    if current in (None, ""):
        fields[key] = value
    elif value not in [part.strip() for part in current.split("；")]:
        fields[key] = f"{current}；{value}"


def _field_value(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, dict):
        return "；".join(
            f"{key}:{val}" for key, val in value.items() if str(val).strip()
        )
    return str(value)
