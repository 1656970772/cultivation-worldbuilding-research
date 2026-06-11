from pathlib import Path

from scripts.pipeline.config_loader import load_yaml
from scripts.pipeline.encoding import detect_text_encoding, read_text_with_encoding


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"E:\AI_Projects\修仙游戏调研\小说原文\凡人修仙传.txt")


def _fallbacks() -> list[str]:
    config = load_yaml(ROOT / "assets" / "default-config.yaml")
    return config["encoding"]["fallbacks"]


def test_detects_fanren_legacy_encoding():
    result = detect_text_encoding(SOURCE, _fallbacks())
    assert result["encoding"].lower() in {"gb18030", "gbk", "gb2312"}


def test_reads_fanren_without_garbage():
    text, meta = read_text_with_encoding(SOURCE, candidates=_fallbacks())
    assert "凡人修仙传" in text[:1000] or "韩立" in text[:5000]
    assert text.count("\ufffd") == 0
    assert meta["line_count"] > 100000
