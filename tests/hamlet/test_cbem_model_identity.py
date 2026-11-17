from __future__ import annotations

import pytest

from awarevln_memory.cbem.model_identity import (
    canonical_identity,
    verify_model_attestation,
    write_model_attestation,
)


def _bundle(root) -> None:
    root.mkdir()
    (root / "model-00001-of-00001.safetensors").write_bytes(b"weights")
    (root / "config.json").write_text(
        '{"mm_vision_tower":"vision","mm_projector_type":"mlp"}\n',
        encoding="utf-8",
    )
    (root / "tokenizer.json").write_text("{}\n", encoding="utf-8")


def test_attestation_uses_content_identity_not_path_and_detects_tamper(
    tmp_path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _bundle(first)
    _bundle(second)
    first_attestation = tmp_path / "first.json"
    second_attestation = tmp_path / "second.json"
    first_document = write_model_attestation(first, first_attestation)
    second_document = write_model_attestation(second, second_attestation)
    first_identity = first_document["identity"]["canonical_identity"]
    assert first_identity == second_document["identity"]["canonical_identity"]
    assert canonical_identity(first_identity) == first_identity
    verified = verify_model_attestation(
        first, first_attestation, verify_content=True
    )
    assert verified["verification_mode"] == "full_content"
    (first / "model-00001-of-00001.safetensors").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="size mismatch|hash mismatch"):
        verify_model_attestation(
            first, first_attestation, verify_content=True
        )


def test_filesystem_path_is_not_a_canonical_identity(tmp_path) -> None:
    with pytest.raises(ValueError, match="filesystem paths are not identities"):
        canonical_identity(str(tmp_path))
