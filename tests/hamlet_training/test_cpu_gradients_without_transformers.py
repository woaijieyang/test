"""Pure-PyTorch gradient parity smoke: no HF checkpoint or GPU required.

These tests complement (never replace) the real 8B/FP16 S05 validation.
"""
from types import SimpleNamespace

import torch
from torch import nn
from torch.nn import functional as F

from awarevln_memory.training.models import MemoryModules, ShortMemoryConfig, StageModel


class _CausalEncoder(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, inputs_embeds, attention_mask=None, **kwargs):
        if attention_mask is None:
            mask = torch.ones(inputs_embeds.shape[:2], dtype=torch.bool, device=inputs_embeds.device)
        else:
            mask = attention_mask.bool()
        masked = inputs_embeds * mask.unsqueeze(-1)
        # Deterministic causal contextualization, deliberately dependent on
        # every past token, so it detects zero-gradient injection bugs.
        weights = 1 + torch.arange(inputs_embeds.shape[1], device=inputs_embeds.device)
        hidden = torch.cumsum(masked * weights[None, :, None], dim=1) / weights[None, :, None]
        return SimpleNamespace(last_hidden_state=hidden)


class _TinyLLM(nn.Module):
    def __init__(self, dim=8, vocab=13):
        super().__init__()
        self.embedding = nn.Embedding(vocab, dim)
        self.output = nn.Linear(dim, vocab, bias=False)
        self.model = _CausalEncoder()
        self.config = SimpleNamespace(hidden_size=dim, n_positions=128)
        self.is_gradient_checkpointing = False

    def get_input_embeddings(self):
        return self.embedding

    def forward(self, inputs_embeds, attention_mask=None, **kwargs):
        representation = self.model(inputs_embeds, attention_mask=attention_mask).last_hidden_state
        return SimpleNamespace(logits=self.output(representation))


def _modules():
    return MemoryModules(ShortMemoryConfig(hidden_size=8, memory_size=12, heads=3,
                                          layers=1, projection_size=8))


def test_tcl_gradients_reach_moment_token_through_frozen_decoder():
    torch.manual_seed(50)
    model = StageModel(_TinyLLM(), _modules(), 'tcl')
    model.train()
    batch = {key: torch.randn(2, 4, 8) for key in ('anchor', 'positive', 'negative')}
    for key in ('anchor', 'positive', 'negative'):
        batch[key + '_mask'] = torch.ones(2, 4, dtype=torch.bool)
    out = model(**batch)
    assert torch.isfinite(out['loss'])
    out['loss'].backward()
    gradient = model.modules_.moment.tokens.grad
    assert gradient is not None and torch.isfinite(gradient).all() and gradient.norm()>0
    assert all(p.grad is None for p in model.llm.parameters())
    assert all(p.grad is None for p in model.modules_.reader.parameters())


def _reader_batch():
    return {
        'prompt': torch.randn(2, 5, 8),
        'prompt_mask': torch.ones(2, 5, dtype=torch.bool),
        'past_moments': torch.randn(2, 3, 4, 8),
        'current_moment': torch.randn(2, 4, 8),
        'past_valid': torch.tensor([[True, True, True], [False, False, False]]),
        'ages': torch.tensor([[3, 2, 1, 0], [3, 2, 1, 0]]),
        'actions': torch.tensor([[1, 1, 2, 4], [4, 4, 4, 4]]),
        'target_ids': torch.tensor([[3, 4, 5], [6, 7, 8]], dtype=torch.long),
        'target_mask': torch.ones(2, 3, dtype=torch.bool),
        'kind': torch.tensor([0, 0]),
        'preserve': torch.tensor([False, False]),
    }


def test_reader_alpha_and_memory_gradients_with_history_and_empty_fallback():
    torch.manual_seed(51)
    model = StageModel(_TinyLLM(), _modules(), 'reader', memory_dropout=0)
    model.train()
    batch = _reader_batch()
    result = model(**batch)
    assert torch.isfinite(result['loss'])
    assert result['logits'][1, 1] == 0, 'empty history must have zero read probability'
    result['loss'].backward()
    alpha = model.modules_.reader.injection.alpha
    assert alpha.grad is not None and alpha.grad.abs()>0
    assert all(p.grad is None for p in model.llm.parameters())
    assert all(p.grad is None for p in model.modules_.moment.parameters())

    # Initially zero alpha only admits an alpha gradient. On the subsequent
    # step, nonzero alpha must propagate action-loss gradients into the Reader.
    model.zero_grad(set_to_none=True)
    with torch.no_grad(): alpha.fill_(0.2)
    result = model(**batch)
    result['loss'].backward()
    grad = model.modules_.reader.down.weight.grad
    assert grad is not None and torch.isfinite(grad).all() and grad.norm()>0

    # Sample 1 has no past, so the injection is an exact baseline identity.
    with torch.no_grad():
        memory,probs,_ = model.modules_.read(batch['current_moment'],batch['past_moments'],
                                              batch['past_valid'],batch['ages'],batch['actions'])
        adapted = model.modules_.reader.inject(batch['prompt'],batch['prompt_mask'],memory)
    assert probs[1].item() == 0.0
    torch.testing.assert_close(adapted[1], batch['prompt'][1], rtol=0, atol=0)
