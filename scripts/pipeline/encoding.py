from pathlib import Path
from typing import Sequence


def _require_candidates(candidates: Sequence[str] | None) -> list[str]:
    values = [value for value in candidates or [] if value]
    if not values:
        raise ValueError("encoding.fallbacks must contain at least one encoding")
    return values


def detect_text_encoding(path: Path, candidates: Sequence[str]) -> dict:
    tried: list[str] = []
    data = path.read_bytes()
    for encoding in _require_candidates(candidates):
        tried.append(encoding)
        try:
            text = data.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            continue
        confidence = "high" if "\ufffd" not in text else "medium"
        return {"encoding": encoding, "confidence": confidence, "tried": tried}
    raise UnicodeDecodeError("unknown", data, 0, 1, f"unable to decode with {tried}")


def read_text_with_encoding(
    path: Path,
    encoding: str | None = None,
    candidates: Sequence[str] | None = None,
) -> tuple[str, dict]:
    detected = (
        {"encoding": encoding, "confidence": "forced", "tried": [encoding]}
        if encoding
        else detect_text_encoding(path, _require_candidates(candidates))
    )
    text = path.read_bytes().decode(detected["encoding"], errors="strict")
    meta = {
        "encoding": detected["encoding"],
        "confidence": detected["confidence"],
        "line_count": len(text.splitlines()),
        "char_count": len(text),
        "replacement_count": text.count("\ufffd"),
    }
    return text, meta
