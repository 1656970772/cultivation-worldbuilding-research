import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.pipeline.jsonl_io import (
    iter_jsonl_objects,
    jsonl_sha256,
    write_jsonl_objects,
)


DEFAULT_ALLOWED_DECISIONS = ("confirmed", "rejected", "needs-review")


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


def _read_json_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


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


def collect_decision_parts(
    manifest_path: str | Path,
    parts_dir: str | Path,
    output_path: str | Path,
    *,
    allowed_decisions: Sequence[str] = DEFAULT_ALLOWED_DECISIONS,
) -> dict[str, Any]:
    manifest_file = Path(manifest_path)
    parts = Path(parts_dir)
    output = Path(output_path)
    manifest = _read_json_object(manifest_file)
    shards = _manifest_shards(manifest)
    allowed = tuple(str(item).strip() for item in allowed_decisions if str(item).strip())
    allowed_set = set(allowed)

    blocking_errors: list[dict[str, Any]] = []
    expected_by_id: dict[str, str] = {}
    expected_order: list[tuple[str, str]] = []
    review_ids_by_shard: dict[str, list[str]] = {}
    shard_info_by_name: dict[str, dict[str, Any]] = {}

    for shard_info in shards:
        shard = str(shard_info["shard"])
        review_ids = _review_ids(shard_info)
        shard_info_by_name[shard] = dict(shard_info)
        review_ids_by_shard[shard] = review_ids
        for review_id in review_ids:
            expected_by_id.setdefault(review_id, shard)
            expected_order.append((shard, review_id))

    records_by_shard: dict[str, dict[str, dict[str, Any]]] = {
        shard: {} for shard in review_ids_by_shard
    }
    first_seen: dict[str, dict[str, Any]] = {}
    part_paths_by_shard: dict[str, str] = {}
    missing_part_shards: set[str] = set()
    decision_counts = {decision: 0 for decision in allowed}
    part_records = 0
    part_files_read = 0

    for shard_info in shards:
        shard = str(shard_info["shard"])
        expected_output = str(shard_info["expected_output"])
        part_path = parts / expected_output
        part_paths_by_shard[shard] = str(part_path)
        review_ids = review_ids_by_shard[shard]
        shard_review_ids = set(review_ids)

        if not part_path.exists():
            missing_part_shards.add(shard)
            _add_blocking(
                blocking_errors,
                "missing_part_file",
                shard=shard,
                path=str(part_path),
            )
            continue

        part_files_read += 1
        part_seen: dict[str, dict[str, Any]] = {}
        actual_count = 0
        with part_path.open("r", encoding="utf-8-sig") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                actual_count += 1
                part_records += 1
                context = {
                    "shard": shard,
                    "path": str(part_path),
                    "line": line_number,
                }
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError as exc:
                    _add_blocking(
                        blocking_errors,
                        "invalid_json",
                        **context,
                        detail=str(exc),
                    )
                    continue
                if not isinstance(parsed, dict):
                    _add_blocking(
                        blocking_errors,
                        "non_object_line",
                        **context,
                        value=parsed,
                    )
                    continue

                review_id = _clean_string(parsed.get("review_id"))
                if review_id is None:
                    _add_blocking(blocking_errors, "missing_review_id", **context)
                    continue
                context["review_id"] = review_id

                if review_id in part_seen:
                    first = part_seen[review_id]
                    _add_blocking(
                        blocking_errors,
                        "duplicate_review_id_in_part",
                        **context,
                        first_line=first["line"],
                    )
                else:
                    part_seen[review_id] = context

                if review_id in first_seen:
                    first = first_seen[review_id]
                    _add_blocking(
                        blocking_errors,
                        "duplicate_review_id_global",
                        **context,
                        first_shard=first["shard"],
                        first_path=first["path"],
                        first_line=first["line"],
                    )
                else:
                    first_seen[review_id] = context

                if review_id not in shard_review_ids:
                    _add_blocking(
                        blocking_errors,
                        "review_id_outside_shard",
                        **context,
                    )

                decision = _clean_string(parsed.get("decision"))
                if decision not in allowed_set:
                    _add_blocking(
                        blocking_errors,
                        "invalid_decision",
                        **context,
                        decision=decision,
                        allowed_decisions=list(allowed),
                    )
                else:
                    decision_counts[decision] = decision_counts.get(decision, 0) + 1

                if (
                    review_id in shard_review_ids
                    and review_id not in records_by_shard[shard]
                ):
                    records_by_shard[shard][review_id] = parsed

        expected_count = len(review_ids)
        if actual_count != expected_count:
            _add_blocking(
                blocking_errors,
                "part_count_mismatch",
                shard=shard,
                path=str(part_path),
                expected_count=expected_count,
                actual_count=actual_count,
            )

    for shard, review_id in expected_order:
        if shard in missing_part_shards:
            continue
        if review_id not in first_seen:
            _add_blocking(
                blocking_errors,
                "missing_review_id_global",
                shard=shard,
                review_id=review_id,
                path=part_paths_by_shard.get(shard),
            )

    for review_id, context in first_seen.items():
        if review_id not in expected_by_id:
            _add_blocking(
                blocking_errors,
                "extra_review_id_global",
                **context,
            )

    collected_records = _ordered_records(shards, review_ids_by_shard, records_by_shard)
    passed = not blocking_errors
    if passed:
        write_jsonl_objects(output, collected_records)

    counts = {
        "shards": len(shards),
        "part_files_read": part_files_read,
        "expected_review_ids": len(expected_order),
        "part_records": part_records,
        "collected_records": len(collected_records),
        "blocking_errors": len(blocking_errors),
        **decision_counts,
    }
    return {
        "passed": passed,
        "manifest": str(manifest_file),
        "output": str(output),
        "counts": counts,
        "blocking_errors": blocking_errors,
        "repair_hints": _repair_hints(blocking_errors, shard_info_by_name),
    }


def _manifest_shards(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    shards = manifest.get("shards", [])
    if not isinstance(shards, list):
        raise ValueError("manifest.shards must be a list")
    return shards


def _review_ids(shard_info: Mapping[str, Any]) -> list[str]:
    review_ids = shard_info.get("review_ids", [])
    if not isinstance(review_ids, list):
        raise ValueError("manifest shard review_ids must be a list")
    return [str(review_id) for review_id in review_ids]


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _add_blocking(
    errors: list[dict[str, Any]],
    error_type: str,
    **context: Any,
) -> None:
    error = {"type": error_type}
    for key, value in context.items():
        if value is not None:
            error[key] = value
    errors.append(error)


def _ordered_records(
    shards: Sequence[Mapping[str, Any]],
    review_ids_by_shard: Mapping[str, Sequence[str]],
    records_by_shard: Mapping[str, Mapping[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for shard_info in shards:
        shard = str(shard_info["shard"])
        shard_records = records_by_shard.get(shard, {})
        for review_id in review_ids_by_shard.get(shard, []):
            record = shard_records.get(review_id)
            if record is not None:
                records.append(record)
    return records


def _repair_hints(
    blocking_errors: Sequence[Mapping[str, Any]],
    shard_info_by_name: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    error_types_by_shard: dict[str, set[str]] = {}
    for error in blocking_errors:
        shard = error.get("shard")
        if shard is None:
            continue
        shard_name = str(shard)
        error_types_by_shard.setdefault(shard_name, set()).add(str(error["type"]))

    hints: list[dict[str, Any]] = []
    for shard in shard_info_by_name:
        error_types = error_types_by_shard.get(shard)
        if not error_types:
            continue
        expected_output = str(shard_info_by_name[shard].get("expected_output", ""))
        hints.append(
            {
                "shard": shard,
                "expected_output": expected_output,
                "blocking_error_types": sorted(error_types),
                "hint": "Rerun this decision shard and write the expected part file.",
            }
        )
    return hints
