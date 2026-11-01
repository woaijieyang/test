from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


DEFAULT_HASH_CHUNK_BYTES = 8 * 1024 * 1024


def sha256_file(
    path: str | Path,
    *,
    chunk_bytes: int = DEFAULT_HASH_CHUNK_BYTES,
) -> str:
    """Return the SHA-256 of one regular input file."""

    if chunk_bytes <= 0:
        raise ValueError("chunk_bytes must be positive")
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Input file does not exist: {source}")
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        while True:
            block = stream.read(chunk_bytes)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def file_provenance(
    path: str | Path,
    *,
    role: str | None = None,
) -> dict[str, Any]:
    """Describe an immutable input without modifying or resolving its path."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Input file does not exist: {source}")
    stat = source.stat()
    result: dict[str, Any] = {
        "path": str(source.absolute()),
        "sha256": sha256_file(source),
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }
    if role is not None:
        result["role"] = str(role)
    return result


def input_file_provenance(
    inputs: Mapping[str, str | Path],
) -> list[dict[str, Any]]:
    """Return role-labelled provenance in deterministic role order."""

    return [
        file_provenance(inputs[role], role=role)
        for role in sorted(inputs)
    ]


def exclusive_output_dir(path: str | Path) -> Path:
    """Create a new output directory and refuse every existing target."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(exist_ok=False)
    return output


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_exclusive(
    path: str | Path,
    write: Any,
) -> Path:
    """Publish a complete file atomically without an overwrite race.

    A temporary file is fully flushed in the destination directory, then
    hard-linked into place.  ``os.link`` is atomic and fails if the target
    already exists, unlike ``os.replace`` which could overwrite another run.
    """

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"Refusing to overwrite artifact: {target}")

    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, target)
        except FileExistsError as error:
            raise FileExistsError(
                f"Refusing to overwrite artifact: {target}"
            ) from error
        _fsync_directory(target.parent)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def write_json_atomic_exclusive(
    path: str | Path,
    value: Mapping[str, Any],
) -> Path:
    """Atomically publish one formatted JSON object."""

    if not isinstance(value, Mapping):
        raise TypeError("JSON artifact must be a mapping")

    def write(stream: Any) -> None:
        json.dump(
            dict(value),
            stream,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        stream.write("\n")

    return _atomic_write_exclusive(path, write)


def write_jsonl_atomic_exclusive(
    path: str | Path,
    records: Iterable[Mapping[str, Any]],
) -> Path:
    """Atomically publish JSONL and reject non-object records."""

    def write(stream: Any) -> None:
        for index, record in enumerate(records, start=1):
            if not isinstance(record, Mapping):
                raise TypeError(
                    f"JSONL record {index} is not a mapping: "
                    f"{type(record).__name__}"
                )
            stream.write(
                json.dumps(
                    dict(record),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            stream.write("\n")

    return _atomic_write_exclusive(path, write)
