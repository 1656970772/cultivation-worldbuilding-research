import json
from pathlib import Path
from typing import Any, Mapping

from scripts.pipeline.jsonl_io import (
    iter_jsonl_objects,
    jsonl_sha256,
    write_jsonl_objects,
)


def _shard_name(prefix: str, index: int) -> str:
    return f"{prefix}-{index:06d}"


def _part_name(prefix: str, index: int) -> str:
    return f"{prefix}-{index:06d}.jsonl"


def _write_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(manifest), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def split_review_pack(
    review_pack_path: str | Path,
    parts_dir: str | Path,
    *,
    entries_per_shard: int,
    manifest_path: str | Path | None = None,
    shard_prefix: str = "review-shard",
    expected_part_prefix: str = "review-decisions.part",
) -> dict[str, Any]:
    if entries_per_shard < 1:
        raise ValueError("entries_per_shard must be >= 1")

    review_pack = Path(review_pack_path)
    parts = Path(parts_dir)
    manifest_output = Path(manifest_path) if manifest_path is not None else (
        parts / "review-shard-manifest.json"
    )
    parts.mkdir(parents=True, exist_ok=True)

    shards: list[dict[str, Any]] = []
    current_entries: list[dict[str, Any]] = []
    current_review_ids: list[str] = []
    total_entries = 0

    def flush_shard() -> None:
        if not current_entries:
            return
        shard_index = len(shards) + 1
        shard = _shard_name(shard_prefix, shard_index)
        input_name = f"{shard}.jsonl"
        input_path = parts / input_name
        write_jsonl_objects(input_path, current_entries)
        shards.append(
            {
                "shard": shard,
                "input": input_name,
                "expected_output": _part_name(expected_part_prefix, shard_index),
                "count": len(current_entries),
                "first_review_id": current_review_ids[0],
                "last_review_id": current_review_ids[-1],
                "review_ids": list(current_review_ids),
                "input_sha256": jsonl_sha256(input_path),
            }
        )
        current_entries.clear()
        current_review_ids.clear()

    for line_number, entry in iter_jsonl_objects(review_pack):
        review_id = entry.get("review_id")
        if not review_id:
            raise ValueError(f"{review_pack}:{line_number} missing review_id")
        current_entries.append(entry)
        current_review_ids.append(str(review_id))
        total_entries += 1
        if len(current_entries) == entries_per_shard:
            flush_shard()

    flush_shard()

    manifest = {
        "schema_version": 1,
        "review_pack": str(review_pack),
        "review_pack_sha256": jsonl_sha256(review_pack),
        "entries_per_shard": entries_per_shard,
        "total_entries": total_entries,
        "shards": shards,
    }
    _write_manifest(manifest_output, manifest)
    return manifest
