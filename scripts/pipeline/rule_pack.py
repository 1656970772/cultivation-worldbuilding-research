from pathlib import Path

from .config_loader import load_yaml


def _configured_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _dedupe(values: list) -> list:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _apply_list_extensions(strategy: dict) -> dict:
    merged = dict(strategy)
    for key, value in list(strategy.items()):
        if not key.startswith("additional_"):
            continue
        target_key = key.removeprefix("additional_")
        merged[target_key] = _dedupe(
            _configured_list(merged.get(target_key)) + _configured_list(value)
        )
        merged.pop(key, None)
    return merged


def load_rule_pack(mode_rule_path: Path, rule_pack_path: Path) -> dict:
    mode = load_yaml(mode_rule_path)
    pack = load_yaml(rule_pack_path)
    strategy = _deep_merge(
        mode.get("candidate_strategy", {}),
        pack.get("candidate_strategy", {}),
    )
    strategy = _apply_list_extensions(strategy)
    status = mode.get("status", {})
    merged = dict(pack)
    merged["candidate_strategy"] = strategy
    merged["default_candidate_status"] = status.get(
        "default_candidate_status",
        "needs-review",
    )
    required = [
        "include_suffixes",
        "context_triggers",
        "noise_exact",
        "noise_patterns",
        "field_schema",
        "strong_suffixes",
        "weak_suffixes",
    ]
    missing = [key for key in required if key not in merged]
    if missing:
        raise ValueError(f"rule pack missing keys: {missing}")
    return merged
