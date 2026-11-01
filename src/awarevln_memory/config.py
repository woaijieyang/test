from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class MemoryAdapterConfig:
    """Configuration for the minimal AwareVLN memory adapter.

    Moment tensors stored by the rollout logger stay in the frozen LLM hidden
    dimension.  Projection into ``memory_hidden_size`` therefore remains
    trainable without invalidating canonical rollout assets.
    """

    schema_version: str = "0.1"
    llm_hidden_size: int = 4096
    memory_hidden_size: int = 768
    moment_tokens: int = 4
    memory_layers: int = 2
    memory_heads: int = 12
    recent_calls: int = 4
    max_event_items: int = 8
    output_memory_tokens: int = 4
    max_age: int = 256
    dropout: float = 0.0
    alpha_init: float = 0.0
    write_threshold: float = 0.5

    def __post_init__(self) -> None:
        positive = {
            "llm_hidden_size": self.llm_hidden_size,
            "memory_hidden_size": self.memory_hidden_size,
            "moment_tokens": self.moment_tokens,
            "memory_layers": self.memory_layers,
            "memory_heads": self.memory_heads,
            "recent_calls": self.recent_calls,
            "max_event_items": self.max_event_items,
            "output_memory_tokens": self.output_memory_tokens,
            "max_age": self.max_age,
        }
        invalid = [name for name, value in positive.items() if value <= 0]
        if invalid:
            raise ValueError(f"Memory config values must be positive: {invalid}")
        if self.memory_hidden_size % self.memory_heads:
            raise ValueError(
                "memory_hidden_size must be divisible by memory_heads: "
                f"{self.memory_hidden_size} % {self.memory_heads}"
            )
        if not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        if not 0.0 <= self.write_threshold <= 1.0:
            raise ValueError("write_threshold must be in [0, 1]")

    @property
    def max_memory_items(self) -> int:
        return self.recent_calls + self.max_event_items

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "MemoryAdapterConfig":
        known = cls.__dataclass_fields__
        return cls(**{key: value for key, value in values.items() if key in known})

    @classmethod
    def from_json(cls, path: str | Path) -> "MemoryAdapterConfig":
        with Path(path).open("r", encoding="utf-8") as stream:
            return cls.from_dict(json.load(stream))

    def save_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as stream:
            json.dump(self.to_dict(), stream, indent=2, sort_keys=True)
            stream.write("\n")
