from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Optional

import torch
import torch.nn.functional as F
from safetensors.torch import load_file, save_file
from torch import Tensor, nn

from awarevln_memory.cbem.artifacts import (
    exclusive_output_dir,
    file_provenance,
    write_json_atomic_exclusive,
)
from awarevln_memory.cbem.config import CBEMConfig
from awarevln_memory.cbem.model_identity import canonical_identity

TRAINING_MANIFEST_SCHEMA = "cbem.training-manifest.v2"
DEPLOYMENT_MANIFEST_SCHEMA = "cbem.deployment-manifest.v1"
CHECKPOINT_MANIFEST_SCHEMA = "cbem.checkpoint-manifest.v2"
RUN_COMPLETION_SCHEMA = "cbem.run-completion.v1"


def _read_manifest_object(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError(f"Expected regular manifest: {source}")
    with source.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {source}")
    return value


def _regular_file_provenance(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError(f"Expected regular checkpoint file: {source}")
    return file_provenance(source)


def _validate_run_completion(
    *,
    training_path: Path,
    training: dict[str, Any],
    training_provenance: dict[str, Any],
    deployment_path: Path,
    deployment: dict[str, Any],
    deployment_provenance: dict[str, Any],
) -> dict[str, Any] | None:
    """Require the final run marker for manifests that opt into the contract."""

    contract = training.get("completion_contract")
    if contract is None:
        return None
    if not isinstance(contract, dict):
        raise ValueError("Training completion_contract must be an object")
    if (
        contract.get("schema_version") != RUN_COMPLETION_SCHEMA
        or contract.get("required_final_marker") != "run_completion.json"
        or contract.get("complete_iff_marker_hashes_validate") is not True
        or contract.get("training_manifest_alone_is_not_run_completion")
        is not True
    ):
        raise ValueError("Unsupported CBEM run completion contract")

    run_root = training_path.parent
    failure_path = run_root / "failure.json"
    if failure_path.exists() or failure_path.is_symlink():
        raise ValueError(
            "CBEM run contains failure.json and is not deployable"
        )
    completion_path = run_root / "run_completion.json"
    completion = _read_manifest_object(completion_path)
    if (
        completion.get("schema_version") != RUN_COMPLETION_SCHEMA
        or completion.get("status") != "complete"
    ):
        raise ValueError("Unsupported or incomplete CBEM run completion marker")
    if completion.get("metrics_reportable") is not True:
        raise ValueError("CBEM run completion does not permit metric reporting")
    if (
        completion.get("deployment_eligible")
        != deployment.get("deployment_eligible")
    ):
        raise ValueError(
            "Run completion eligibility disagrees with deployment manifest"
        )

    for role, reference, provenance in (
        (
            "training_manifest",
            completion.get("training_manifest"),
            training_provenance,
        ),
        (
            "deployment_manifest",
            completion.get("deployment_manifest"),
            deployment_provenance,
        ),
    ):
        if not isinstance(reference, dict):
            raise ValueError(
                f"Run completion lacks bound {role}"
            )
        if (
            reference.get("path") != provenance["path"]
            or reference.get("sha256") != provenance["sha256"]
        ):
            raise ValueError(
                f"Run completion {role} path/SHA-256 mismatch"
            )

    return {
        "manifest": completion,
        "provenance": _regular_file_provenance(completion_path),
    }


def load_and_validate_training_manifest(
    *,
    checkpoint_dir: str | Path,
    training_manifest: str | Path,
) -> dict[str, Any]:
    """Load and strictly bind a v2 training manifest to one checkpoint."""

    checkpoint = Path(checkpoint_dir)
    training_path = Path(training_manifest)
    training = _read_manifest_object(training_path)
    if (
        training.get("schema_version") != TRAINING_MANIFEST_SCHEMA
        or training.get("status") != "complete"
    ):
        raise ValueError(
            "Unsupported or incomplete CBEM training manifest"
        )
    gate = training.get("final_gate")
    eligible = training.get("deployment_eligible")
    if not isinstance(gate, dict) or not isinstance(gate.get("passed"), bool):
        raise ValueError("Training manifest lacks boolean final_gate.passed")
    if not isinstance(eligible, bool) or eligible != gate["passed"]:
        raise ValueError("Training deployment_eligible disagrees with final_gate")

    checkpoint_paths = {
        "checkpoint_config": checkpoint / CBEMRouter.CONFIG_NAME,
        "checkpoint_weights": checkpoint / CBEMRouter.WEIGHTS_NAME,
        "checkpoint_artifact_manifest": checkpoint / "artifact_manifest.json",
    }
    checkpoint_files = {
        role: _regular_file_provenance(path)
        for role, path in checkpoint_paths.items()
    }
    artifact = _read_manifest_object(
        checkpoint_paths["checkpoint_artifact_manifest"]
    )
    if (
        artifact.get("schema_version") != CHECKPOINT_MANIFEST_SCHEMA
        or artifact.get("status") != "complete"
    ):
        raise ValueError("Unsupported or incomplete checkpoint artifact manifest")
    artifact_records = artifact.get("artifacts")
    if not isinstance(artifact_records, dict):
        raise ValueError("Checkpoint artifact manifest lacks artifacts")
    for artifact_key, role in (
        ("config", "checkpoint_config"),
        ("weights", "checkpoint_weights"),
    ):
        record = artifact_records.get(artifact_key)
        if (
            not isinstance(record, dict)
            or record.get("sha256") != checkpoint_files[role]["sha256"]
        ):
            raise ValueError(
                f"Checkpoint artifact manifest {artifact_key} SHA-256 mismatch"
            )

    training_records = training.get("artifacts")
    if not isinstance(training_records, dict):
        raise ValueError("Training manifest lacks checkpoint artifacts")
    for role in checkpoint_paths:
        record = training_records.get(role)
        if (
            not isinstance(record, dict)
            or record.get("sha256") != checkpoint_files[role]["sha256"]
        ):
            raise ValueError(
                f"Training manifest {role} SHA-256 mismatch"
            )

    return {
        "manifest": training,
        "provenance": _regular_file_provenance(training_path),
        "artifact_manifest": artifact,
        "checkpoint_files": checkpoint_files,
    }


def validate_deployment_contract(
    checkpoint_dir: str | Path,
    *,
    deployment_manifest: str | Path | None = None,
    require_eligible: bool,
) -> dict[str, Any]:
    """Validate one deployment certificate against training and checkpoint."""

    checkpoint = Path(checkpoint_dir)
    deployment_path = (
        Path(deployment_manifest)
        if deployment_manifest is not None
        else checkpoint / "deployment_manifest.json"
    )
    deployment = _read_manifest_object(deployment_path)
    if (
        deployment.get("schema_version") != DEPLOYMENT_MANIFEST_SCHEMA
        or deployment.get("status") != "complete"
    ):
        raise ValueError("Unsupported or incomplete deployment manifest")
    artifact_reference = deployment.get("artifact_manifest")
    training_reference = deployment.get("training_manifest")
    if not isinstance(artifact_reference, dict) or not isinstance(
        training_reference, dict
    ):
        raise ValueError("Deployment manifest lacks bound input manifests")

    artifact_path = checkpoint / "artifact_manifest.json"
    artifact_provenance = _regular_file_provenance(artifact_path)
    if artifact_reference.get("sha256") != artifact_provenance["sha256"]:
        raise ValueError("Deployment artifact-manifest SHA-256 mismatch")
    training_path = Path(str(training_reference.get("path") or ""))
    training_validation = load_and_validate_training_manifest(
        checkpoint_dir=checkpoint,
        training_manifest=training_path,
    )
    training_provenance = training_validation["provenance"]
    if training_reference.get("sha256") != training_provenance["sha256"]:
        raise ValueError("Deployment training-manifest SHA-256 mismatch")
    deployment_provenance = _regular_file_provenance(deployment_path)

    deployment_gate = deployment.get("final_gate")
    deployment_eligible = deployment.get("deployment_eligible")
    if not isinstance(deployment_gate, dict) or not isinstance(
        deployment_gate.get("passed"), bool
    ):
        raise ValueError("Deployment manifest lacks boolean final_gate.passed")
    if not isinstance(deployment_eligible, bool):
        raise ValueError("Deployment manifest lacks boolean deployment_eligible")
    training = training_validation["manifest"]
    training_gate = training["final_gate"]
    training_eligible = training["deployment_eligible"]
    if deployment_gate != training_gate:
        raise ValueError("Deployment final_gate does not match training final_gate")
    if (
        deployment_eligible != training_eligible
        or deployment_eligible != deployment_gate["passed"]
    ):
        raise ValueError(
            "Deployment eligibility disagrees with training and final_gate"
        )
    completion_validation = _validate_run_completion(
        training_path=training_path,
        training=training,
        training_provenance=training_provenance,
        deployment_path=deployment_path,
        deployment=deployment,
        deployment_provenance=deployment_provenance,
    )
    if require_eligible and not deployment_eligible:
        raise ValueError(
            "CBEM checkpoint failed its final offline deployment gate"
        )

    return {
        "deployment_manifest": deployment,
        "deployment_provenance": deployment_provenance,
        "artifact_manifest_provenance": artifact_provenance,
        "training_manifest": training,
        "training_manifest_provenance": training_provenance,
        "run_completion": completion_validation,
        "deployment_eligible": deployment_eligible,
        "final_gate": deployment_gate,
    }


@dataclass
class CBEMSelection:
    """Auditable result of query-conditioned memory selection."""

    coarse_indices: Tensor
    candidate_logits: Tensor
    candidate_mask: Tensor
    none_logit: Tensor
    none_probability: Tensor
    memory_probability: Tensor
    use_memory: Tensor
    selected_indices: Tensor
    selected_mask: Tensor
    selected_scores: Tensor

    def detached_metrics(self) -> dict[str, Any]:
        def values(tensor: Tensor) -> Any:
            result = tensor.detach().cpu()
            if result.numel() == 1:
                return result.item()
            return result.tolist()

        return {
            "cbem_none_probability": values(self.none_probability.float()),
            "cbem_memory_probability": values(
                self.memory_probability.float()
            ),
            "cbem_use_memory": values(self.use_memory),
            "cbem_selected_indices": values(self.selected_indices),
            "cbem_selected_mask": values(self.selected_mask),
            "cbem_selected_scores": values(
                torch.where(
                    self.selected_mask,
                    self.selected_scores.float(),
                    torch.zeros_like(self.selected_scores.float()),
                )
            ),
            "cbem_candidate_scores": values(
                torch.where(
                    self.candidate_mask,
                    self.candidate_logits.float(),
                    torch.zeros_like(self.candidate_logits.float()),
                )
            ),
        }


class CBEMRouter(nn.Module):
    """Rank historical moments against an explicit learned NONE candidate.

    The router consumes frozen adapter-space features.  A parameter-free
    cosine prefilter limits compute, then a small learned scorer ranks each
    remaining moment relative to NONE.  There is no global read threshold:
    if NONE wins, every selected mask is false and the frozen memory adapter
    receives an empty row, yielding an exact baseline fallback.
    """

    CONFIG_NAME = "cbem_config.json"
    WEIGHTS_NAME = "cbem_router.safetensors"

    def __init__(self, config: CBEMConfig) -> None:
        super().__init__()
        self.config = config
        hidden = config.adapter_hidden_size
        rank = config.rank
        self.query_norm = nn.LayerNorm(hidden)
        self.memory_norm = nn.LayerNorm(hidden)
        self.query_projection = nn.Linear(hidden, rank, bias=False)
        self.memory_projection = nn.Linear(hidden, rank, bias=False)
        self.type_embedding = nn.Embedding(config.memory_types, rank)
        self.age_embedding = nn.Embedding(config.max_age + 1, rank)
        self.none_head = nn.Linear(hidden, 1)
        self.logit_scale = nn.Parameter(torch.zeros(()))
        nn.init.zeros_(self.none_head.weight)
        nn.init.constant_(self.none_head.bias, config.none_logit_init)

    @staticmethod
    def _validate_inputs(
        current_query: Tensor,
        memory_items: Tensor,
        memory_mask: Optional[Tensor],
        memory_types: Optional[Tensor],
        memory_ages: Optional[Tensor],
    ) -> tuple[Tensor, Tensor, Tensor]:
        if current_query.ndim != 3:
            raise ValueError(
                "current_query must have shape [B,Q,D], got "
                f"{tuple(current_query.shape)}"
            )
        if memory_items.ndim != 3:
            raise ValueError(
                "memory_items must have shape [B,N,D], got "
                f"{tuple(memory_items.shape)}"
            )
        if current_query.shape[0] != memory_items.shape[0]:
            raise ValueError("Query and memory batch sizes differ")
        if current_query.shape[-1] != memory_items.shape[-1]:
            raise ValueError("Query and memory hidden sizes differ")
        batch, items, _ = memory_items.shape
        device = memory_items.device
        if memory_mask is None:
            memory_mask = torch.ones(
                batch, items, dtype=torch.bool, device=device
            )
        else:
            memory_mask = memory_mask.to(device=device, dtype=torch.bool)
        if memory_types is None:
            memory_types = torch.zeros(
                batch, items, dtype=torch.long, device=device
            )
        else:
            memory_types = memory_types.to(device=device, dtype=torch.long)
        if memory_ages is None:
            memory_ages = torch.zeros(
                batch, items, dtype=torch.long, device=device
            )
        else:
            memory_ages = memory_ages.to(device=device, dtype=torch.long)
        expected = (batch, items)
        for name, tensor in (
            ("memory_mask", memory_mask),
            ("memory_types", memory_types),
            ("memory_ages", memory_ages),
        ):
            if tuple(tensor.shape) != expected:
                raise ValueError(
                    f"{name} must have shape {expected}, got "
                    f"{tuple(tensor.shape)}"
                )
        return memory_mask, memory_types, memory_ages

    @staticmethod
    def _gather_items(values: Tensor, indices: Tensor) -> Tensor:
        if values.ndim == 2:
            return torch.gather(values, 1, indices)
        expanded = indices.unsqueeze(-1).expand(
            *indices.shape, values.shape[-1]
        )
        return torch.gather(values, 1, expanded)

    def forward(
        self,
        current_query: Tensor,
        memory_items: Tensor,
        memory_mask: Optional[Tensor] = None,
        memory_types: Optional[Tensor] = None,
        memory_ages: Optional[Tensor] = None,
    ) -> CBEMSelection:
        memory_mask, memory_types, memory_ages = self._validate_inputs(
            current_query,
            memory_items,
            memory_mask,
            memory_types,
            memory_ages,
        )
        valid_types = memory_types[memory_mask]
        if valid_types.numel() and (
            valid_types.min() < 0
            or valid_types.max() >= self.config.memory_types
        ):
            raise ValueError(
                "memory_types contains an unsupported valid-item type"
            )
        valid_ages = memory_ages[memory_mask]
        if valid_ages.numel() and valid_ages.min() < 0:
            raise ValueError("memory_ages contains a negative valid-item age")
        batch, item_count, _ = memory_items.shape
        if item_count == 0:
            raise ValueError(
                "CBEMRouter expects a padded memory row; use an all-false "
                "mask for empty memory"
            )

        pooled_query = current_query.mean(dim=1).float()
        normalized_query = F.normalize(pooled_query, dim=-1)
        normalized_items = F.normalize(memory_items.float(), dim=-1)
        coarse_logits = torch.einsum(
            "bd,bnd->bn", normalized_query, normalized_items
        )
        coarse_logits = coarse_logits.masked_fill(~memory_mask, float("-inf"))

        prefilter_count = min(self.config.prefilter_top_k, item_count)
        coarse_values, coarse_indices = torch.topk(
            coarse_logits, k=prefilter_count, dim=1
        )
        candidate_mask = torch.isfinite(coarse_values)
        candidate_items = self._gather_items(memory_items, coarse_indices)
        candidate_types = self._gather_items(memory_types, coarse_indices)
        candidate_ages = self._gather_items(memory_ages, coarse_indices)

        query_key = F.normalize(
            self.query_projection(self.query_norm(pooled_query)), dim=-1
        )
        memory_key = self.memory_projection(
            self.memory_norm(candidate_items.float())
        )
        memory_key = memory_key + self.type_embedding(
            candidate_types.clamp(0, self.config.memory_types - 1)
        )
        memory_key = memory_key + self.age_embedding(
            candidate_ages.clamp(0, self.config.max_age)
        )
        memory_key = F.normalize(memory_key, dim=-1)
        scale = self.logit_scale.exp().clamp(max=100.0)
        candidate_logits = torch.einsum(
            "bd,bkd->bk", query_key, memory_key
        ) * scale
        candidate_logits = candidate_logits.masked_fill(
            ~candidate_mask, float("-inf")
        )
        none_logit = self.none_head(self.query_norm(pooled_query)).squeeze(-1)
        probabilities = torch.softmax(
            torch.cat([candidate_logits, none_logit[:, None]], dim=1),
            dim=1,
        )
        none_probability = probabilities[:, -1]
        memory_probability = 1.0 - none_probability
        best_candidate = candidate_logits.max(dim=1).values
        use_memory = torch.isfinite(best_candidate) & (
            best_candidate > none_logit
        )

        selected_count = min(
            self.config.selected_top_k, prefilter_count
        )
        selected_scores, local_indices = torch.topk(
            candidate_logits, k=selected_count, dim=1
        )
        selected_indices = self._gather_items(
            coarse_indices, local_indices
        )
        selected_mask = torch.isfinite(selected_scores)
        selected_mask &= selected_scores > none_logit[:, None]
        selected_mask &= use_memory[:, None]
        selected_indices = torch.where(
            selected_mask,
            selected_indices,
            torch.full_like(selected_indices, -1),
        )
        return CBEMSelection(
            coarse_indices=coarse_indices,
            candidate_logits=candidate_logits,
            candidate_mask=candidate_mask,
            none_logit=none_logit,
            none_probability=none_probability,
            memory_probability=memory_probability,
            use_memory=use_memory,
            selected_indices=selected_indices,
            selected_mask=selected_mask,
            selected_scores=selected_scores,
        )

    @staticmethod
    def select_tensor(
        values: Optional[Tensor],
        selection: CBEMSelection,
    ) -> Optional[Tensor]:
        if values is None:
            return None
        indices = selection.selected_indices.clamp_min(0)
        if values.ndim == 2:
            selected = torch.gather(values, 1, indices)
        elif values.ndim >= 3:
            view = indices
            for _ in range(values.ndim - 2):
                view = view.unsqueeze(-1)
            view = view.expand(
                *indices.shape,
                *values.shape[2:],
            )
            selected = torch.gather(values, 1, view)
        else:
            raise ValueError(
                f"Cannot select from tensor with shape {tuple(values.shape)}"
            )
        mask = selection.selected_mask
        for _ in range(selected.ndim - 2):
            mask = mask.unsqueeze(-1)
        return torch.where(mask, selected, torch.zeros_like(selected))

    @staticmethod
    def force_include_indices(
        selection: CBEMSelection,
        forced_indices: Tensor,
        *,
        item_count: int,
    ) -> tuple[CBEMSelection, dict[str, Tensor]]:
        """Force one item per row into the existing fixed-K selection.

        The learned CBEM decision is completed first.  This method then applies
        an explicitly audited causal intervention without changing K: an
        already-selected target is left untouched, the first inactive slot is
        activated when available, otherwise the last (lowest-ranked) active
        slot is replaced.  The caller must retain both the original selection
        and the returned audit tensors.
        """

        selected_indices = selection.selected_indices
        selected_mask = selection.selected_mask
        if (
            selected_indices.ndim != 2
            or selected_mask.shape != selected_indices.shape
        ):
            raise ValueError("CBEM selected indices/mask must be aligned [B,K]")
        if item_count <= 0:
            raise ValueError("Forced memory intervention requires item_count > 0")
        forced = forced_indices.to(
            device=selected_indices.device,
            dtype=selected_indices.dtype,
        )
        if forced.ndim == 2 and forced.shape[1] == 1:
            forced = forced[:, 0]
        if (
            forced.ndim != 1
            or forced.shape[0] != selected_indices.shape[0]
        ):
            raise ValueError(
                "forced_indices must contain exactly one index per batch row"
            )
        if bool(((forced < 0) | (forced >= item_count)).any().item()):
            raise ValueError(
                f"Forced memory index is outside [0,{item_count})"
            )

        post_indices = selected_indices.clone()
        post_mask = selected_mask.clone()
        post_scores = selection.selected_scores.clone()
        already_selected = (
            post_mask & post_indices.eq(forced[:, None])
        ).any(dim=1)
        forced_slots = torch.full_like(forced, -1)
        displaced_indices = torch.full_like(forced, -1)
        inserted = ~already_selected

        for row in range(post_indices.shape[0]):
            if bool(already_selected[row].item()):
                continue
            inactive = (~post_mask[row]).nonzero(as_tuple=False).flatten()
            if inactive.numel() > 0:
                slot = int(inactive[0].item())
            else:
                active = post_mask[row].nonzero(as_tuple=False).flatten()
                if active.numel() == 0:
                    raise RuntimeError("Fixed-K CBEM selection has no writable slot")
                slot = int(active[-1].item())
                displaced_indices[row] = post_indices[row, slot]
            forced_slots[row] = slot
            post_indices[row, slot] = forced[row]
            post_mask[row, slot] = True
            # This slot is intervention-selected, not router-scored.  A finite
            # placeholder keeps JSON metrics valid; the audit below is the
            # authoritative score provenance.
            post_scores[row, slot] = 0.0

        post = replace(
            selection,
            selected_indices=post_indices,
            selected_mask=post_mask,
            selected_scores=post_scores,
            use_memory=post_mask.any(dim=1),
        )
        return post, {
            "forced_indices": forced,
            "target_was_selected": already_selected,
            "inserted": inserted,
            "forced_slots": forced_slots,
            "displaced_indices": displaced_indices,
        }

    @staticmethod
    def _base_model_identity(value: Any) -> str:
        return canonical_identity(value)

    @staticmethod
    def write_deployment_manifest(
        checkpoint_dir: str | Path,
        *,
        training_manifest: str | Path,
        final_gate: dict[str, Any],
        deployment_eligible: bool,
    ) -> dict[str, Any]:
        checkpoint = Path(checkpoint_dir)
        training = Path(training_manifest)
        training_validation = load_and_validate_training_manifest(
            checkpoint_dir=checkpoint,
            training_manifest=training,
        )
        training_document = training_validation["manifest"]
        if not isinstance(final_gate, dict) or not isinstance(
            final_gate.get("passed"), bool
        ):
            raise ValueError("final_gate must contain a boolean passed field")
        if not isinstance(deployment_eligible, bool):
            raise ValueError("deployment_eligible must be boolean")
        if final_gate != training_document["final_gate"]:
            raise ValueError(
                "Certificate final_gate must exactly match training final_gate"
            )
        if (
            deployment_eligible != training_document["deployment_eligible"]
            or deployment_eligible != final_gate["passed"]
        ):
            raise ValueError(
                "Certificate eligibility must match training and final_gate"
            )
        artifact_manifest = checkpoint / "artifact_manifest.json"
        document = {
            "schema_version": DEPLOYMENT_MANIFEST_SCHEMA,
            "status": "complete",
            "deployment_eligible": deployment_eligible,
            "final_gate": final_gate,
            "artifact_manifest": file_provenance(
                artifact_manifest, role="router_artifact_manifest"
            ),
            "training_manifest": file_provenance(
                training, role="router_training_manifest"
            ),
        }
        write_json_atomic_exclusive(
            checkpoint / "deployment_manifest.json", document
        )
        return document

    @staticmethod
    def _deployment_disclosure(
        checkpoint: Path,
        *,
        allow_non_deployable: bool,
    ) -> dict[str, Any]:
        deployment_path = checkpoint / "deployment_manifest.json"
        if not deployment_path.is_file():
            if not allow_non_deployable:
                raise ValueError(
                    "Deployable CBEM checkpoint requires deployment_manifest.json"
                )
            return {
                "deployment_eligible": False,
                "final_gate_passed": False,
                "override_used": True,
                "override_reason": "deployment_manifest_missing",
                "deployment_manifest": None,
            }
        validation = validate_deployment_contract(
            checkpoint,
            deployment_manifest=deployment_path,
            require_eligible=not allow_non_deployable,
        )
        eligible = validation["deployment_eligible"]
        return {
            "deployment_eligible": eligible,
            "final_gate_passed": bool(validation["final_gate"]["passed"]),
            "override_used": bool(allow_non_deployable and not eligible),
            "override_reason": (
                "explicit_offline_or_bootstrap_override"
                if allow_non_deployable and not eligible
                else None
            ),
            "deployment_manifest": validation["deployment_provenance"],
            "training_manifest": validation["training_manifest_provenance"],
            "artifact_manifest": validation["artifact_manifest_provenance"],
        }

    @staticmethod
    def _source_adapter_identity(path: str | Path) -> dict[str, Any]:
        source = Path(path)
        weights = source / "memory_adapter.safetensors"
        config = source / "memory_config.json"
        return {
            "path": str(source.absolute()),
            "weights": file_provenance(weights, role="adapter_weights"),
            "config": file_provenance(config, role="adapter_config"),
        }

    def save_pretrained(
        self,
        output_dir: str | Path,
        *,
        source_adapter: str | Path,
        base_model_identity: Any,
    ) -> None:
        output_dir = exclusive_output_dir(output_dir)
        self.config.save_json(output_dir / self.CONFIG_NAME)
        state = {
            name: tensor.detach().contiguous().cpu()
            for name, tensor in self.state_dict().items()
        }
        save_file(
            state,
            str(output_dir / self.WEIGHTS_NAME),
            metadata={
                "format": "awarevln-cbem-router",
                "schema_version": self.config.schema_version,
            },
        )
        manifest = {
            "schema_version": "cbem.checkpoint-manifest.v2",
            "status": "complete",
            "source_adapter": self._source_adapter_identity(
                source_adapter
            ),
            "base_model_identity": self._base_model_identity(
                base_model_identity
            ),
            "artifacts": {
                "config": file_provenance(
                    output_dir / self.CONFIG_NAME,
                    role="cbem_config",
                ),
                "weights": file_provenance(
                    output_dir / self.WEIGHTS_NAME,
                    role="cbem_weights",
                ),
            },
        }
        write_json_atomic_exclusive(
            output_dir / "artifact_manifest.json",
            manifest,
        )

    @classmethod
    def from_pretrained(
        cls,
        path: str | Path,
        *,
        expected_source_adapter: str | Path,
        expected_base_model_identity: Any,
        map_location: str | torch.device = "cpu",
        allow_non_deployable: bool = False,
    ) -> "CBEMRouter":
        path = Path(path)
        deployment_disclosure = cls._deployment_disclosure(
            path, allow_non_deployable=allow_non_deployable
        )
        manifest_path = path / "artifact_manifest.json"
        with manifest_path.open("r", encoding="utf-8") as stream:
            manifest = json.load(stream)
        if not isinstance(manifest, dict) or manifest.get("status") != "complete":
            raise ValueError(
                f"Incomplete CBEM checkpoint manifest: {manifest_path}"
            )
        expected_base = cls._base_model_identity(
            expected_base_model_identity
        )
        recorded_base = manifest.get("base_model_identity")
        if recorded_base != expected_base:
            raise ValueError(
                "CBEM checkpoint/base model identity mismatch: "
                f"{recorded_base!r} != {expected_base!r}"
            )
        actual_adapter = cls._source_adapter_identity(
            expected_source_adapter
        )
        recorded_adapter = manifest.get("source_adapter", {})
        for key in ("weights", "config"):
            recorded_hash = recorded_adapter.get(key, {}).get("sha256")
            actual_hash = actual_adapter[key]["sha256"]
            if recorded_hash != actual_hash:
                raise ValueError(
                    f"CBEM source-adapter {key} hash mismatch: "
                    f"{recorded_hash!r} != {actual_hash!r}"
                )
        for key, filename in (
            ("config", cls.CONFIG_NAME),
            ("weights", cls.WEIGHTS_NAME),
        ):
            recorded_hash = manifest.get("artifacts", {}).get(
                key, {}
            ).get("sha256")
            actual_hash = file_provenance(path / filename)["sha256"]
            if recorded_hash != actual_hash:
                raise ValueError(
                    f"CBEM {key} artifact hash mismatch: "
                    f"{recorded_hash!r} != {actual_hash!r}"
                )
        config = CBEMConfig.from_json(path / cls.CONFIG_NAME)
        router = cls(config)
        state = load_file(
            str(path / cls.WEIGHTS_NAME), device=str(map_location)
        )
        router.load_state_dict(state, strict=True)
        router.deployment_disclosure = deployment_disclosure
        return router
