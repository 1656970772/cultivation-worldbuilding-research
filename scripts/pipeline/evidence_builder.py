from typing import Any


def _segments_by_id(segments: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(segment["segment_id"]): segment for segment in segments}


def _int_value(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    return int(value)


def _candidate_local_span(
    candidate: dict[str, Any],
    segment: dict[str, Any],
) -> tuple[int, int]:
    if "start" in candidate and "end" in candidate:
        return int(candidate["start"]), int(candidate["end"])
    if "start_char" in candidate and "end_char" in candidate:
        segment_start = _int_value(segment.get("start_char"))
        return (
            int(candidate["start_char"]) - segment_start,
            int(candidate["end_char"]) - segment_start,
        )
    raise ValueError(f"candidate missing local offsets: {candidate.get('name', '')}")


def _validate_global_offsets(
    candidate: dict[str, Any],
    expected_start: int,
    expected_end: int,
) -> None:
    if "start_char" in candidate and int(candidate["start_char"]) != expected_start:
        raise ValueError(
            f"candidate global offsets do not match local span: {candidate.get('name', '')}"
        )
    if "end_char" in candidate and int(candidate["end_char"]) != expected_end:
        raise ValueError(
            f"candidate global offsets do not match local span: {candidate.get('name', '')}"
        )


def _validate_span_text(candidate: dict[str, Any], text: str, start: int, end: int) -> None:
    name = str(candidate.get("name", ""))
    if name and text[start:end] != name:
        raise ValueError(
            f"candidate span text does not match name: {candidate.get('name', '')}"
        )


def _line_for_local_offset(segment: dict[str, Any], local_start: int) -> int:
    text = str(segment.get("text", ""))
    start_line = _int_value(segment.get("start_line"), 1)
    return start_line + text[:local_start].count("\n")


def _context_summary(text: str, start: int, end: int, context_chars: int) -> str:
    summary_start = max(0, start - context_chars)
    summary_end = min(len(text), end + context_chars)
    return text[summary_start:summary_end].replace("\n", " ").strip()


def build_evidence_pack(
    candidates: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    context_chars: int = 80,
) -> list[dict[str, Any]]:
    segment_lookup = _segments_by_id(segments)
    evidence: list[dict[str, Any]] = []
    for candidate in candidates:
        segment_id = str(candidate.get("segment_id", ""))
        if segment_id not in segment_lookup:
            raise KeyError(f"candidate segment not found: {segment_id}")
        segment = segment_lookup[segment_id]
        text = str(segment.get("text", ""))
        local_start, local_end = _candidate_local_span(candidate, segment)
        if local_start < 0 or local_end < local_start or local_end > len(text):
            raise ValueError(
                f"candidate offsets outside segment: {candidate.get('name', '')}"
            )
        segment_start = _int_value(segment.get("start_char"))
        source_start = segment_start + local_start
        source_end = segment_start + local_end
        _validate_global_offsets(candidate, source_start, source_end)
        _validate_span_text(candidate, text, local_start, local_end)
        evidence.append(
            {
                "name": candidate.get("name", ""),
                "status": candidate.get("status", ""),
                "segment_id": segment_id,
                "title": segment.get("title", ""),
                "line": _line_for_local_offset(segment, local_start),
                "summary": _context_summary(text, local_start, local_end, context_chars),
                "source_span": {
                    "start_char": source_start,
                    "end_char": source_end,
                },
                "local_span": {
                    "start": local_start,
                    "end": local_end,
                },
            }
        )
    return evidence
