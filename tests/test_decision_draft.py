import pytest

from scripts.pipeline.decision_draft import draft_decisions


def test_draft_scaffold_keeps_all_entries_needs_review(tmp_path):
    entries = [
        {
            "review_id": "r-001",
            "name": "甲",
            "status_suggestion": "rejected",
            "aliases": [],
            "fields": {"名称": "甲"},
        }
    ]
    drafts = draft_decisions(entries, mode="scaffold", allowed_auto_safe=False)
    assert drafts[0]["decision"] == "needs-review"


def test_draft_suggestions_respects_rejected_suggestion_only(tmp_path):
    entries = [
        {
            "review_id": "r-001",
            "name": "甲",
            "status_suggestion": "rejected",
            "aliases": [],
            "fields": {"名称": "甲"},
        },
        {
            "review_id": "r-002",
            "name": "乙",
            "status_suggestion": "needs-review",
            "aliases": [],
            "fields": {"名称": "乙"},
        },
    ]
    drafts = draft_decisions(entries, mode="suggestions", allowed_auto_safe=False)
    assert [d["decision"] for d in drafts] == ["rejected", "needs-review"]


def test_draft_auto_safe_requires_explicit_enable():
    with pytest.raises(ValueError, match="auto-safe"):
        draft_decisions([], mode="auto-safe", allowed_auto_safe=False)
