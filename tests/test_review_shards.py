import json

from scripts.pipeline.jsonl_io import jsonl_sha256, write_jsonl_objects
from scripts.pipeline.review_shards import split_review_pack


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_split_review_pack_writes_manifest_with_ids_and_checksum(tmp_path):
    review_pack = tmp_path / "review-pack.jsonl"
    entries = [
        {"review_id": "review-001", "name": "A"},
        {"review_id": "review-002", "name": "B"},
        {"review_id": "review-003", "name": "C"},
    ]
    write_jsonl_objects(review_pack, entries)

    parts_dir = tmp_path / "review-decisions.parts"
    manifest = split_review_pack(review_pack, parts_dir, entries_per_shard=2)

    manifest_path = parts_dir / "review-shard-manifest.json"
    assert manifest_path.exists()
    assert manifest == _read_json(manifest_path)
    assert manifest["schema_version"] == 1
    assert manifest["review_pack"] == str(review_pack)
    assert manifest["review_pack_sha256"] == jsonl_sha256(review_pack)
    assert manifest["entries_per_shard"] == 2
    assert manifest["total_entries"] == 3

    assert manifest["shards"] == [
        {
            "shard": "review-shard-000001",
            "input": "review-shard-000001.jsonl",
            "expected_output": "review-decisions.part-000001.jsonl",
            "count": 2,
            "first_review_id": "review-001",
            "last_review_id": "review-002",
            "review_ids": ["review-001", "review-002"],
            "input_sha256": jsonl_sha256(parts_dir / "review-shard-000001.jsonl"),
        },
        {
            "shard": "review-shard-000002",
            "input": "review-shard-000002.jsonl",
            "expected_output": "review-decisions.part-000002.jsonl",
            "count": 1,
            "first_review_id": "review-003",
            "last_review_id": "review-003",
            "review_ids": ["review-003"],
            "input_sha256": jsonl_sha256(parts_dir / "review-shard-000002.jsonl"),
        },
    ]

    first_shard_lines = (parts_dir / "review-shard-000001.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert [json.loads(line)["review_id"] for line in first_shard_lines] == [
        "review-001",
        "review-002",
    ]


def test_split_review_pack_is_deterministic_for_same_input(tmp_path):
    review_pack = tmp_path / "review-pack.jsonl"
    write_jsonl_objects(
        review_pack,
        [
            {"review_id": "review-001", "name": "A"},
            {"review_id": "review-002", "name": "B"},
            {"review_id": "review-003", "name": "C"},
        ],
    )

    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = split_review_pack(review_pack, first_dir, entries_per_shard=2)
    second = split_review_pack(review_pack, second_dir, entries_per_shard=2)

    assert first == second
    assert (first_dir / "review-shard-000001.jsonl").read_bytes() == (
        second_dir / "review-shard-000001.jsonl"
    ).read_bytes()
    assert (first_dir / "review-shard-000002.jsonl").read_bytes() == (
        second_dir / "review-shard-000002.jsonl"
    ).read_bytes()
