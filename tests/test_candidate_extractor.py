from pathlib import Path

from scripts.pipeline.config_loader import load_yaml
from scripts.pipeline.rule_pack import load_rule_pack
from scripts.pipeline.candidate_extractor import extract_candidates_from_text


ROOT = Path(__file__).resolve().parents[1]


def _medicine_rules():
    return load_rule_pack(
        ROOT / "assets" / "mode-rules" / "entity.yaml",
        ROOT / "assets" / "rule-packs" / "entity-medicine.yaml",
    )


def test_extracts_medicine_names_and_rejects_noise():
    rules = _medicine_rules()
    text = "韩立服下黄龙丹和金髓丸，又听闻回阳水可以延寿。他检查丹田，脸上露出笑意。"

    names = {item["name"] for item in extract_candidates_from_text(text, rules)}

    assert {"黄龙丹", "金髓丸", "回阳水"} <= names
    assert "丹田" not in names
    assert "脸上露" not in names
    assert "服下黄龙丹" not in names
    assert "黄龙丹和金髓丸" not in names
    assert "检查丹" not in names


def test_candidates_include_segment_local_and_global_offsets():
    rules = _medicine_rules()
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


def test_medicine_name_strategy_lives_in_rule_pack_not_generic_entity_mode():
    mode = load_yaml(ROOT / "assets" / "mode-rules" / "entity.yaml")
    pack = load_yaml(ROOT / "assets" / "rule-packs" / "entity-medicine.yaml")
    rules = _medicine_rules()

    assert "name_patterns" not in mode["candidate_strategy"]
    assert "name_patterns" in pack["candidate_strategy"]
    assert rules["candidate_strategy"]["name_patterns"] == pack["candidate_strategy"]["name_patterns"]


def test_trims_configured_left_prefixes_from_medicine_names():
    rules = _medicine_rules()
    text = "韩立曾服用过黄龙丹。"

    candidates = extract_candidates_from_text(text, rules)
    names = {item["name"] for item in candidates}
    item = next(candidate for candidate in candidates if candidate["name"] == "黄龙丹")

    assert "黄龙丹" in names
    assert "过黄龙丹" not in names
    assert item["start"] == text.index("黄龙丹")
    assert item["end"] == item["start"] + len("黄龙丹")


def test_rejects_generic_medicine_phrase_noise_while_extracting_named_pill():
    rules = _medicine_rules()
    text = "这个药丸不是抽髓丸。"

    names = {item["name"] for item in extract_candidates_from_text(text, rules)}

    assert "抽髓丸" in names
    assert "这个药" not in names
    assert "这个药丸" not in names
    assert "个药丸不是抽髓丸" not in names


def test_rejects_expression_and_generic_weak_suffix_noise():
    rules = _medicine_rules()
    text = "韩立服下黄龙丹后，脸上流露出笑意，不禁露出异色。几种不同的药可以配制丹方。"

    names = {item["name"] for item in extract_candidates_from_text(text, rules)}

    assert "黄龙丹" in names
    assert "流露" not in names
    assert "不禁露" not in names
    assert "几种不同的药" not in names


def test_right_boundary_noise_filters_do_not_drop_strong_suffix_names():
    rules = _medicine_rules()
    text = "黄龙丹出现在丹方中。"

    names = {item["name"] for item in extract_candidates_from_text(text, rules)}

    assert "黄龙丹" in names


def test_rejects_generic_medicine_terms_and_overlapping_suffixes():
    rules = _medicine_rules()
    text = "这些丹药的丹方复杂，的丹也不应抽出。"

    names = {item["name"] for item in extract_candidates_from_text(text, rules)}

    assert "丹" not in names
    assert "丹药" not in names
    assert "这些丹" not in names
    assert "这些丹药" not in names
    assert "这些丹药的丹" not in names
    assert "的丹" not in names


def test_smoke_probe_rejects_obvious_real_text_noise_examples():
    rules = _medicine_rules()
    text = (
        "这些丹药各有来历，韩立曾服用过黄龙丹，又收起金髓丸。"
        "他脸上流露出笑意，不禁露出沉吟之色，心如秋水。"
        "架上有几种不同的药，旁人说这个药丸不是抽髓丸。"
    )

    names = {item["name"] for item in extract_candidates_from_text(text, rules)}

    assert {"黄龙丹", "金髓丸", "抽髓丸"} <= names
    assert not {
        "这些丹",
        "这些丹药",
        "流露",
        "不禁露",
        "心如秋水",
        "几种不同的药",
        "这个药",
        "这个药丸",
        "个药丸不是抽髓丸",
    } & names
