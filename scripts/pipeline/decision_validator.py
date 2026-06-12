from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ReviewWorkflowConfig:
    entries_per_shard: int
    part_dir: str
    require_complete_parts: bool
    draft_mode: str
    allowed_decisions: Sequence[str]
    require_all_review_ids: bool
    expected_present_blocking: bool
    required_field_policy: str
    checksum_algorithm: str


def resolve_review_workflow(curation: Mapping[str, Any]) -> ReviewWorkflowConfig:
    workflow = curation.get("review_workflow") or {}
    validation = curation.get("decision_validation") or {}

    if not isinstance(workflow, Mapping):
        raise ValueError("review_workflow must be a mapping")
    if not isinstance(validation, Mapping):
        raise ValueError("decision_validation must be a mapping")

    entries_per_shard = int(workflow.get("entries_per_shard", 60))
    if entries_per_shard < 1:
        raise ValueError("review_workflow.entries_per_shard must be >= 1")

    part_dir = str(workflow.get("part_dir", "review-decisions.parts")).strip()
    if not part_dir:
        raise ValueError("review_workflow.part_dir must not be empty")

    require_complete_parts = bool(workflow.get("require_complete_parts", True))
    draft_mode = str(workflow.get("draft_mode", "scaffold")).strip()
    if draft_mode not in {"scaffold", "suggestions", "auto-safe"}:
        raise ValueError("review_workflow.draft_mode must be scaffold, suggestions, or auto-safe")

    allowed_raw = validation.get("allowed_decisions", ["confirmed", "rejected", "needs-review"])
    if not isinstance(allowed_raw, Sequence) or isinstance(allowed_raw, (str, bytes)):
        raise ValueError("decision_validation.allowed_decisions must be a list")
    allowed_decisions = tuple(str(item).strip() for item in allowed_raw if str(item).strip())
    if not allowed_decisions:
        raise ValueError("decision_validation.allowed_decisions must not be empty")

    required_field_policy = str(validation.get("required_field_policy", "fill_unknown")).strip()
    if required_field_policy not in {"fill_unknown", "warn", "block"}:
        raise ValueError("decision_validation.required_field_policy must be fill_unknown, warn, or block")

    checksum_algorithm = str(workflow.get("checksum_algorithm", "sha256")).strip().lower()
    if checksum_algorithm != "sha256":
        raise ValueError("review_workflow.checksum_algorithm currently supports sha256")

    return ReviewWorkflowConfig(
        entries_per_shard=entries_per_shard,
        part_dir=part_dir,
        require_complete_parts=require_complete_parts,
        draft_mode=draft_mode,
        allowed_decisions=allowed_decisions,
        require_all_review_ids=bool(validation.get("require_all_review_ids", True)),
        expected_present_blocking=bool(validation.get("expected_present_blocking", False)),
        required_field_policy=required_field_policy,
        checksum_algorithm=checksum_algorithm,
    )
