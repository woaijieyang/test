from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import torch
from safetensors.torch import load_file, save_file
from torch import Tensor, nn

from awarevln_memory.config import MemoryAdapterConfig


@dataclass
class MemoryAdapterOutput:
    """Auditable outputs produced for one memory-conditioned policy call."""

    adapted_inputs: Tensor
    current_query: Tensor
    memory_tokens: Tensor
    read_probability: Tensor
    effective_read_probability: Tensor
    write_probability: Tensor
    alpha: Tensor
    effective_alpha: Tensor
    valid_memory_items: Tensor

    def detached_metrics(self) -> dict[str, object]:
        def scalar_or_list(value: Tensor) -> object:
            value = value.detach().float().cpu()
            if value.numel() == 1:
                return float(value.item())
            return value.tolist()

        return {
            "read_probability": scalar_or_list(self.read_probability),
            "effective_read_probability": scalar_or_list(
                self.effective_read_probability
            ),
            "write_probability": scalar_or_list(self.write_probability),
            "alpha": scalar_or_list(self.alpha),
            "effective_alpha": scalar_or_list(self.effective_alpha),
            "valid_memory_items": scalar_or_list(self.valid_memory_items),
        }


@dataclass
class MemoryGenerationOutput:
    sequences: Tensor
    moment_tokens: Tensor
    adapter_output: Optional[MemoryAdapterOutput] = None
    cbem_selection: Optional[Any] = None
    cbem_selection_pre_intervention: Optional[Any] = None
    memory_intervention: Optional[dict[str, Any]] = None
    base_mode_token_ids: Optional[Tensor] = None
    mode_lock_applied: bool = False


class MomentQueryEncoder(nn.Module):
    """Read the current multimodal prompt with a few learned queries."""

    def __init__(self, config: MemoryAdapterConfig) -> None:
        super().__init__()
        dim = config.memory_hidden_size
        self.queries = nn.Parameter(torch.empty(config.moment_tokens, dim))
        self.key_value = nn.Linear(config.llm_hidden_size, dim, bias=False)
        self.attention = nn.MultiheadAttention(
            dim,
            config.memory_heads,
            dropout=config.dropout,
            batch_first=True,
        )
        self.norm1 = nn.LayerNorm(dim)
        self.ffn = nn.Sequential(
            nn.Linear(dim, dim * 2),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(dim * 2, dim),
        )
        self.norm2 = nn.LayerNorm(dim)
        nn.init.normal_(self.queries, mean=0.0, std=0.02)

    def forward(
        self,
        prompt_embeddings: Tensor,
        attention_mask: Optional[Tensor],
    ) -> Tensor:
        projected = self.key_value(prompt_embeddings.float())
        queries = self.queries.unsqueeze(0).expand(projected.shape[0], -1, -1)
        key_padding_mask = None
        if attention_mask is not None:
            key_padding_mask = ~attention_mask.bool()
        attended, _ = self.attention(
            queries,
            projected,
            projected,
            key_padding_mask=key_padding_mask,
            need_weights=False,
        )
        hidden = self.norm1(queries + attended)
        return self.norm2(hidden + self.ffn(hidden))


class MemoryReader(nn.Module):
    """Aggregate recent moments and sparse events for the current query."""

    def __init__(self, config: MemoryAdapterConfig) -> None:
        super().__init__()
        dim = config.memory_hidden_size
        self.config = config
        self.moment_down = nn.Linear(config.llm_hidden_size, dim, bias=False)
        self.moment_slot_embedding = nn.Parameter(
            torch.empty(config.moment_tokens, dim)
        )
        self.type_embedding = nn.Embedding(3, dim)
        self.age_embedding = nn.Embedding(config.max_age + 1, dim)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=dim,
            nhead=config.memory_heads,
            dim_feedforward=dim * 4,
            dropout=config.dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(
            encoder_layer,
            num_layers=config.memory_layers,
            enable_nested_tensor=False,
        )
        self.cross_attention = nn.MultiheadAttention(
            dim,
            config.memory_heads,
            dropout=config.dropout,
            batch_first=True,
        )
        self.output_norm = nn.LayerNorm(dim)
        self.read_gate = nn.Sequential(
            nn.Linear(dim * 2, dim),
            nn.GELU(),
            nn.Linear(dim, 1),
        )
        self.write_gate = nn.Sequential(
            nn.Linear(dim, dim // 2),
            nn.GELU(),
            nn.Linear(dim // 2, 1),
        )
        nn.init.normal_(self.moment_slot_embedding, mean=0.0, std=0.02)

    def _collapse_moments(self, memory_moments: Tensor) -> Tensor:
        if memory_moments.ndim == 3:
            memory_moments = memory_moments.unsqueeze(2)
        if memory_moments.ndim != 4:
            raise ValueError(
                "memory_moments must have shape [B,N,H] or [B,N,Q,H], "
                f"got {tuple(memory_moments.shape)}"
            )
        if memory_moments.shape[-1] != self.config.llm_hidden_size:
            raise ValueError(
                "Unexpected raw moment hidden size: "
                f"{memory_moments.shape[-1]} != {self.config.llm_hidden_size}"
            )

        projected = self.moment_down(memory_moments.float())
        slots = self.moment_slot_embedding
        if projected.shape[2] != slots.shape[0]:
            slots = torch.nn.functional.interpolate(
                slots.T.unsqueeze(0),
                size=projected.shape[2],
                mode="linear",
                align_corners=False,
            ).squeeze(0).T
        projected = projected + slots[None, None, :, :]
        return projected.mean(dim=2)

    def forward(
        self,
        current_query: Tensor,
        memory_moments: Optional[Tensor],
        memory_mask: Optional[Tensor],
        memory_types: Optional[Tensor],
        memory_ages: Optional[Tensor],
    ) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        batch_size = current_query.shape[0]
        write_probability = torch.sigmoid(
            self.write_gate(current_query.mean(dim=1))
        ).squeeze(-1)

        if memory_moments is None or memory_moments.shape[1] == 0:
            zeros = current_query.new_zeros(current_query.shape)
            return (
                zeros,
                current_query.new_zeros(batch_size),
                write_probability,
                current_query.new_zeros(batch_size),
            )

        memory_items = self._collapse_moments(memory_moments)
        item_count = memory_items.shape[1]
        if memory_mask is None:
            memory_mask = torch.ones(
                batch_size,
                item_count,
                dtype=torch.bool,
                device=memory_items.device,
            )
        else:
            memory_mask = memory_mask.to(memory_items.device).bool()
        if memory_types is None:
            memory_types = torch.zeros_like(memory_mask, dtype=torch.long)
        if memory_ages is None:
            memory_ages = torch.zeros_like(memory_mask, dtype=torch.long)
        memory_types = memory_types.to(memory_items.device).long().clamp(0, 2)
        memory_ages = (
            memory_ages.to(memory_items.device)
            .long()
            .clamp(0, self.config.max_age)
        )

        memory_items = (
            memory_items
            + self.type_embedding(memory_types)
            + self.age_embedding(memory_ages)
        )
        valid_counts = memory_mask.sum(dim=1)

        # Transformer attention cannot consume a row whose every item is
        # masked.  Temporarily unmask a zero item and force its output gate to
        # zero afterwards.
        safe_mask = memory_mask.clone()
        empty_rows = valid_counts == 0
        if empty_rows.any():
            safe_mask[empty_rows, 0] = True
            memory_items = memory_items.clone()
            memory_items[empty_rows, 0] = 0

        encoded = self.encoder(
            memory_items,
            src_key_padding_mask=~safe_mask,
        )
        attended, _ = self.cross_attention(
            current_query,
            encoded,
            encoded,
            key_padding_mask=~safe_mask,
            need_weights=False,
        )
        attended = self.output_norm(current_query + attended)
        pooled_query = current_query.mean(dim=1)
        pooled_memory = attended.mean(dim=1)
        read_probability = torch.sigmoid(
            self.read_gate(torch.cat([pooled_query, pooled_memory], dim=-1))
        ).squeeze(-1)
        read_probability = torch.where(
            empty_rows,
            torch.zeros_like(read_probability),
            read_probability,
        )
        attended = attended * read_probability[:, None, None]
        return attended, read_probability, write_probability, valid_counts


class GatedPromptInjection(nn.Module):
    """Inject memory into existing prompt positions with an exact zero gate."""

    def __init__(self, config: MemoryAdapterConfig) -> None:
        super().__init__()
        self.config = config
        self.up = nn.Linear(
            config.memory_hidden_size,
            config.llm_hidden_size,
            bias=False,
        )
        self.alpha = nn.Parameter(torch.tensor(float(config.alpha_init)))

    def _prompt_indices(
        self,
        attention_mask: Optional[Tensor],
        labels: Optional[Tensor],
        sequence_length: int,
        batch_index: int,
        device: torch.device,
    ) -> Tensor:
        valid = torch.ones(sequence_length, dtype=torch.bool, device=device)
        if attention_mask is not None:
            valid &= attention_mask[batch_index].bool()
        if labels is not None:
            # Training sequences include assistant target tokens.  Memory is
            # injected only into the last masked prompt positions.
            valid &= labels[batch_index].eq(-100)
        indices = torch.where(valid)[0]
        count = min(self.config.output_memory_tokens, indices.numel())
        return indices[-count:]

    def forward(
        self,
        inputs_embeds: Tensor,
        memory_tokens: Tensor,
        attention_mask: Optional[Tensor],
        labels: Optional[Tensor] = None,
        enabled: bool = True,
        alpha_scale: float = 1.0,
    ) -> Tensor:
        if not enabled:
            return inputs_embeds
        projected = self.up(memory_tokens.float())
        projected = projected.to(dtype=inputs_embeds.dtype)
        alpha = self.alpha.to(dtype=inputs_embeds.dtype) * float(alpha_scale)
        delta = torch.zeros_like(inputs_embeds)
        for batch_index in range(inputs_embeds.shape[0]):
            indices = self._prompt_indices(
                attention_mask,
                labels,
                inputs_embeds.shape[1],
                batch_index,
                inputs_embeds.device,
            )
            if indices.numel() == 0:
                continue
            selected = projected[batch_index, -indices.numel() :]
            delta[batch_index, indices] = selected * alpha
        return inputs_embeds + delta


class AwareVLNMemoryAdapter(nn.Module):
    """Minimal-intrusion HAMLET-style episode memory for AwareVLN."""

    CONFIG_NAME = "memory_config.json"
    WEIGHTS_NAME = "memory_adapter.safetensors"

    def __init__(self, config: MemoryAdapterConfig) -> None:
        super().__init__()
        self.config = config
        self.query_encoder = MomentQueryEncoder(config)
        self.reader = MemoryReader(config)
        self.injection = GatedPromptInjection(config)

    @property
    def alpha(self) -> Tensor:
        return self.injection.alpha

    def forward(
        self,
        inputs_embeds: Tensor,
        attention_mask: Optional[Tensor] = None,
        labels: Optional[Tensor] = None,
        memory_moments: Optional[Tensor] = None,
        memory_mask: Optional[Tensor] = None,
        memory_types: Optional[Tensor] = None,
        memory_ages: Optional[Tensor] = None,
        enabled: bool = True,
        read_threshold: float = 0.0,
        alpha_scale: float = 1.0,
    ) -> MemoryAdapterOutput:
        if not 0.0 <= read_threshold <= 1.0:
            raise ValueError("read_threshold must be in [0, 1]")
        if alpha_scale < 0.0:
            raise ValueError("alpha_scale must be non-negative")
        current_query = self.query_encoder(inputs_embeds, attention_mask)
        (
            memory_tokens,
            read_probability,
            write_probability,
            valid_memory_items,
        ) = self.reader(
            current_query,
            memory_moments,
            memory_mask,
            memory_types,
            memory_ages,
        )
        if read_threshold > 0.0:
            read_enabled = read_probability.ge(float(read_threshold))
            memory_tokens = memory_tokens * read_enabled[:, None, None]
            effective_read_probability = torch.where(
                read_enabled,
                read_probability,
                torch.zeros_like(read_probability),
            )
        else:
            effective_read_probability = read_probability
        adapted_inputs = self.injection(
            inputs_embeds,
            memory_tokens,
            attention_mask,
            labels=labels,
            enabled=enabled,
            alpha_scale=alpha_scale,
        )
        return MemoryAdapterOutput(
            adapted_inputs=adapted_inputs,
            current_query=current_query,
            memory_tokens=memory_tokens,
            read_probability=read_probability,
            effective_read_probability=effective_read_probability,
            write_probability=write_probability,
            alpha=self.alpha,
            effective_alpha=self.alpha * float(alpha_scale),
            valid_memory_items=valid_memory_items,
        )

    def score_write(self, raw_moment: Tensor) -> Tensor:
        """Score contextual moments without requiring the original prompt."""
        if raw_moment.ndim == 2:
            raw_moment = raw_moment.unsqueeze(0)
        projected = self.reader.moment_down(raw_moment.float()).mean(dim=1)
        return torch.sigmoid(self.reader.write_gate(projected)).squeeze(-1)

    def save_pretrained(self, output_dir: str | Path) -> None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self.config.save_json(output_dir / self.CONFIG_NAME)
        state = {
            name: tensor.detach().contiguous().cpu()
            for name, tensor in self.state_dict().items()
        }
        save_file(
            state,
            str(output_dir / self.WEIGHTS_NAME),
            metadata={"format": "awarevln-memory", "schema_version": "0.1"},
        )

    @classmethod
    def from_pretrained(
        cls,
        path: str | Path,
        *,
        map_location: str | torch.device = "cpu",
    ) -> "AwareVLNMemoryAdapter":
        path = Path(path)
        config = MemoryAdapterConfig.from_json(path / cls.CONFIG_NAME)
        model = cls(config)
        state = load_file(str(path / cls.WEIGHTS_NAME), device=str(map_location))
        model.load_state_dict(state, strict=True)
        return model

    def extra_repr(self) -> str:
        return json.dumps(self.config.to_dict(), sort_keys=True)
