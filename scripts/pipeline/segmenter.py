import json
import re
from pathlib import Path


def _line_for_char(line_starts: list[int], char_index: int) -> int:
    line_number = 1
    for i, start in enumerate(line_starts, start=1):
        if start > char_index:
            break
        line_number = i
    return line_number


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for match in re.finditer(r"\n", text):
        starts.append(match.end())
    return starts


def segment_text(
    text: str,
    chapter_patterns: list[str],
    max_chars: int,
    overlap_chars: int,
) -> list[dict]:
    combined = re.compile("|".join(f"(?:{p})" for p in chapter_patterns), re.MULTILINE)
    matches = list(combined.finditer(text))
    boundaries = [(match.start(), match.group(0).strip()) for match in matches]
    if not boundaries or boundaries[0][0] != 0:
        boundaries.insert(0, (0, "前置内容"))

    line_starts = _line_starts(text)
    segments: list[dict] = []
    for index, (start, title) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(text)
        window_start = start
        while window_start < end:
            window_end = min(end, window_start + max_chars)
            segment_text_value = text[window_start:window_end]
            segments.append(
                {
                    "segment_id": f"seg-{len(segments) + 1:06d}",
                    "title": title,
                    "text": segment_text_value,
                    "start_line": _line_for_char(line_starts, window_start),
                    "end_line": _line_for_char(
                        line_starts,
                        max(window_end - 1, window_start),
                    ),
                    "start_char": window_start,
                    "end_char": window_end,
                }
            )
            if window_end >= end:
                break
            window_start = max(window_start + 1, window_end - overlap_chars)
    return segments


def write_jsonl(items: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
