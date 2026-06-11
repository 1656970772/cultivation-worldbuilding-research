from pathlib import Path

from scripts.pipeline.config_loader import load_yaml
from scripts.pipeline.encoding import read_text_with_encoding
from scripts.pipeline.segmenter import segment_text


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"E:\AI_Projects\修仙游戏调研\小说原文\凡人修仙传.txt")


def test_segments_fanren_with_spans():
    config = load_yaml(ROOT / "assets" / "default-config.yaml")
    text, _ = read_text_with_encoding(SOURCE, candidates=config["encoding"]["fallbacks"])
    segments = segment_text(
        text,
        [r"^第[一二三四五六七八九十百千万零〇两0-9]+章"],
        6000,
        300,
    )
    assert len(segments) > 1000
    assert segments[0]["segment_id"] == "seg-000001"
    assert segments[0]["start_line"] >= 1
    assert segments[0]["end_char"] > segments[0]["start_char"]
