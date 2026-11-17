"""Historical inference methods; baseline forward and model loading remain in LLaVA."""
import os
from pathlib import Path
from typing import Any,Optional,Union
import torch
from transformers.generation.logits_process import LogitsProcessorList
from awarevln_memory.config import MemoryAdapterConfig
from awarevln_memory.cbem.router import CBEMRouter,CBEMSelection
from awarevln_memory.memory.adapter import AwareVLNMemoryAdapter,MemoryAdapterOutput,MemoryGenerationOutput

class _ForceFirstGeneratedToken:
    """Force one token per batch row on the first decoding step only."""

    def __init__(self, token_ids: torch.LongTensor) -> None:
        self.token_ids = token_ids.detach()
        self.pending = True

    def __call__(
        self,
        input_ids: torch.LongTensor,
        scores: torch.FloatTensor,
    ) -> torch.FloatTensor:
        del input_ids
        if not self.pending:
            return scores
        forced = self.token_ids.to(device=scores.device)
        if scores.shape[0] != forced.numel():
            if scores.shape[0] % forced.numel() != 0:
                raise RuntimeError(
                    "Cannot broadcast mode-lock tokens over generation rows: "
                    f"{forced.numel()} -> {scores.shape[0]}"
                )
            forced = forced.repeat_interleave(
                scores.shape[0] // forced.numel()
            )
        locked = torch.full_like(scores, torch.finfo(scores.dtype).min)
        locked.scatter_(1, forced[:, None], 0.0)
        self.pending = False
        return locked


class HAMLETMemoryMixin:
    def init_memory_adapter(
        self,
        checkpoint: Optional[Union[str, os.PathLike]] = None,
        *,
        config: Optional[Union[MemoryAdapterConfig, dict[str, Any]]] = None,
    ) -> AwareVLNMemoryAdapter:
        """Attach a separately saved memory adapter to the frozen AwareVLN."""

        if checkpoint is not None:
            adapter = AwareVLNMemoryAdapter.from_pretrained(checkpoint)
            expected = int(self.get_llm().config.hidden_size)
            if adapter.config.llm_hidden_size != expected:
                raise ValueError(
                    "Memory adapter/base hidden-size mismatch: "
                    f"{adapter.config.llm_hidden_size} != {expected}"
                )
        else:
            if config is None:
                config = MemoryAdapterConfig(
                    llm_hidden_size=int(self.get_llm().config.hidden_size)
                )
            elif isinstance(config, dict):
                config = MemoryAdapterConfig.from_dict(config)
            adapter = AwareVLNMemoryAdapter(config)

        device = next(self.get_llm().parameters()).device
        adapter.to(device=device, dtype=torch.float32)
        self.memory_adapter = adapter
        return adapter

    def init_cbem_router(
        self,
        checkpoint: Union[str, os.PathLike],
        *,
        source_adapter_checkpoint: Union[str, os.PathLike],
        base_model_identity: str,
    ) -> CBEMRouter:
        """Attach a provenance-bound CBEM sidecar to a frozen adapter."""

        if self.memory_adapter is None:
            raise RuntimeError(
                "Initialize the source memory adapter before CBEM"
            )
        router = CBEMRouter.from_pretrained(
            checkpoint,
            expected_source_adapter=source_adapter_checkpoint,
            expected_base_model_identity=base_model_identity,
        )
        expected = int(self.memory_adapter.config.memory_hidden_size)
        if router.config.adapter_hidden_size != expected:
            raise ValueError(
                "CBEM/source-adapter hidden-size mismatch: "
                f"{router.config.adapter_hidden_size} != {expected}"
            )
        device = next(self.memory_adapter.parameters()).device
        router.to(device=device, dtype=torch.float32)
        router.eval()
        self.cbem_router = router
        return router

    @staticmethod
    def _select_last_context_tokens(
        hidden_states: torch.Tensor,
        attention_mask: Optional[torch.Tensor],
        moment_tokens: int,
    ) -> torch.Tensor:
        selected = []
        for batch_index in range(hidden_states.shape[0]):
            if attention_mask is None:
                indices = torch.arange(
                    hidden_states.shape[1],
                    device=hidden_states.device,
                )
            else:
                indices = torch.where(attention_mask[batch_index].bool())[0]
            if indices.numel() == 0:
                raise RuntimeError("Cannot extract a moment from an empty prompt")
            values = hidden_states[batch_index, indices[-moment_tokens:]]
            if values.shape[0] < moment_tokens:
                pad = values[:1].expand(moment_tokens - values.shape[0], -1)
                values = torch.cat([pad, values], dim=0)
            selected.append(values)
        return torch.stack(selected, dim=0)

    def _base_reason_act_token_ids(
        self,
        inputs_embeds: torch.Tensor,
        attention_mask: Optional[torch.Tensor],
    ) -> torch.LongTensor:
        """Choose the frozen base model's REASON/ACT token for each row."""

        reason_token_id = getattr(
            self.config,
            "reason_token_id",
            getattr(self, "reason_token_id", None),
        )
        act_token_id = getattr(
            self.config,
            "act_token_id",
            getattr(self, "act_token_id", None),
        )
        if reason_token_id is None or act_token_id is None:
            raise RuntimeError(
                "Mode lock requires reason_token_id and act_token_id"
            )

        backbone = getattr(self.llm, "model", None)
        if backbone is None:
            backbone = getattr(self.llm, "transformer", None)
        if backbone is None:
            raise RuntimeError(
                "Mode lock cannot locate the causal-LM backbone"
            )
        output = backbone(
            input_ids=None,
            inputs_embeds=inputs_embeds,
            attention_mask=attention_mask,
            use_cache=False,
            return_dict=True,
        )
        hidden_states = getattr(output, "last_hidden_state", None)
        if hidden_states is None:
            hidden_states = output[0]
        last_hidden = self._select_last_context_tokens(
            hidden_states,
            attention_mask,
            1,
        ).squeeze(1)

        lm_head = self.get_lm_head()
        candidate_ids = torch.tensor(
            [int(reason_token_id), int(act_token_id)],
            dtype=torch.long,
            device=lm_head.weight.device,
        )
        candidate_weight = lm_head.weight.index_select(0, candidate_ids)
        mode_logits = torch.nn.functional.linear(
            last_hidden.to(dtype=candidate_weight.dtype),
            candidate_weight,
        )
        if getattr(lm_head, "bias", None) is not None:
            mode_logits = mode_logits + lm_head.bias.index_select(
                0,
                candidate_ids,
            )
        return candidate_ids[mode_logits.argmax(dim=-1)]

    @torch.inference_mode()
    def generate_with_memory(
        self,
        input_ids: Optional[torch.LongTensor] = None,
        images: Optional[torch.FloatTensor] = None,
        attention_mask: Optional[torch.LongTensor] = None,
        *,
        memory_moments: Optional[torch.Tensor] = None,
        memory_mask: Optional[torch.Tensor] = None,
        memory_types: Optional[torch.Tensor] = None,
        memory_ages: Optional[torch.Tensor] = None,
        memory_enabled: bool = True,
        memory_read_threshold: float = 0.0,
        memory_alpha_scale: float = 1.0,
        preserve_base_mode: bool = False,
        forced_memory_indices: Optional[torch.LongTensor] = None,
        **generation_kwargs: Any,
    ) -> MemoryGenerationOutput:
        """Generate normally while capturing one contextual moment.

        A pre-hook on the LM head captures only the first (prompt-prefill)
        hidden state, avoiding the large memory cost of
        ``output_hidden_states=True`` during autoregressive generation.
        """

        if images is not None:
            (
                _,
                _,
                attention_mask,
                _,
                inputs_embeds,
                _,
            ) = self.prepare_inputs_labels_for_multimodal(
                input_ids,
                None,
                attention_mask,
                None,
                None,
                images,
            )
        else:
            inputs_embeds = self.get_input_embeddings()(input_ids)
        inputs_embeds = inputs_embeds.to(self.dtype)

        base_inputs_embeds = inputs_embeds
        adapter_output = None
        cbem_selection: Optional[CBEMSelection] = None
        cbem_selection_pre_intervention: Optional[CBEMSelection] = None
        memory_intervention: Optional[dict[str, Any]] = None
        cbem_router = getattr(self, "cbem_router", None)
        if forced_memory_indices is not None and cbem_router is None:
            raise RuntimeError(
                "Forced memory intervention requires a completed CBEM selection"
            )
        if cbem_router is not None:
            if self.memory_adapter is None:
                raise RuntimeError(
                    "CBEM cannot run without its source memory adapter"
                )
            if memory_read_threshold != 0.0:
                raise ValueError(
                    "AWAREVLN_MEMORY_READ_THRESHOLD must be exactly 0 when "
                    "CBEM is active; NONE is the sole abstention decision"
                )
            if not memory_enabled:
                memory_moments = None
                memory_mask = None
                memory_types = None
                memory_ages = None
            elif memory_moments is not None and memory_moments.shape[1] > 0:
                current_query = self.memory_adapter.query_encoder(
                    inputs_embeds,
                    attention_mask,
                )
                memory_items = self.memory_adapter.reader._collapse_moments(
                    memory_moments
                )
                cbem_selection = cbem_router(
                    current_query=current_query,
                    memory_items=memory_items,
                    memory_mask=memory_mask,
                    memory_types=memory_types,
                    memory_ages=memory_ages,
                )
                if forced_memory_indices is not None:
                    cbem_selection_pre_intervention = cbem_selection
                    cbem_selection, memory_intervention = (
                        cbem_router.force_include_indices(
                            cbem_selection,
                            forced_memory_indices,
                            item_count=int(memory_moments.shape[1]),
                        )
                    )
                memory_moments = cbem_router.select_tensor(
                    memory_moments,
                    cbem_selection,
                )
                memory_types = cbem_router.select_tensor(
                    memory_types,
                    cbem_selection,
                )
                memory_ages = cbem_router.select_tensor(
                    memory_ages,
                    cbem_selection,
                )
                memory_mask = cbem_selection.selected_mask
            elif forced_memory_indices is not None:
                raise RuntimeError(
                    "Forced memory intervention requires non-empty memory"
                )

        if self.memory_adapter is not None:
            adapter_output = self.memory_adapter(
                inputs_embeds,
                attention_mask=attention_mask,
                memory_moments=memory_moments,
                memory_mask=memory_mask,
                memory_types=memory_types,
                memory_ages=memory_ages,
                enabled=memory_enabled,
                read_threshold=memory_read_threshold,
                alpha_scale=memory_alpha_scale,
            )
            inputs_embeds = adapter_output.adapted_inputs

        base_mode_token_ids = None
        mode_lock_applied = False
        prompt_is_changed = (
            adapter_output is not None
            and memory_enabled
            and bool(
                adapter_output.effective_read_probability.gt(0).any().item()
            )
            and bool(adapter_output.effective_alpha.detach().abs().gt(0).item())
        )
        if preserve_base_mode and prompt_is_changed:
            base_mode_token_ids = self._base_reason_act_token_ids(
                base_inputs_embeds,
                attention_mask,
            )
            processors = generation_kwargs.pop("logits_processor", None)
            if processors is None:
                processors = LogitsProcessorList()
            else:
                processors = LogitsProcessorList(list(processors))
            processors.append(
                _ForceFirstGeneratedToken(base_mode_token_ids)
            )
            generation_kwargs["logits_processor"] = processors
            mode_lock_applied = True

        captured: list[torch.Tensor] = []
        moment_count = (
            self.memory_adapter.config.moment_tokens
            if self.memory_adapter is not None
            else 4
        )

        def capture_prompt_hidden(
            module: torch.nn.Module,
            inputs: tuple[torch.Tensor, ...],
        ) -> None:
            del module
            hidden = inputs[0]
            if captured or hidden.ndim != 3:
                return
            # The first LM-head call is the full prompt prefill.  A later
            # single-token call must never overwrite it.
            if hidden.shape[1] == 1 and inputs_embeds.shape[1] > 1:
                return
            captured.append(
                self._select_last_context_tokens(
                    hidden,
                    attention_mask,
                    moment_count,
                ).detach()
            )

        with self.get_lm_head().register_forward_pre_hook(
            capture_prompt_hidden
        ):
            sequences = self.llm.generate(
                inputs_embeds=inputs_embeds,
                attention_mask=attention_mask,
                **generation_kwargs,
            )
        if not captured:
            raise RuntimeError("LM-head hook did not capture prompt hidden states")
        return MemoryGenerationOutput(
            sequences=sequences,
            moment_tokens=captured[0],
            adapter_output=adapter_output,
            cbem_selection=cbem_selection,
            cbem_selection_pre_intervention=(
                cbem_selection_pre_intervention
            ),
            memory_intervention=memory_intervention,
            base_mode_token_ids=base_mode_token_ids,
            mode_lock_applied=mode_lock_applied,
        )

