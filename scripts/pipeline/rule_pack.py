from pathlib import Path

from .config_loader import load_yaml

def load_rule_pack(mode_rule_path: Path, rule_pack_path: Path) -> dict:
    mode = load_yaml(mode_rule_path)
    pack = load_yaml(rule_pack_path)
    strategy = mode.get("candidate_strategy", {})
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
    ]
    missing = [key for key in required if key not in merged]
    if missing:
        raise ValueError(f"rule pack missing keys: {missing}")
    return merged
