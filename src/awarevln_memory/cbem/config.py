from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CBEMConfig:
    """Configuration of the counterfactual-benefit episode-memory router.

    CBEM is a sidecar: it ranks frozen AwareVLN memory items but never changes
    the source memory-adapter checkpoint.  ``prefilter_top_k`` is a compute
    budget, not a learned or hand-tuned read threshold; the explicit NONE
    candidate is the only abstention decision.
    """

    schema_version: str = "cbem.router.v1"
    adapter_hidden_size: int = 768
    rank: int = 128
    memory_types: int = 3
    max_age: int = 256
    prefilter_top_k: int = 12
    selected_top_k: int = 4
    archive_capacity: int = 256
    none_logit_init: float = 4.0
    target_supervision_margin: float = 0.1
    target_loss_weight: float = 1.0
    helpful_coarse_recall_min: float = 1.0

    def __post_init__(self) -> None:
        positive = {
            "adapter_hidden_size": self.adapter_hidden_size,
            "rank": self.rank,
            "memory_types": self.memory_types,
            "max_age": self.max_age,
            "prefilter_top_k": self.prefilter_top_k,
            "selected_top_k": self.selected_top_k,
            "archive_capacity": self.archive_capacity,
        }
        invalid = [name for name, value in positive.items() if value <= 0]
        if invalid:
            raise ValueError(f"CBEM config values must be positive: {invalid}")
        if self.selected_top_k > self.prefilter_top_k:
            raise ValueError(
                "selected_top_k must not exceed prefilter_top_k: "
                f"{self.selected_top_k} > {self.prefilter_top_k}"
            )
        if self.prefilter_top_k > self.archive_capacity:
            raise ValueError(
                "prefilter_top_k must not exceed archive_capacity: "
                f"{self.prefilter_top_k} > {self.archive_capacity}"
            )
        if self.target_supervision_margin < 0.0:
            raise ValueError("target_supervision_margin must be non-negative")
        if self.target_loss_weight < 0.0:
            raise ValueError("target_loss_weight must be non-negative")
        if not 0.0 <= self.helpful_coarse_recall_min <= 1.0:
            raise ValueError(
                "helpful_coarse_recall_min must be in [0, 1]"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "CBEMConfig":
        known = cls.__dataclass_fields__
        unknown = sorted(set(values) - set(known))
        if unknown:
            raise ValueError(f"Unknown CBEM config fields: {unknown}")
        return cls(**values)

    @classmethod
    def from_json(cls, path: str | Path) -> "CBEMConfig":
        with Path(path).open("r", encoding="utf-8") as stream:
            return cls.from_dict(json.load(stream))

    def save_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            json.dump(self.to_dict(), stream, indent=2, sort_keys=True)
            stream.write("\n")
