from typing import Any, Iterable, Mapping


def draft_decisions(
    review_entries: Iterable[Mapping[str, Any]],
    *,
    mode: str,
    allowed_auto_safe: bool = False,
) -> list[dict[str, Any]]:
    if mode not in {"scaffold", "suggestions", "auto-safe"}:
        raise ValueError("mode must be scaffold, suggestions, or auto-safe")
    if mode == "auto-safe" and not allowed_auto_safe:
        raise ValueError("auto-safe draft mode requires explicit allowed_auto_safe=true")

    drafts: list[dict[str, Any]] = []
    for entry in review_entries:
        review_id = str(entry.get("review_id") or "").strip()
        if not review_id:
            raise ValueError("review entry missing review_id")
        status_suggestion = str(entry.get("status_suggestion") or "").strip()
        if mode == "scaffold":
            decision = "needs-review"
        elif mode == "suggestions":
            decision = "rejected" if status_suggestion == "rejected" else "needs-review"
        else:
            decision = "needs-review"

        drafts.append(
            {
                "review_id": review_id,
                "decision": decision,
                "name": entry.get("name") or "",
                "aliases": list(entry.get("aliases") or []),
                "fields": dict(entry.get("fields") or {}),
                "source_spans": list(entry.get("source_spans") or []),
                "notes": "",
            }
        )
    return drafts
