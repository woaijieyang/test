"""CPU-only check of the real official tokenizer and eight-frame preprocessing path."""

import os, json
from workspace import ROOT, atomic_json

if not os.environ.get("CASE1_PROTECTION"):
    raise RuntimeError("Use protected runtime")
os.environ["CUDA_VISIBLE_DEVICES"] = ""
import importlib, torch

importlib.import_module(
    "llava.model.builder"
)  # Register the same official model classes as the trainer.
from PIL import Image
from transformers import AutoTokenizer, AutoImageProcessor, AutoConfig
from llava.mm_utils import process_images, tokenizer_image_token
from llava.constants import IMAGE_TOKEN_INDEX
from llava.conversation import conv_templates

root = ROOT / "models/awarevln"
tokenizer = AutoTokenizer.from_pretrained(str(root / "llm"), local_files_only=True)
processor = AutoImageProcessor.from_pretrained(
    str(root / "vision_tower"), local_files_only=True
)
config = AutoConfig.from_pretrained(str(root), local_files_only=True)
images = [Image.new("RGB", (512, 512), (i * 20, i * 20, i * 20)) for i in range(8)]
pixels = process_images(images, processor, config).to(dtype=torch.float16)
assert tuple(pixels.shape) == (8, 3, 384, 384) and torch.isfinite(pixels).all()
conv = conv_templates["llama_3"].copy()
conv.append_message(conv.roles[0], "<image>\n" * 8 + "Synthetic preprocessing check.")
conv.append_message(conv.roles[1], None)
ids = tokenizer_image_token(
    conv.get_prompt(), tokenizer, IMAGE_TOKEN_INDEX, return_tensors="pt"
)
assert int((ids == IMAGE_TOKEN_INDEX).sum()) == 8
modes = {
    x: tokenizer.convert_tokens_to_ids(x)
    for x in ("<BEGIN_OF_REASONING>", "<BEGIN_OF_ACTION>")
}
vocab = json.loads((root / "llm/config.json").read_text())["vocab_size"]
assert len(set(modes.values())) == 2 and all(
    isinstance(i, int) and i != tokenizer.unk_token_id and 0 <= i < vocab
    for i in modes.values()
)
record = {
    "status": "PASS",
    "scope": "CPU tokenizer/image processing only; no model weight load or generation",
    "pixel_shape": list(pixels.shape),
    "pixel_dtype": str(pixels.dtype),
    "image_tokens": 8,
    "mode_tokens": modes,
    "tokenizer_size": len(tokenizer),
    "embedding_vocab_size": vocab,
    "processor_class": type(processor).__name__,
    "model_config_class": type(config).__name__,
}
atomic_json(ROOT / "outputs/setup/model-input-components.json", record)
print(record)
