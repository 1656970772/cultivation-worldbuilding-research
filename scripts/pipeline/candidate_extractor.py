import re


def _configured_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _context(text: str, start: int, end: int, size: int) -> str:
    return text[max(0, start - size): min(len(text), end + size)]


def _local_phrase(text: str, start: int, end: int, size: int) -> str:
    return text[max(0, start - size): min(len(text), end + size)]


def _noise_patterns(rules: dict) -> dict[str, list[str]]:
    patterns = rules.get("noise_patterns", {})
    if isinstance(patterns, dict):
        return {
            "candidate_name": list(patterns.get("candidate_name", [])),
            "local_phrase": list(patterns.get("local_phrase", [])),
            "strong_context": list(patterns.get("strong_context", [])),
        }
    return {
        "candidate_name": list(patterns or []),
        "local_phrase": [],
        "strong_context": [],
    }


def _candidate_start(
    text: str,
    suffix_start: int,
    max_chars: int,
    boundary_tokens: list[str],
) -> int:
    earliest_start = max(0, suffix_start - max_chars + 1)
    start = earliest_start
    for token in boundary_tokens:
        index = text.rfind(token, earliest_start, suffix_start)
        if index >= 0:
            start = max(start, index + len(token))
    while start < suffix_start and not re.fullmatch(r"[\u4e00-\u9fff]", text[start]):
        start += 1
    return start


def _is_noise(name: str, local_phrase: str, context: str, rules: dict) -> bool:
    if name in set(rules.get("noise_exact", [])):
        return True
    patterns = _noise_patterns(rules)
    if any(pattern in name for pattern in patterns["candidate_name"]):
        return True
    if any(pattern in local_phrase for pattern in patterns["local_phrase"]):
        return True
    return any(pattern in context for pattern in patterns["strong_context"])


def _matches_name_pattern(name: str, strategy: dict) -> bool:
    patterns = _configured_list(strategy.get("name_patterns"))
    if not patterns:
        return True
    return any(re.fullmatch(pattern, name) for pattern in patterns)


def extract_candidates_from_text(
    text: str,
    rules: dict,
    segment_id: str | None = None,
    segment_start_char: int = 0,
) -> list[dict]:
    suffix_values = sorted(rules.get("include_suffixes", []), key=len, reverse=True)
    if not suffix_values:
        return []
    suffix_pattern = re.compile("|".join(re.escape(value) for value in suffix_values))
    strategy = rules.get("candidate_strategy", {})
    min_chars = int(strategy.get("min_name_chars", 2))
    max_chars = int(strategy.get("max_name_chars", 12))
    window = int(strategy.get("context_window_chars", 80))
    local_window = int(strategy.get("noise_local_window_chars", 4))
    boundary_tokens = _configured_list(strategy.get("left_boundary_tokens"))
    candidates: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for suffix_match in suffix_pattern.finditer(text):
        suffix_end = suffix_match.end()
        start = _candidate_start(
            text,
            suffix_match.start(),
            max_chars,
            boundary_tokens,
        )
        name = text[start:suffix_end]
        if len(name) < min_chars or len(name) > max_chars:
            continue
        if not re.fullmatch(r"[\u4e00-\u9fff]+", name):
            continue
        if not _matches_name_pattern(name, strategy):
            continue
        context = _context(text, start, suffix_end, window)
        local_phrase = _local_phrase(text, start, suffix_end, local_window)
        if _is_noise(name, local_phrase, context, rules):
            continue
        if not any(trigger in context for trigger in rules.get("context_triggers", [])):
            continue
        key = (name, start)
        if key in seen:
            continue
        seen.add(key)
        item = {
            "name": name,
            "subject_type": rules.get("subject_type", "实体"),
            "status": rules.get("default_candidate_status", "needs-review"),
            "matched_by": "boundary-pattern-context",
            "start": start,
            "end": suffix_end,
            "start_char": segment_start_char + start,
            "end_char": segment_start_char + suffix_end,
            "context": context.replace("\n", " "),
        }
        if segment_id is not None:
            item["segment_id"] = segment_id
        candidates.append(item)
    return candidates
