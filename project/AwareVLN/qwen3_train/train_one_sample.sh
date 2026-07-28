#!/usr/bin/env bash
set -euo pipefail

QWEN_ENV="${QWEN_ENV:-/home/zy/DataDrive/qwen/conda-envs/qwen3vl}"
MODEL_PATH="${MODEL_PATH:-/home/zy/DataDrive/qwen/Qwen3-VL-4B-Instruct}"
MINI_ROOT="${AWAREVLN_MINI_ROOT:-/home/zy/DataDrive/qwen/AwareVLN-mini}"
QWEN_FINETUNE_ROOT="${QWEN_FINETUNE_ROOT:-/mnt/data/Project/vln/Qwen3-VL/qwen-vl-finetune}"
OUTPUT_DIR="${OUTPUT_DIR:-/home/zy/DataDrive/qwen/outputs/awarevln-qwen3vl-4b-one-sample}"

export AWAREVLN_MINI_ROOT="$MINI_ROOT"
export HF_HOME="${HF_HOME:-/home/zy/DataDrive/qwen/hf-cache}"
export TMPDIR="${TMPDIR:-/home/zy/DataDrive/qwen/tmp}"
export QWEN_ATTN_IMPLEMENTATION="${QWEN_ATTN_IMPLEMENTATION:-sdpa}"
export TOKENIZERS_PARALLELISM=false
export WANDB_DISABLED=true

mkdir -p "$OUTPUT_DIR" "$HF_HOME" "$TMPDIR"
cd "$QWEN_FINETUNE_ROOT"

"$QWEN_ENV/bin/python" qwenvl/train/train_qwen.py \
  --model_name_or_path "$MODEL_PATH" \
  --dataset_use awarevln_mini_one \
  --tune_mm_vision False \
  --tune_mm_mlp False \
  --tune_mm_llm True \
  --lora_enable True \
  --lora_r 16 \
  --lora_alpha 32 \
  --lora_dropout 0.05 \
  --bf16 True \
  --output_dir "$OUTPUT_DIR" \
  --overwrite_output_dir True \
  --num_train_epochs 1 \
  --max_steps 10 \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 1 \
  --learning_rate 1e-4 \
  --weight_decay 0.0 \
  --warmup_ratio 0.0 \
  --lr_scheduler_type constant \
  --logging_steps 1 \
  --save_strategy no \
  --eval_strategy no \
  --report_to none \
  --model_max_length 4096 \
  --max_pixels 50176 \
  --min_pixels 50176 \
  --gradient_checkpointing True \
  --dataloader_num_workers 0 \
  --remove_unused_columns False \
  --seed 10
