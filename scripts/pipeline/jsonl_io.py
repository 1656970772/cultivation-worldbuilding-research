import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


def iter_jsonl_objects(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
            if not isinstance(parsed, dict):
                raise ValueError(f"{path}:{line_number}: JSON object required")
            yield line_number, parsed


def read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    return [item for _, item in iter_jsonl_objects(path)]


def write_jsonl_objects(path: Path, items: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for item in items:
            handle.write(
                json.dumps(
                    dict(item),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )


def jsonl_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_sha256(item: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(item),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
