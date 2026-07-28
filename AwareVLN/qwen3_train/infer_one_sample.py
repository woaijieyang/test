#!/usr/bin/env python3
"""Run the saved AwareVLN Qwen3-VL LoRA adapter on its smoke-test sample."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", default="/home/zy/DataDrive/qwen/Qwen3-VL-4B-Instruct"
    )
    parser.add_argument(
        "--adapter",
        default="/home/zy/DataDrive/qwen/outputs/awarevln-qwen3vl-4b-one-sample",
    )
    parser.add_argument(
        "--sample",
        default="/home/zy/DataDrive/qwen/AwareVLN-mini/reason/r2rfollow/qwen3_sft/one_sample.json",
    )
    parser.add_argument(
        "--image-root",
        default="/home/zy/DataDrive/qwen/AwareVLN-mini/reason/r2rfollow/videos",
    )
    parser.add_argument(
        "--qwen-finetune-root",
        default="/mnt/data/Project/vln/Qwen3-VL/qwen-vl-finetune",
    )
    parser.add_argument("--max-new-tokens", type=int, default=128)
    args = parser.parse_args()

    sys.path.insert(0, args.qwen_finetune_root)
    from qwenvl.data.data_processor import _build_messages

    sample = json.loads(Path(args.sample).read_text(encoding="utf-8"))[0]
    target = sample["conversations"][1]["value"]
    prompt_only = dict(sample)
    prompt_only["conversations"] = sample["conversations"][:1]
    prompt_only["data_path"] = args.image_root
    messages = _build_messages(prompt_only, Path(args.image_root))

    processor = AutoProcessor.from_pretrained(args.model)
    base = Qwen3VLForConditionalGeneration.from_pretrained(
        args.model, dtype=torch.bfloat16, attn_implementation="sdpa"
    )
    model = PeftModel.from_pretrained(base, args.adapter).to("cuda").eval()
    model.config.use_cache = True

    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    ).to("cuda")

    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=args.max_new_tokens,
            do_sample=False,
            use_cache=True,
        )
    generated = output[:, inputs["input_ids"].shape[1] :]
    text = processor.batch_decode(generated, skip_special_tokens=True)[0]
    print("TARGET:")
    print(target)
    print("GENERATED:")
    print(text)


if __name__ == "__main__":
    main()
