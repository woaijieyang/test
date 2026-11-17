from __future__ import annotations

import json

import pytest
import torch

from awarevln_memory.cbem.artifacts import file_provenance
from awarevln_memory.cbem.config import CBEMConfig
from awarevln_memory.cbem.router import CBEMRouter
from awarevln_memory.cbem.validate_deployment import validate_deployment
from awarevln_memory.config import MemoryAdapterConfig
from awarevln_memory.memory.adapter import AwareVLNMemoryAdapter
from awarevln_memory.memory.state import EpisodeMemory, MemoryItem


def router_config(*, none_logit_init: float = 4.0) -> CBEMConfig:
    return CBEMConfig(
        adapter_hidden_size=8,
        rank=4,
        memory_types=3,
        max_age=8,
        prefilter_top_k=4,
        selected_top_k=2,
        archive_capacity=4,
        none_logit_init=none_logit_init,
    )


def adapter_config() -> MemoryAdapterConfig:
    return MemoryAdapterConfig(
        llm_hidden_size=16,
        memory_hidden_size=8,
        moment_tokens=4,
        memory_layers=1,
        memory_heads=2,
        recent_calls=2,
        max_event_items=2,
        output_memory_tokens=4,
        max_age=8,
        dropout=0.0,
        alpha_init=0.25,
    )


def write_training_manifest(
    checkpoint,
    path,
    *,
    passed: bool,
    require_completion: bool = False,
) -> dict:
    gate = {"passed": passed}
    document = {
        "schema_version": "cbem.training-manifest.v2",
        "status": "complete",
        "deployment_eligible": passed,
        "final_gate": gate,
        "artifacts": {
            "checkpoint_config": file_provenance(
                checkpoint / CBEMRouter.CONFIG_NAME
            ),
            "checkpoint_weights": file_provenance(
                checkpoint / CBEMRouter.WEIGHTS_NAME
            ),
            "checkpoint_artifact_manifest": file_provenance(
                checkpoint / "artifact_manifest.json"
            ),
        },
    }
    if require_completion:
        document["completion_contract"] = {
            "schema_version": "cbem.run-completion.v1",
            "required_final_marker": "run_completion.json",
            "complete_iff_marker_hashes_validate": True,
            "training_manifest_alone_is_not_run_completion": True,
        }
    path.write_text(
        json.dumps(document, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return gate


def write_run_completion(checkpoint, training, *, passed: bool) -> None:
    document = {
        "schema_version": "cbem.run-completion.v1",
        "status": "complete",
        "deployment_eligible": passed,
        "metrics_reportable": True,
        "training_manifest": file_provenance(training),
        "deployment_manifest": file_provenance(
            checkpoint / "deployment_manifest.json"
        ),
    }
    (training.parent / "run_completion.json").write_text(
        json.dumps(document, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def completion_case(tmp_path):
    adapter = tmp_path / "adapter-completion"
    adapter.mkdir()
    (adapter / "memory_adapter.safetensors").write_bytes(b"weights")
    (adapter / "memory_config.json").write_text("{}\n", encoding="utf-8")
    identity = "sha256:" + "f" * 64
    checkpoint = tmp_path / "router-completion"
    CBEMRouter(router_config()).save_pretrained(
        checkpoint,
        source_adapter=adapter,
        base_model_identity=identity,
    )
    training = tmp_path / "training-completion.json"
    write_training_manifest(
        checkpoint,
        training,
        passed=True,
        require_completion=True,
    )
    CBEMRouter.write_deployment_manifest(
        checkpoint,
        training_manifest=training,
        final_gate={"passed": True},
        deployment_eligible=True,
    )
    return adapter, checkpoint, training, identity


def test_completion_contract_rejects_missing_marker(tmp_path) -> None:
    _, checkpoint, _, _ = completion_case(tmp_path)
    with pytest.raises(FileNotFoundError, match="run_completion"):
        validate_deployment(checkpoint)


def test_completion_contract_rejects_forged_manifest_path(tmp_path) -> None:
    _, checkpoint, training, _ = completion_case(tmp_path)
    write_run_completion(checkpoint, training, passed=True)
    marker_path = tmp_path / "run_completion.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["training_manifest"]["path"] = str(tmp_path / "forged.json")
    marker_path.write_text(
        json.dumps(marker, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="training_manifest path/SHA-256"):
        validate_deployment(checkpoint)


def test_completion_contract_rejects_hash_mismatch(tmp_path) -> None:
    _, checkpoint, training, _ = completion_case(tmp_path)
    write_run_completion(checkpoint, training, passed=True)
    marker_path = tmp_path / "run_completion.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["deployment_manifest"]["sha256"] = "0" * 64
    marker_path.write_text(
        json.dumps(marker, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="deployment_manifest path/SHA-256"):
        validate_deployment(checkpoint)


def test_completion_contract_rejects_failure_coexistence(tmp_path) -> None:
    adapter, checkpoint, training, identity = completion_case(tmp_path)
    write_run_completion(checkpoint, training, passed=True)
    (tmp_path / "failure.json").write_text(
        '{"status":"failed"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="contains failure.json"):
        CBEMRouter.from_pretrained(
            checkpoint,
            expected_source_adapter=adapter,
            expected_base_model_identity=identity,
        )


def test_archive_is_causal_capped_and_cleared() -> None:
    state = EpisodeMemory(max_archive_items=2)
    state.observe(torch.randn(4, 16), 0)
    state.observe(torch.randn(4, 16), 1)
    state.observe(torch.randn(4, 16), 2)
    tensors = state.as_tensors(condition="archive")
    assert tensors["item_ids"] == ["archive_000001", "archive_000002"]
    assert tensors["memory_types"].tolist() == [[2, 2]]
    assert tensors["memory_ages"].tolist() == [[2, 1]]
    state.clear()
    assert state.as_tensors(condition="archive")["item_ids"] == []


def test_archive_rejects_current_or_future_item() -> None:
    state = EpisodeMemory(max_archive_items=2)
    state.current_policy_call = 3
    state.archive.append(
        MemoryItem(
            moment=torch.randn(4, 16),
            policy_call_id=3,
            item_id="archive_000003",
        )
    )
    with pytest.raises(RuntimeError, match="current/future"):
        state.as_tensors(condition="archive")


def test_router_empty_mask_abstains_and_metrics_are_finite_json() -> None:
    router = CBEMRouter(router_config()).eval()
    selection = router(
        current_query=torch.randn(1, 4, 8),
        memory_items=torch.randn(1, 4, 8),
        memory_mask=torch.zeros(1, 4, dtype=torch.bool),
    )
    assert not selection.use_memory.item()
    assert not selection.selected_mask.any()
    encoded = json.dumps(selection.detached_metrics(), allow_nan=False)
    assert "Infinity" not in encoded


def test_forced_read_preserves_fixed_k_and_audits_insertion() -> None:
    torch.manual_seed(11)
    router = CBEMRouter(router_config(none_logit_init=-20.0)).eval()
    selection = router(
        current_query=torch.randn(1, 4, 8),
        memory_items=torch.randn(1, 4, 8),
        memory_mask=torch.ones(1, 4, dtype=torch.bool),
    )
    selected = {
        int(index)
        for index, enabled in zip(
            selection.selected_indices[0].tolist(),
            selection.selected_mask[0].tolist(),
        )
        if enabled
    }
    target = next(index for index in range(4) if index not in selected)
    post, audit = router.force_include_indices(
        selection,
        torch.tensor([target]),
        item_count=4,
    )
    assert post.selected_mask.sum().item() == selection.selected_mask.sum().item()
    assert target in post.selected_indices[0][post.selected_mask[0]].tolist()
    assert audit["target_was_selected"].tolist() == [False]
    assert audit["inserted"].tolist() == [True]
    forced_slot = int(audit["forced_slots"].item())
    assert forced_slot == 1
    assert int(audit["displaced_indices"].item()) == int(
        selection.selected_indices[0, forced_slot].item()
    )
    for slot in range(selection.selected_indices.shape[1]):
        if slot != forced_slot:
            assert torch.equal(
                post.selected_indices[:, slot],
                selection.selected_indices[:, slot],
            )

    already = int(post.selected_indices[0, 0].item())
    unchanged, second_audit = router.force_include_indices(
        post,
        torch.tensor([already]),
        item_count=4,
    )
    assert torch.equal(unchanged.selected_indices, post.selected_indices)
    assert torch.equal(unchanged.selected_mask, post.selected_mask)
    assert second_audit["target_was_selected"].tolist() == [True]
    assert second_audit["inserted"].tolist() == [False]
    assert second_audit["forced_slots"].tolist() == [-1]


def test_none_selection_is_exact_adapter_empty_fallback() -> None:
    torch.manual_seed(7)
    adapter = AwareVLNMemoryAdapter(adapter_config()).eval()
    router = CBEMRouter(router_config(none_logit_init=20.0)).eval()
    inputs = torch.randn(1, 7, 16)
    raw_memory = torch.randn(1, 4, 4, 16)
    query = adapter.query_encoder(inputs, None)
    items = adapter.reader._collapse_moments(raw_memory)
    selection = router(query, items)
    selected_memory = router.select_tensor(raw_memory, selection)
    output = adapter(
        inputs,
        memory_moments=selected_memory,
        memory_mask=selection.selected_mask,
        memory_types=torch.zeros_like(selection.selected_indices),
        memory_ages=torch.zeros_like(selection.selected_indices),
    )
    empty = adapter(inputs, memory_moments=None)
    assert not selection.selected_mask.any()
    assert torch.equal(output.adapted_inputs, inputs)
    assert torch.equal(output.adapted_inputs, empty.adapted_inputs)
    assert torch.equal(output.read_probability, empty.read_probability)


def test_checkpoint_is_bound_to_adapter_and_base_identity(tmp_path) -> None:
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "memory_adapter.safetensors").write_bytes(b"weights-a")
    (adapter / "memory_config.json").write_text("{}\n", encoding="utf-8")
    base_identity = "sha256:" + "a" * 64
    router = CBEMRouter(router_config()).eval()
    checkpoint = tmp_path / "router"
    router.save_pretrained(
        checkpoint,
        source_adapter=adapter,
        base_model_identity=base_identity,
    )
    training_manifest = tmp_path / "training_manifest.json"
    write_training_manifest(
        checkpoint, training_manifest, passed=True
    )
    CBEMRouter.write_deployment_manifest(
        checkpoint,
        training_manifest=training_manifest,
        final_gate={"passed": True},
        deployment_eligible=True,
    )
    loaded = CBEMRouter.from_pretrained(
        checkpoint,
        expected_source_adapter=adapter,
        expected_base_model_identity=base_identity,
    )
    assert loaded.config == router.config

    wrong_adapter = tmp_path / "wrong-adapter"
    wrong_adapter.mkdir()
    (wrong_adapter / "memory_adapter.safetensors").write_bytes(b"weights-b")
    (wrong_adapter / "memory_config.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        CBEMRouter.from_pretrained(
            checkpoint,
            expected_source_adapter=wrong_adapter,
            expected_base_model_identity=base_identity,
        )


def test_non_deployable_checkpoint_requires_explicit_offline_override(
    tmp_path,
) -> None:
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "memory_adapter.safetensors").write_bytes(b"weights")
    (adapter / "memory_config.json").write_text("{}\n", encoding="utf-8")
    checkpoint = tmp_path / "router"
    identity = "sha256:" + "b" * 64
    CBEMRouter(router_config()).save_pretrained(
        checkpoint,
        source_adapter=adapter,
        base_model_identity=identity,
    )
    training = tmp_path / "training.json"
    write_training_manifest(checkpoint, training, passed=False)
    CBEMRouter.write_deployment_manifest(
        checkpoint,
        training_manifest=training,
        final_gate={"passed": False},
        deployment_eligible=False,
    )
    with pytest.raises(ValueError, match="failed its final offline"):
        CBEMRouter.from_pretrained(
            checkpoint,
            expected_source_adapter=adapter,
            expected_base_model_identity=identity,
        )
    loaded = CBEMRouter.from_pretrained(
        checkpoint,
        expected_source_adapter=adapter,
        expected_base_model_identity=identity,
        allow_non_deployable=True,
    )
    assert loaded.deployment_disclosure["override_used"] is True


def test_writer_rejects_status_only_training_manifest(tmp_path) -> None:
    adapter = tmp_path / "adapter-status-only"
    adapter.mkdir()
    (adapter / "memory_adapter.safetensors").write_bytes(b"weights")
    (adapter / "memory_config.json").write_text("{}\n", encoding="utf-8")
    checkpoint = tmp_path / "router-status-only"
    CBEMRouter(router_config()).save_pretrained(
        checkpoint,
        source_adapter=adapter,
        base_model_identity="sha256:" + "c" * 64,
    )
    training = tmp_path / "status-only.json"
    training.write_text('{"status":"complete"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="CBEM training manifest"):
        CBEMRouter.write_deployment_manifest(
            checkpoint,
            training_manifest=training,
            final_gate={"passed": True},
            deployment_eligible=True,
        )


def test_negative_training_cannot_be_promoted_by_certificate(tmp_path) -> None:
    adapter = tmp_path / "adapter-negative"
    adapter.mkdir()
    (adapter / "memory_adapter.safetensors").write_bytes(b"weights")
    (adapter / "memory_config.json").write_text("{}\n", encoding="utf-8")
    checkpoint = tmp_path / "router-negative"
    identity = "sha256:" + "d" * 64
    CBEMRouter(router_config()).save_pretrained(
        checkpoint,
        source_adapter=adapter,
        base_model_identity=identity,
    )
    training = tmp_path / "negative-training.json"
    write_training_manifest(checkpoint, training, passed=False)
    with pytest.raises(ValueError, match="exactly match training"):
        CBEMRouter.write_deployment_manifest(
            checkpoint,
            training_manifest=training,
            final_gate={"passed": True},
            deployment_eligible=True,
        )

    forged = {
        "schema_version": "cbem.deployment-manifest.v1",
        "status": "complete",
        "deployment_eligible": True,
        "final_gate": {"passed": True},
        "artifact_manifest": file_provenance(
            checkpoint / "artifact_manifest.json"
        ),
        "training_manifest": file_provenance(training),
    }
    (checkpoint / "deployment_manifest.json").write_text(
        json.dumps(forged, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not match training"):
        validate_deployment(checkpoint)
    with pytest.raises(ValueError, match="does not match training"):
        CBEMRouter.from_pretrained(
            checkpoint,
            expected_source_adapter=adapter,
            expected_base_model_identity=identity,
            allow_non_deployable=True,
        )


def test_writer_rejects_wrong_checkpoint_hash_in_training_manifest(
    tmp_path,
) -> None:
    adapter = tmp_path / "adapter-wrong-hash"
    adapter.mkdir()
    (adapter / "memory_adapter.safetensors").write_bytes(b"weights")
    (adapter / "memory_config.json").write_text("{}\n", encoding="utf-8")
    checkpoint = tmp_path / "router-wrong-hash"
    CBEMRouter(router_config()).save_pretrained(
        checkpoint,
        source_adapter=adapter,
        base_model_identity="sha256:" + "e" * 64,
    )
    training = tmp_path / "wrong-hash-training.json"
    write_training_manifest(checkpoint, training, passed=True)
    document = json.loads(training.read_text(encoding="utf-8"))
    document["artifacts"]["checkpoint_config"]["sha256"] = "0" * 64
    training.write_text(
        json.dumps(document, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="checkpoint_config SHA-256 mismatch"):
        CBEMRouter.write_deployment_manifest(
            checkpoint,
            training_manifest=training,
            final_gate={"passed": True},
            deployment_eligible=True,
        )


def test_config_rejects_prefilter_larger_than_archive() -> None:
    with pytest.raises(ValueError, match="archive_capacity"):
        CBEMConfig(
            adapter_hidden_size=8,
            rank=4,
            memory_types=3,
            max_age=8,
            prefilter_top_k=5,
            selected_top_k=2,
            archive_capacity=4,
        )
