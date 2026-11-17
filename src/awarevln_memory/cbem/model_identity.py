from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


MODEL_IDENTITY_SCHEMA = "cbem.model-identity.v1"
MODEL_ATTESTATION_SCHEMA = "cbem.model-attestation.v1"
_EXCLUDED_PARTS = frozenset({".git", ".cache", "__pycache__"})
_EXCLUDED_SUFFIXES = frozenset({".lock", ".pyc", ".tmp"})


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _bundle_files(model_root: Path) -> list[Path]:
    root = model_root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    candidates = [
        candidate
        for candidate in root.rglob("*")
        if not (_EXCLUDED_PARTS & set(candidate.relative_to(root).parts))
        and candidate.suffix not in _EXCLUDED_SUFFIXES
    ]
    symlinks = [candidate for candidate in candidates if candidate.is_symlink()]
    if symlinks:
        raise ValueError(
            "Base model bundle contains un-attestable child symlinks: "
            f"{[path.relative_to(root).as_posix() for path in symlinks[:8]]}"
        )
    files = sorted(candidate for candidate in candidates if candidate.is_file())
    if not files:
        raise ValueError(f"Base model bundle contains no regular files: {root}")
    return files


def _required_component_coverage(entries: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    paths = [str(entry["path"]) for entry in entries]
    lowered = {path: path.lower() for path in paths}
    groups = {
        "weights": [
            path for path, value in lowered.items()
            if value.endswith((".safetensors", ".bin", ".pt", ".pth"))
        ],
        "config": [path for path, value in lowered.items() if "config" in value],
        "tokenizer": [path for path, value in lowered.items() if "token" in value],
        "vision": [
            path for path, value in lowered.items()
            if any(key in value for key in ("vision", "image_processor", "preprocessor"))
        ],
        "projector": [
            path for path, value in lowered.items()
            if any(key in value for key in ("projector", "mm_projector"))
        ],
    }
    # LLaVA checkpoints commonly consolidate vision tower and multimodal
    # projector parameters into the same model weight shards.  In that case
    # those complete shards, together with config files, are the actual
    # artifacts to attest rather than separately named component files.
    if not groups["vision"] and groups["weights"] and groups["config"]:
        groups["vision"] = list(groups["weights"])
    if not groups["projector"] and groups["weights"] and groups["config"]:
        groups["projector"] = list(groups["weights"])
    missing = [name for name, values in groups.items() if not values]
    if missing:
        raise ValueError(
            "Base model attestation lacks required component coverage: "
            f"{missing}; every actual weight/config/tokenizer/vision/projector "
            "artifact must live inside the attested model bundle"
        )
    return groups


def build_model_identity(model_root: str | Path) -> dict[str, Any]:
    root = Path(model_root).resolve(strict=True)
    entries = []
    for path in _bundle_files(root):
        relative = path.relative_to(root).as_posix()
        entries.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    coverage = _required_component_coverage(entries)
    canonical_payload = {
        "schema_version": MODEL_IDENTITY_SCHEMA,
        "files": entries,
    }
    manifest_sha256 = hashlib.sha256(
        _canonical_json(canonical_payload)
    ).hexdigest()
    return {
        **canonical_payload,
        "canonical_manifest_sha256": manifest_sha256,
        "canonical_identity": f"sha256:{manifest_sha256}",
        "file_count": len(entries),
        "total_bytes": sum(int(entry["size"]) for entry in entries),
        "component_coverage": coverage,
    }


def write_model_attestation(
    model_root: str | Path, attestation_path: str | Path
) -> dict[str, Any]:
    output = Path(attestation_path)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite attestation: {output}")
    identity = build_model_identity(model_root)
    document = {
        "schema_version": MODEL_ATTESTATION_SCHEMA,
        "status": "complete",
        "model_root": str(Path(model_root).resolve(strict=True)),
        "identity": identity,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(output, flags, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    return document


def load_model_attestation(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError(f"Attestation must be a regular file: {source}")
    with source.open("r", encoding="utf-8") as stream:
        document = json.load(stream)
    if not isinstance(document, dict):
        raise ValueError("Model attestation must be a JSON object")
    if (
        document.get("schema_version") != MODEL_ATTESTATION_SCHEMA
        or document.get("status") != "complete"
    ):
        raise ValueError("Unsupported or incomplete model attestation")
    identity = document.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("Model attestation lacks identity")
    payload = {
        "schema_version": identity.get("schema_version"),
        "files": identity.get("files"),
    }
    actual_manifest_hash = hashlib.sha256(_canonical_json(payload)).hexdigest()
    if identity.get("canonical_manifest_sha256") != actual_manifest_hash:
        raise ValueError("Model attestation canonical manifest hash mismatch")
    if identity.get("canonical_identity") != f"sha256:{actual_manifest_hash}":
        raise ValueError("Model attestation canonical identity mismatch")
    entries = identity.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Model attestation has no file inventory")
    _required_component_coverage(entries)
    if int(identity.get("file_count", -1)) != len(entries):
        raise ValueError("Model attestation file_count mismatch")
    if int(identity.get("total_bytes", -1)) != sum(
        int(entry.get("size", -1)) for entry in entries
    ):
        raise ValueError("Model attestation total_bytes mismatch")
    return document


def verify_model_attestation(
    model_root: str | Path,
    attestation_path: str | Path,
    *,
    verify_content: bool,
    expected_attestation_sha256: str | None = None,
) -> dict[str, Any]:
    source = Path(attestation_path)
    if expected_attestation_sha256 is not None:
        if sha256_file(source) != expected_attestation_sha256:
            raise ValueError("Model attestation file SHA-256 mismatch")
    document = load_model_attestation(source)
    root = Path(model_root).resolve(strict=True)
    entries = document["identity"]["files"]
    declared_paths = [str(entry["path"]) for entry in entries]
    if declared_paths != sorted(declared_paths) or len(declared_paths) != len(
        set(declared_paths)
    ):
        raise ValueError("Model attestation inventory is unsorted or duplicated")
    actual_files = _bundle_files(root)
    actual_paths = [path.relative_to(root).as_posix() for path in actual_files]
    if actual_paths != declared_paths:
        raise ValueError("Base model file inventory differs from attestation")
    for path, entry in zip(actual_files, entries):
        if int(entry.get("size", -1)) != path.stat().st_size:
            raise ValueError(f"Base model file size mismatch: {entry['path']}")
        digest = str(entry.get("sha256") or "")
        if len(digest) != 64:
            raise ValueError(f"Invalid file digest in attestation: {entry['path']}")
        if verify_content and sha256_file(path) != digest:
            raise ValueError(f"Base model file hash mismatch: {entry['path']}")
    return {
        "canonical_identity": document["identity"]["canonical_identity"],
        "canonical_manifest_sha256": document["identity"][
            "canonical_manifest_sha256"
        ],
        "attestation_path": str(source.resolve()),
        "attestation_sha256": sha256_file(source),
        "verification_mode": "full_content" if verify_content else "inventory_size",
        "file_count": len(entries),
        "total_bytes": int(document["identity"]["total_bytes"]),
        "component_coverage": document["identity"]["component_coverage"],
    }


def canonical_identity(value: Mapping[str, Any] | str) -> str:
    if isinstance(value, Mapping):
        text = str(value.get("canonical_identity") or "").strip()
    else:
        text = str(value).strip()
    if not text.startswith("sha256:") or len(text) != 71:
        raise ValueError(
            "Base model identity must be a canonical sha256:<64 hex> identity; "
            "filesystem paths are not identities"
        )
    digest = text.removeprefix("sha256:")
    if any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("Base model canonical identity is not lowercase hex")
    return text


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or verify a CBEM base-model attestation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--model-root", type=Path, required=True)
    create.add_argument("--attestation", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--model-root", type=Path, required=True)
    verify.add_argument("--attestation", type=Path, required=True)
    verify.add_argument("--expected-attestation-sha256")
    verify.add_argument("--inventory-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "create":
        result = write_model_attestation(args.model_root, args.attestation)
        output = {
            "status": "complete",
            "canonical_identity": result["identity"]["canonical_identity"],
            "attestation": str(args.attestation.resolve()),
            "attestation_sha256": sha256_file(args.attestation),
        }
    else:
        output = verify_model_attestation(
            args.model_root,
            args.attestation,
            verify_content=not args.inventory_only,
            expected_attestation_sha256=args.expected_attestation_sha256,
        )
        output["status"] = "verified"
    json.dump(output, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
