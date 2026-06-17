from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "extracting-worldbuilding" / "SKILL.md"


def test_skill_documents_low_confidence_confirmation():
    text = SKILL.read_text(encoding="utf-8")

    assert "low confidence" in text
    assert "ask the user before running extraction" in text
    assert "questions" in text


def test_skill_documents_shard_contract():
    text = SKILL.read_text(encoding="utf-8")

    assert "review-pack.jsonl" in text
    assert "review-decisions.parts/part-{index}.jsonl" in text
    assert "review_id" in text
    assert "decision" in text


def test_skill_requires_generated_framework_files_downstream():
    text = SKILL.read_text(encoding="utf-8")

    assert "route.json" in text
    assert "rule-pack.yaml" in text
    assert "curation.yaml" in text
    assert "must be reused by extract-candidates, make-review-pack, finalize-reviewed, and render" in text
