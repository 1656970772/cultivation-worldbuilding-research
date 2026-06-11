from pathlib import Path

from scripts.pipeline.rule_pack import load_rule_pack
from scripts.pipeline.candidate_extractor import extract_candidates_from_text


ROOT = Path(__file__).resolve().parents[1]


def test_extracts_medicine_names_and_rejects_noise():
    rules = load_rule_pack(
        ROOT / "assets" / "mode-rules" / "entity.yaml",
        ROOT / "assets" / "rule-packs" / "entity-medicine.yaml",
    )
    text = "韩立服下黄龙丹和金髓丸，又听闻回阳水可以延寿。他检查丹田，脸上露出笑意。"

    names = {item["name"] for item in extract_candidates_from_text(text, rules)}

    assert {"黄龙丹", "金髓丸", "回阳水"} <= names
    assert "丹田" not in names
    assert "脸上露" not in names
    assert "服下黄龙丹" not in names
    assert "黄龙丹和金髓丸" not in names
    assert "检查丹" not in names


def test_candidates_include_segment_local_and_global_offsets():
    rules = load_rule_pack(
        ROOT / "assets" / "mode-rules" / "entity.yaml",
        ROOT / "assets" / "rule-packs" / "entity-medicine.yaml",
    )
    text = "韩立服下黄龙丹。"

    candidates = extract_candidates_from_text(
        text,
        rules,
        segment_id="seg-000002",
        segment_start_char=500,
    )
    item = next(candidate for candidate in candidates if candidate["name"] == "黄龙丹")

    assert item["segment_id"] == "seg-000002"
    assert item["start"] == text.index("黄龙丹")
    assert item["end"] == item["start"] + len("黄龙丹")
    assert item["start_char"] == 500 + item["start"]
    assert item["end_char"] == 500 + item["end"]
