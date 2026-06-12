import pytest

from scripts.pipeline.jsonl_io import iter_jsonl_objects, jsonl_sha256, write_jsonl_objects


def test_iter_jsonl_objects_reports_line_number_for_invalid_json(tmp_path):
    path = tmp_path / "items.jsonl"
    path.write_text('{"a": 1}\n{bad json}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"items\.jsonl:2"):
        list(iter_jsonl_objects(path))


def test_iter_jsonl_objects_rejects_non_object_lines(tmp_path):
    path = tmp_path / "items.jsonl"
    path.write_text('["not-object"]\n', encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        list(iter_jsonl_objects(path))


def test_write_jsonl_objects_uses_lf_and_stable_key_order(tmp_path):
    path = tmp_path / "items.jsonl"
    write_jsonl_objects(path, [{"b": 2, "a": 1}])
    assert path.read_bytes() == b'{"a":1,"b":2}\n'


def test_jsonl_checksum_changes_when_content_changes(tmp_path):
    path = tmp_path / "items.jsonl"
    write_jsonl_objects(path, [{"review_id": "r-001"}])
    first = jsonl_sha256(path)
    write_jsonl_objects(path, [{"review_id": "r-002"}])
    assert jsonl_sha256(path) != first
