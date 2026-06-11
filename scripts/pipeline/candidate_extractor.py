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


def _trim_left_prefixes(start: int, end: int, text: str, strategy: dict) -> int:
    trim_tokens = sorted(
        _configured_list(strategy.get("left_trim_tokens")),
        key=len,
        reverse=True,
    )
    changed = True
    while changed and start < end:
        changed = False
        name = text[start:end]
        for token in trim_tokens:
            if token and name.startswith(token) and len(name) > len(token):
                start += len(token)
                changed = True
                break
    return start


def _has_forbidden_name_boundary(name: str, strategy: dict) -> bool:
    prefixes = _configured_list(strategy.get("forbidden_name_prefixes"))
    if any(name.startswith(prefix) for prefix in prefixes):
        return True
    substrings = _configured_list(strategy.get("forbidden_name_substrings"))
    return any(value in name for value in substrings)


def _has_invalid_right_boundary(text: str, end: int, strategy: dict) -> bool:
    return any(
        text.startswith(token, end)
        for token in _configured_list(strategy.get("right_invalid_tokens"))
    )


def _is_noise(name: str, local_phrase: str, context: str, rules: dict) -> bool:
    if name in set(rules.get("noise_exact", [])):
        return True
    patterns = _noise_patterns(rules)
    if any(pattern in name for pattern in patterns["candidate_name"]):
        return True
    if any(pattern in local_phrase for pattern in patterns["local_phrase"]):
        return True
    return any(pattern in context for pattern in patterns["strong_context"])


def _matches_name_pattern(name: str, strategy: dict, key: str = "name_patterns") -> bool:
    patterns = _configured_list(strategy.get(key))
    if not patterns:
        return True
    return any(re.fullmatch(pattern, name) for pattern in patterns)


def _suffix_groups(rules: dict) -> tuple[list[str], list[str]]:
    strong_suffixes = _configured_list(rules.get("strong_suffixes"))
    weak_suffixes = _configured_list(rules.get("weak_suffixes"))
    if strong_suffixes or weak_suffixes:
        return strong_suffixes, weak_suffixes
    return _configured_list(rules.get("include_suffixes")), []


def _weak_suffix_allowed(
    name: str,
    local_context: str,
    strategy: dict,
) -> bool:
    if not _matches_name_pattern(name, strategy, "weak_name_patterns"):
        return False
    allowed_patterns = _configured_list(strategy.get("weak_allowed_name_patterns"))
    if any(re.fullmatch(pattern, name) for pattern in allowed_patterns):
        return True
    triggers = _configured_list(strategy.get("weak_context_triggers"))
    return bool(triggers) and any(trigger in local_context for trigger in triggers)


def extract_candidates_from_text(
    text: str,
    rules: dict,
    segment_id: str | None = None,
    segment_start_char: int = 0,
) -> list[dict]:
    strong_suffixes, weak_suffixes = _suffix_groups(rules)
    suffix_strength = {suffix: "weak" for suffix in weak_suffixes}
    suffix_strength.update({suffix: "strong" for suffix in strong_suffixes})
    suffix_values = sorted(suffix_strength, key=len, reverse=True)
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
        suffix = suffix_match.group(0)
        suffix_end = suffix_match.end()
        if (
            suffix_strength[suffix] == "weak"
            and _has_invalid_right_boundary(text, suffix_end, strategy)
        ):
            continue
        start = _candidate_start(
            text,
            suffix_match.start(),
            max_chars,
            boundary_tokens,
        )
        start = _trim_left_prefixes(start, suffix_end, text, strategy)
        name = text[start:suffix_end]
        if len(name) < min_chars or len(name) > max_chars:
            continue
        if _has_forbidden_name_boundary(name, strategy):
            continue
        if not re.fullmatch(r"[\u4e00-\u9fff]+", name):
            continue
        if not _matches_name_pattern(name, strategy):
            continue
        context = _context(text, start, suffix_end, window)
        local_phrase = _local_phrase(text, start, suffix_end, local_window)
        if suffix_strength[suffix] == "weak":
            weak_window = int(strategy.get("weak_context_window_chars", local_window))
            weak_context = _context(text, start, suffix_end, weak_window)
            if not _weak_suffix_allowed(name, weak_context, strategy):
                continue
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
