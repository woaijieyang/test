"""Opt-in HAMLET inference on the baseline's observed-image/action loop."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import torch

from awarevln_memory.cbem.model_identity import verify_model_attestation
from awarevln_memory.memory.state import EpisodeMemory


def tensor_record(value):
    if value is None:
        return None
    value = value.detach().contiguous()
    raw = value.cpu().view(torch.uint8).numpy().tobytes()
    return {"shape": list(value.shape), "dtype": str(value.dtype),
            "sha256": hashlib.sha256(raw).hexdigest()}


class HAMLETRuntime:
    """Receives policy inputs only; simulator truth is never an argument."""

    def __init__(self, model, config, output):
        self.model = model
        self.config = config
        expected = {"condition": "archive", "mode_lock": True,
                    "read_threshold": 0.0, "alpha_scale": 0.5,
                    "write_threshold": 0.8, "turn_fallback_after": 3,
                    "turn_fallback_calls": 2}
        if config["parameters"] != expected:
            raise ValueError("Historical candidate parameters changed")
        base = verify_model_attestation(
            config["base_model"], config["base_attestation"],
            verify_content=True,
            expected_attestation_sha256=config["base_attestation_sha256"])
        model.init_memory_adapter(config["adapter"])
        model.memory_adapter.eval()
        model.init_cbem_router(
            config["router"], source_adapter_checkpoint=config["adapter"],
            base_model_identity=base["canonical_identity"])
        self.stream = Path(output).open("x", encoding="utf-8")
        self.episode = None
        self.state = None
        self.calls = 0
        self.turns = 0
        self.fallback_remaining = 0
        self.write({"kind": "initialized", "policy": config,
                    "base_verification": base,
                    "router_deployment": model.cbem_router.deployment_disclosure})

    def write(self, record):
        self.stream.write(json.dumps(record, allow_nan=False, sort_keys=True) + "\n")
        self.stream.flush()

    def begin_episode(self, episode):
        episode = str(episode)
        if self.episode == episode:
            return
        if self.episode is not None:
            raise RuntimeError("New episode reached before explicit memory reset")
        self.episode = episode
        adapter = self.model.memory_adapter.config
        self.state = EpisodeMemory(
            recent_calls=adapter.recent_calls, max_event_items=adapter.max_event_items,
            write_threshold=0.8,
            max_archive_items=self.model.cbem_router.config.archive_capacity)
        self.calls = self.turns = self.fallback_remaining = 0
        self.write({"kind": "reset", "episode_id": episode,
                    "archive_items": 0, "policy_calls": 0,
                    "turns": 0, "fallback_remaining": 0})

    @torch.inference_mode()
    def generate(self, *, episode, call_id, frame, input_ids, images, **kwargs):
        self.begin_episode(episode)
        if int(call_id) != self.calls + 1:
            raise RuntimeError("Baseline trace and HAMLET call IDs diverged")
        policy_call = self.calls
        memory = self.state.as_tensors(condition="archive", device=self.model.device)
        archive_ids = memory.pop("item_ids")
        item_records = [{"item_id": item.item_id,
                         "policy_call_id": item.policy_call_id,
                         "moment": tensor_record(item.moment)}
                        for item in self.state.archive]
        if any(item["policy_call_id"] >= policy_call for item in item_records):
            raise RuntimeError("Current or future memory entered generation")
        triggered = self.turns >= 3 and self.fallback_remaining == 0
        if triggered:
            self.fallback_remaining = 2
            self.turns = 0
        fallback_active = self.fallback_remaining > 0
        if fallback_active:
            self.fallback_remaining -= 1
        evidence = {"kind": "memory_input", "episode_id": self.episode,
                    "call_id": int(call_id), "policy_call_id": policy_call,
                    "frame": int(frame), "archive_items": item_records,
                    "input_ids": tensor_record(input_ids), "images": tensor_record(images),
                    "memory_tensors": {k: tensor_record(v) for k, v in memory.items()},
                    "enabled": not fallback_active, "fallback_triggered": triggered,
                    "fallback_active": fallback_active,
                    "fallback_remaining": self.fallback_remaining}
        self.write(evidence)
        captured = {}

        def adapter_hook(module, args, output):
            base = args[0]
            adapted = output.adapted_inputs
            captured["tensor"] = adapted
            captured["base"] = tensor_record(base)
            captured["adapted"] = tensor_record(adapted)
            captured["max_abs_delta"] = float((adapted.float() - base.float()).abs().max())
            captured["consumed"] = False

        def llm_prefill_hook(module, args, kw):
            value = kw.get("inputs_embeds")
            if value is None or captured.get("consumed") or "tensor" not in captured:
                return
            expected = captured["tensor"]
            if value.shape != expected.shape or value.dtype != expected.dtype:
                raise RuntimeError("Generation prefill shape/dtype differs from adapted prompt")
            if not torch.equal(value, expected):
                raise RuntimeError("Generation did not consume the recorded adapted prompt")
            captured["consumed"] = True
            captured["prefill"] = tensor_record(value)
            captured["same_storage"] = value.data_ptr() == expected.data_ptr()

        with self.model.memory_adapter.register_forward_hook(adapter_hook), \
             self.model.llm.register_forward_pre_hook(llm_prefill_hook, with_kwargs=True):
            generation = self.model.generate_with_memory(
                input_ids, images=images, memory_enabled=not fallback_active,
                memory_read_threshold=0.0, memory_alpha_scale=0.5,
                preserve_base_mode=True, **memory, **kwargs)
        if not captured.get("consumed"):
            raise RuntimeError("No actual generation prefill consumption observed")
        selection = generation.cbem_selection
        coarse_ids = []
        selected_ids = []
        selected_mask = []
        router_metrics = None
        if selection is not None:
            indices = selection.coarse_indices[0].detach().cpu().tolist()
            candidate_mask = selection.candidate_mask[0].detach().cpu().tolist()
            coarse_ids = [archive_ids[i] if valid else None
                          for i, valid in zip(indices, candidate_mask)]
            indices = selection.selected_indices[0].detach().cpu().tolist()
            selected_mask = selection.selected_mask[0].detach().cpu().tolist()
            selected_ids = [archive_ids[i] for i, valid in zip(indices, selected_mask) if valid]
            router_metrics = selection.detached_metrics()
        adapter_output = generation.adapter_output
        if adapter_output is None:
            raise RuntimeError("HAMLET returned no adapter output")
        write_probability = float(adapter_output.write_probability[0].item())
        moment = tensor_record(generation.moment_tokens)
        before = [item.item_id for item in self.state.archive]
        self.state.observe(generation.moment_tokens, policy_call,
                           write_probability=write_probability,
                           metadata={"frame_id": int(frame), "moment_ref": None})
        self.calls += 1
        self.write({"kind": "memory_generation", "episode_id": self.episode,
                    "call_id": int(call_id), "policy_call_id": policy_call,
                    "archive_item_ids": archive_ids,
                    "coarse_candidate_item_ids": coarse_ids,
                    "selected_item_ids": selected_ids, "selected_mask": selected_mask,
                    "router": router_metrics,
                    "adapter": adapter_output.detached_metrics(),
                    "base_prompt": captured["base"], "adapted_prompt": captured["adapted"],
                    "generation_prefill": captured["prefill"],
                    "prefill_same_storage": captured["same_storage"],
                    "prompt_max_abs_delta": captured["max_abs_delta"],
                    "mode_lock_applied": generation.mode_lock_applied,
                    "base_mode_token_id": (int(generation.base_mode_token_ids[0])
                                           if generation.base_mode_token_ids is not None else None),
                    "moment_tokens": moment, "write_probability": write_probability,
                    "archive_before_write": before,
                    "archive_after_write": [item.item_id for item in self.state.archive],
                    "stored_moment": tensor_record(self.state.archive[-1].moment),
                    "output_tokens": tensor_record(generation.sequences)})
        return generation.sequences

    def action_decision(self, action, call_id):
        if int(call_id) != self.calls:
            raise RuntimeError("Action feedback is not bound to latest generation")
        self.turns = self.turns + 1 if int(action) in (2, 3) else 0
        self.write({"kind": "action_decision", "episode_id": self.episode,
                    "call_id": int(call_id), "action": int(action),
                    "consecutive_turn_decisions": self.turns})

    def end_episode(self, episode):
        if self.episode is None:
            return
        if self.episode != str(episode):
            raise RuntimeError("Memory terminal episode mismatch")
        count = len(self.state.archive)
        calls = self.calls
        self.state.clear()
        self.write({"kind": "terminal_reset", "episode_id": self.episode,
                    "calls": calls, "archive_before_clear": count,
                    "archive_after_clear": len(self.state.archive)})
        self.episode = None
        self.calls = self.turns = self.fallback_remaining = 0

    def close(self):
        if self.episode is not None:
            raise RuntimeError("HAMLET runtime closed before episode completion")
        self.stream.close()
