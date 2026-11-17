from __future__ import annotations

from types import SimpleNamespace

import torch
from transformers import GPT2Config, GPT2LMHeadModel

from awarevln_memory.config import MemoryAdapterConfig
from awarevln_memory.memory.adapter import AwareVLNMemoryAdapter
from llava.model.language_model.llava_llama import AwareVLNModel


def tiny_config() -> MemoryAdapterConfig:
    return MemoryAdapterConfig(
        llm_hidden_size=32,
        memory_hidden_size=16,
        moment_tokens=4,
        memory_layers=1,
        memory_heads=4,
        recent_calls=2,
        max_event_items=2,
        output_memory_tokens=4,
        max_age=16,
        dropout=0.0,
        alpha_init=0.0,
    )


def test_zero_init_gate_exact_equivalence() -> None:
    torch.manual_seed(7)
    adapter = AwareVLNMemoryAdapter(tiny_config()).eval()
    inputs = torch.randn(2, 9, 32)
    memory = torch.randn(2, 3, 4, 32)
    mask = torch.tensor([[1, 1, 1], [1, 0, 0]], dtype=torch.bool)
    output = adapter(inputs, memory_moments=memory, memory_mask=mask)
    assert torch.equal(inputs, output.adapted_inputs)
    assert output.alpha.item() == 0.0


def test_memory_off_matches_base_after_gate_changes() -> None:
    torch.manual_seed(11)
    adapter = AwareVLNMemoryAdapter(tiny_config()).eval()
    adapter.injection.alpha.data.fill_(0.25)
    inputs = torch.randn(1, 8, 32)
    memory = torch.randn(1, 2, 4, 32)
    off = adapter(inputs, memory_moments=memory, enabled=False)
    on = adapter(inputs, memory_moments=memory, enabled=True)
    assert torch.equal(inputs, off.adapted_inputs)
    assert not torch.equal(inputs, on.adapted_inputs)


def test_empty_memory_forces_read_gate_closed() -> None:
    adapter = AwareVLNMemoryAdapter(tiny_config()).eval()
    inputs = torch.randn(3, 6, 32)
    output = adapter(inputs, memory_moments=None)
    assert torch.equal(output.read_probability, torch.zeros(3))
    assert torch.equal(output.valid_memory_items, torch.zeros(3))


def test_runtime_read_threshold_and_alpha_scale_can_close_injection() -> None:
    torch.manual_seed(17)
    adapter = AwareVLNMemoryAdapter(tiny_config()).eval()
    adapter.injection.alpha.data.fill_(0.25)
    inputs = torch.randn(1, 8, 32)
    memory = torch.randn(1, 2, 4, 32)

    threshold_closed = adapter(
        inputs,
        memory_moments=memory,
        read_threshold=1.0,
    )
    alpha_closed = adapter(
        inputs,
        memory_moments=memory,
        alpha_scale=0.0,
    )

    assert torch.equal(inputs, threshold_closed.adapted_inputs)
    assert torch.equal(
        threshold_closed.effective_read_probability,
        torch.zeros(1),
    )
    assert torch.equal(inputs, alpha_closed.adapted_inputs)
    assert alpha_closed.effective_alpha.item() == 0.0


def test_training_injects_only_masked_prompt_positions() -> None:
    torch.manual_seed(3)
    adapter = AwareVLNMemoryAdapter(tiny_config()).eval()
    adapter.injection.alpha.data.fill_(0.5)
    inputs = torch.randn(1, 10, 32)
    labels = torch.full((1, 10), -100)
    labels[:, 7:] = torch.tensor([[1, 2, 3]])
    output = adapter(
        inputs,
        labels=labels,
        memory_moments=torch.randn(1, 2, 4, 32),
    )
    changed = (output.adapted_inputs != inputs).any(dim=-1)[0]
    assert changed[:7].sum().item() == 4
    assert not changed[7:].any()


def test_adapter_save_load_roundtrip(tmp_path) -> None:
    torch.manual_seed(5)
    adapter = AwareVLNMemoryAdapter(tiny_config()).eval()
    adapter.injection.alpha.data.fill_(0.125)
    adapter.save_pretrained(tmp_path)
    loaded = AwareVLNMemoryAdapter.from_pretrained(tmp_path).eval()
    for name, value in adapter.state_dict().items():
        assert torch.equal(value.cpu(), loaded.state_dict()[name].cpu())


def test_generate_hook_captures_contextual_moment_and_preserves_zero_gate() -> None:
    class Harness:
        generate_with_memory = AwareVLNModel.generate_with_memory
        _select_last_context_tokens = staticmethod(
            AwareVLNModel._select_last_context_tokens
        )

        def __init__(self) -> None:
            self.llm = GPT2LMHeadModel(
                GPT2Config(
                    vocab_size=32,
                    n_embd=16,
                    n_inner=32,
                    n_layer=1,
                    n_head=2,
                    n_positions=32,
                    bos_token_id=1,
                    eos_token_id=2,
                    pad_token_id=0,
                )
            ).eval()
            config = MemoryAdapterConfig(
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
            )
            self.memory_adapter = AwareVLNMemoryAdapter(config).eval()

        @property
        def dtype(self) -> torch.dtype:
            return next(self.llm.parameters()).dtype

        def get_input_embeddings(self):
            return self.llm.get_input_embeddings()

        def get_lm_head(self):
            return self.llm.lm_head

    torch.manual_seed(13)
    harness = Harness()
    input_ids = torch.tensor([[1, 4, 5, 6, 7, 8]])
    attention_mask = torch.ones_like(input_ids)
    input_embeds = harness.get_input_embeddings()(input_ids)
    baseline = harness.llm.generate(
        inputs_embeds=input_embeds,
        attention_mask=attention_mask,
        do_sample=False,
        max_new_tokens=2,
        pad_token_id=0,
    )
    result = harness.generate_with_memory(
        input_ids,
        attention_mask=attention_mask,
        memory_moments=torch.randn(1, 2, 4, 16),
        do_sample=False,
        max_new_tokens=2,
        pad_token_id=0,
    )
    assert torch.equal(result.sequences, baseline)
    assert result.moment_tokens.shape == (1, 4, 16)


def test_generate_mode_lock_uses_base_reason_act_choice() -> None:
    class Harness:
        generate_with_memory = AwareVLNModel.generate_with_memory
        _base_reason_act_token_ids = (
            AwareVLNModel._base_reason_act_token_ids
        )
        _select_last_context_tokens = staticmethod(
            AwareVLNModel._select_last_context_tokens
        )

        def __init__(self) -> None:
            self.llm = GPT2LMHeadModel(
                GPT2Config(
                    vocab_size=32,
                    n_embd=16,
                    n_inner=32,
                    n_layer=1,
                    n_head=2,
                    n_positions=32,
                    bos_token_id=1,
                    eos_token_id=2,
                    pad_token_id=0,
                )
            ).eval()
            self.config = SimpleNamespace(
                reason_token_id=9,
                act_token_id=10,
            )
            adapter_config = MemoryAdapterConfig(
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
                alpha_init=0.2,
            )
            self.memory_adapter = AwareVLNMemoryAdapter(
                adapter_config
            ).eval()

        @property
        def dtype(self) -> torch.dtype:
            return next(self.llm.parameters()).dtype

        def get_input_embeddings(self):
            return self.llm.get_input_embeddings()

        def get_lm_head(self):
            return self.llm.lm_head

    torch.manual_seed(23)
    harness = Harness()
    input_ids = torch.tensor([[1, 4, 5, 6, 7, 8]])
    attention_mask = torch.ones_like(input_ids)
    input_embeds = harness.get_input_embeddings()(input_ids)
    expected = harness._base_reason_act_token_ids(
        input_embeds,
        attention_mask,
    )
    result = harness.generate_with_memory(
        input_ids,
        attention_mask=attention_mask,
        memory_moments=torch.randn(1, 2, 4, 16),
        preserve_base_mode=True,
        do_sample=False,
        max_new_tokens=1,
        pad_token_id=0,
    )

    assert result.mode_lock_applied
    assert torch.equal(result.base_mode_token_ids, expected)
    assert result.sequences[0, -1].item() == expected[0].item()


