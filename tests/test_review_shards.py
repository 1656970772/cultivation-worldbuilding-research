import json

from scripts.pipeline import review_shards
from scripts.pipeline.jsonl_io import jsonl_sha256, write_jsonl_objects
from scripts.pipeline.review_shards import split_review_pack


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_manifest(path, shards):
    manifest = {
        "schema_version": 1,
        "review_pack": str(path.parent / "review-pack.jsonl"),
        "review_pack_sha256": "unused",
        "entries_per_shard": 2,
        "total_entries": sum(len(shard["review_ids"]) for shard in shards),
        "shards": shards,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def _shard(name, expected_output, review_ids):
    return {
        "shard": name,
        "input": f"{name}.jsonl",
        "expected_output": expected_output,
        "count": len(review_ids),
        "first_review_id": review_ids[0],
        "last_review_id": review_ids[-1],
        "review_ids": review_ids,
        "input_sha256": "unused",
    }


def _write_part(path, rows):
    write_jsonl_objects(path, rows)


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


def test_collect_blocks_missing_part_and_reports_shard(tmp_path):
    parts_dir = tmp_path / "review-decisions.parts"
    manifest_path = parts_dir / "review-shard-manifest.json"
    _write_manifest(
        manifest_path,
        [
            _shard(
                "review-shard-000001",
                "review-decisions.part-000001.jsonl",
                ["review-001"],
            )
        ],
    )
    output_path = tmp_path / "review-decisions.jsonl"

    report = review_shards.collect_decision_parts(
        manifest_path,
        parts_dir,
        output_path,
    )

    assert report["passed"] is False
    assert not output_path.exists()
    assert report["blocking_errors"] == [
        {
            "type": "missing_part_file",
            "shard": "review-shard-000001",
            "path": str(parts_dir / "review-decisions.part-000001.jsonl"),
        }
    ]
    assert report["repair_hints"] == [
        {
            "shard": "review-shard-000001",
            "expected_output": "review-decisions.part-000001.jsonl",
            "blocking_error_types": ["missing_part_file"],
            "hint": "Rerun this decision shard and write the expected part file.",
        }
    ]


def test_collect_blocks_part_with_wrong_review_id_and_line(tmp_path):
    parts_dir = tmp_path / "review-decisions.parts"
    manifest_path = parts_dir / "review-shard-manifest.json"
    _write_manifest(
        manifest_path,
        [
            _shard(
                "review-shard-000001",
                "review-decisions.part-000001.jsonl",
                ["review-001"],
            )
        ],
    )
    part_path = parts_dir / "review-decisions.part-000001.jsonl"
    _write_part(part_path, [{"review_id": "review-999", "decision": "confirmed"}])

    report = review_shards.collect_decision_parts(
        manifest_path,
        parts_dir,
        tmp_path / "review-decisions.jsonl",
    )

    assert report["passed"] is False
    error = next(
        item
        for item in report["blocking_errors"]
        if item["type"] == "review_id_outside_shard"
    )
    assert error["shard"] == "review-shard-000001"
    assert error["path"] == str(part_path)
    assert error["line"] == 1
    assert error["review_id"] == "review-999"


def test_collect_missing_review_id_global_reports_expected_part_path(tmp_path):
    parts_dir = tmp_path / "review-decisions.parts"
    manifest_path = parts_dir / "review-shard-manifest.json"
    _write_manifest(
        manifest_path,
        [
            _shard(
                "review-shard-000001",
                "review-decisions.part-000001.jsonl",
                ["review-001"],
            )
        ],
    )
    part_path = parts_dir / "review-decisions.part-000001.jsonl"
    _write_part(part_path, [])

    report = review_shards.collect_decision_parts(
        manifest_path,
        parts_dir,
        tmp_path / "review-decisions.jsonl",
    )

    assert report["passed"] is False
    error = next(
        item
        for item in report["blocking_errors"]
        if item["type"] == "missing_review_id_global"
    )
    assert error["shard"] == "review-shard-000001"
    assert error["review_id"] == "review-001"
    assert error["path"] == str(part_path)


def test_collect_outputs_manifest_order_not_filesystem_order(tmp_path):
    parts_dir = tmp_path / "review-decisions.parts"
    manifest_path = parts_dir / "review-shard-manifest.json"
    _write_manifest(
        manifest_path,
        [
            _shard(
                "review-shard-000002",
                "z-review-decisions.part.jsonl",
                ["review-003", "review-004"],
            ),
            _shard(
                "review-shard-000001",
                "a-review-decisions.part.jsonl",
                ["review-001", "review-002"],
            ),
        ],
    )
    _write_part(
        parts_dir / "a-review-decisions.part.jsonl",
        [
            {"review_id": "review-002", "decision": "confirmed"},
            {"review_id": "review-001", "decision": "rejected"},
        ],
    )
    _write_part(
        parts_dir / "z-review-decisions.part.jsonl",
        [
            {"review_id": "review-004", "decision": "confirmed"},
            {"review_id": "review-003", "decision": "needs-review"},
        ],
    )
    output_path = tmp_path / "review-decisions.jsonl"

    report = review_shards.collect_decision_parts(
        manifest_path,
        parts_dir,
        output_path,
    )

    assert report["passed"] is True
    assert [row["review_id"] for row in _read_jsonl(output_path)] == [
        "review-003",
        "review-004",
        "review-001",
        "review-002",
    ]
