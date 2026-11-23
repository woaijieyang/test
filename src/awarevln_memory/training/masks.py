"""One prompt/target boundary shared by legacy adapters and new training."""
from __future__ import annotations
import torch
from torch import Tensor


def causal_prompt_mask(attention_mask, labels, prompt_mask, shape, device) -> Tensor:
    active = (torch.ones(shape, dtype=torch.bool, device=device) if attention_mask is None
              else attention_mask.to(device=device, dtype=torch.bool))
    if tuple(active.shape) != tuple(shape):
        raise ValueError("attention mask shape differs from input")
    allowed = active.clone()
    if labels is not None:
        if tuple(labels.shape) != tuple(shape):
            raise ValueError("labels shape differs from input")
        target = labels.to(device).ne(-100) & active
        # Ignore all tokens after the FIRST target, including ignored target tokens.
        allowed &= target.long().cumsum(-1).eq(0)
    if prompt_mask is not None:
        explicit = prompt_mask.to(device=device, dtype=torch.bool)
        if tuple(explicit.shape) != tuple(shape):
            raise ValueError("prompt mask shape differs from input")
        if (explicit & ~allowed).any():
            raise ValueError("prompt mask exposes target/padding/future tokens")
        allowed &= explicit
    if not allowed.any(-1).all():
        raise ValueError("each query needs a nonempty causal prompt")
    return allowed


def block_causal_mask(slots: int, moments: int, device=None) -> Tensor:
    if slots < 1 or moments < 1:
        raise ValueError("positive slots and moments required")
    time = torch.arange(slots, device=device).repeat_interleave(moments)
    return time[None, :] > time[:, None]
