import pytest

from scripts.pipeline.decision_validator import resolve_review_workflow


def test_review_workflow_defaults_are_generic():
    config = resolve_review_workflow({})
    assert 40 <= config.entries_per_shard <= 80
    assert config.part_dir == "review-decisions.parts"
    assert config.allowed_decisions == ("confirmed", "rejected", "needs-review")
    assert config.require_all_review_ids is True
    assert config.expected_present_blocking is False


def test_review_workflow_rejects_non_positive_entries_per_shard():
    with pytest.raises(ValueError, match="review_workflow.entries_per_shard"):
        resolve_review_workflow({"review_workflow": {"entries_per_shard": 0}})
