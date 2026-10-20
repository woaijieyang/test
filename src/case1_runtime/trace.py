import hashlib, json, math, os
from pathlib import Path


def safe(value):
    if isinstance(value, dict):
        return {str(k): safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [safe(v) for v in value]
    if hasattr(value, "item"):
        return safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": str(value)}
    return value


def identity(dataset, ep):
    instruction = getattr(ep.instruction, "instruction_id", None)
    scene = "mp3d/" + Path(ep.scene_id).parent.name + "/" + Path(ep.scene_id).name
    return "|".join(
        (
            dataset,
            "val_unseen",
            "en-US" if dataset == "rxr" else "en",
            scene,
            str(ep.episode_id),
            str(instruction) if instruction is not None else "-",
        )
    )


class TraceRecorder:
    @staticmethod
    def effective_configuration(config):
        root = Path(os.environ["AWAREVLN_ROOT"]).resolve()
        out = Path(os.environ["CASE1_TRACE_ROOT"]).resolve()
        if root / "outputs" not in out.parents:
            raise RuntimeError("Effective configuration escaped outputs")
        with (out / "effective-config.yaml").open("x", encoding="utf-8") as handle:
            handle.write(str(config))

    @staticmethod
    def model_loaded(checkpoint, tokenizer, model):
        import sys, torch, transformers, inspect

        ids = [
            tokenizer.convert_tokens_to_ids(t)
            for t in ("<BEGIN_OF_REASONING>", "<BEGIN_OF_ACTION>")
        ]
        if len(set(ids)) != 2 or any(
            i is None or i < 0 or i == tokenizer.unk_token_id for i in ids
        ):
            raise RuntimeError("Official mode tokens are not valid")
        root = Path(os.environ["AWAREVLN_ROOT"]).resolve()
        if Path(sys.prefix).resolve() != root / "runtime/awarevln":
            raise RuntimeError("Model imported from wrong environment")
        source = Path(inspect.getfile(type(model))).resolve()
        if root / "src" not in source.parents:
            raise RuntimeError("Model class did not come from tracked project source")
        out = Path(os.environ["CASE1_TRACE_ROOT"]).resolve()
        if root / "outputs" not in out.parents:
            raise RuntimeError("Receipt outside outputs")
        record = {
            "status": "LOADED_PENDING_REAL_GENERATION",
            "checkpoint": str(Path(checkpoint).resolve()),
            "python": sys.executable,
            "prefix": sys.prefix,
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "model_class": type(model).__module__ + "." + type(model).__name__,
            "mode_token_ids": ids,
            "tokenizer_size": len(tokenizer),
            "device": str(model.device),
            "dtype": str(model.dtype),
            "source_sha256": os.environ["CASE1_SOURCE_SHA256"],
        }
        record.update(
            {"model_source_file": str(source), "num_video_frames": model.config.num_video_frames}
        )
        (out / "model-receipt.json").write_text(json.dumps(record, indent=2))

    def __init__(self, root, dataset):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.run_root = Path(os.environ.get("CASE1_RUN_ROOT", str(self.root))).resolve()
        self.dataset = dataset
        self.key = None
        self.handle = None
        self.calls = 0
        self.steps = 0
        self.directory = None
        self.last_call = None
        self.pending_call = None
        self.episode_sequence = 0

    @classmethod
    def from_environment(cls):
        root = os.environ.get("CASE1_TRACE_ROOT")
        dataset = os.environ.get("CASE1_DATASET")
        if not root or dataset not in ("r2r", "rxr") or not os.environ.get("CASE1_PROTECTION"):
            raise RuntimeError("Missing protected trace runtime")
        resolved = Path(root).resolve()
        owned = Path(os.environ["AWAREVLN_ROOT"]).resolve() / "outputs"
        if owned not in resolved.parents:
            raise RuntimeError("Trace output escapes outputs")
        return cls(resolved, dataset)

    def write(self, row):
        self.handle.write(
            json.dumps(safe({"task_key": self.key, **row}), ensure_ascii=False, allow_nan=False)
            + "\n"
        )
        self.handle.flush()

    def ensure_episode(self, ep, state):
        key = identity(self.dataset, ep)
        if key == self.key:
            if self.handle is None:
                raise RuntimeError("Completed episode was dispatched again")
            return
        if self.handle:
            raise RuntimeError("New episode before terminal trace")
        self.key = key
        self.episode_sequence += 1
        self.calls = self.steps = 0
        self.last_call = None
        self.directory = self.root / "episodes" / hashlib.sha256(key.encode()).hexdigest()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.handle = (self.directory / "trace.jsonl").open("x", encoding="utf-8")
        self.write(
            {
                "kind": "reset",
                "episode_sequence": self.episode_sequence,
                "state_evaluator_only": state,
                "scene": ep.scene_id,
                "episode_id": str(ep.episode_id),
                "instruction_id": getattr(ep.instruction, "instruction_id", None),
            }
        )

    def begin_model_call(self, ep, frame, prompt, images, input_ids, tensor, stop_str, sep2):
        if identity(self.dataset, ep) != self.key:
            raise RuntimeError("Model episode mismatch")
        if self.pending_call is not None:
            raise RuntimeError("Unfinished prior model call")
        assets = self.root / "images"
        assets.mkdir(exist_ok=True)
        refs = []
        for image in images:
            pixels = image.tobytes()
            h = hashlib.sha256(image.mode.encode() + str(image.size).encode() + pixels).hexdigest()
            p = assets / (h + ".png")
            if not p.exists():
                image.save(p)
            refs.append(
                {
                    "path": str(p.relative_to(self.run_root)),
                    "pixel_sha256": h,
                    "size": list(image.size),
                    "mode": image.mode,
                }
            )
        self.calls += 1
        self.last_call = self.calls
        values = tensor.detach().cpu().contiguous().numpy()
        self.pending_call = {
            "call_id": self.calls,
            "frame": frame,
            "prompt": prompt,
            "images": refs,
            "input_ids": input_ids.detach().cpu().tolist(),
            "processed_image_shape": list(values.shape),
            "processed_image_sha256": hashlib.sha256(values.tobytes()).hexdigest(),
            "stop_str": stop_str,
            "sep2": sep2,
            "generation": {"do_sample": False, "temperature": 0.0, "max_new_tokens": 256},
        }
        self.write({"kind": "model_input", **self.pending_call})
        return self.calls

    def finish_model_call(self, call_id, output_ids, text, normalized):
        if self.pending_call is None or self.pending_call["call_id"] != call_id:
            raise RuntimeError("Model result has no matching input")
        self.write(
            {
                "kind": "model_call",
                **self.pending_call,
                "output_ids": output_ids.detach().cpu().tolist(),
                "raw_decoded_output": text,
                "normalized_output": normalized,
            }
        )
        self.pending_call = None

    def step(self, ep, action, before, after, done, info, stop_source="model"):
        if identity(self.dataset, ep) != self.key:
            raise RuntimeError("Action episode mismatch")
        self.steps += 1
        self.write(
            {
                "kind": "primitive_action",
                "step": self.steps,
                "action": action,
                "last_call_id": self.last_call,
                "before_evaluator_only": before,
                "after_evaluator_only": after,
                "done": bool(done),
                "stop_source": stop_source if action == 0 else None,
            }
        )
        if done:
            reason = (
                "stop"
                if action == 0
                else "max_steps" if after["elapsed_steps"] >= 500 else "environment_terminal"
            )
            self.write(
                {
                    "kind": "terminal",
                    "steps": self.steps,
                    "model_calls": self.calls,
                    "termination_reason": reason,
                    "stop_source": stop_source if action == 0 else None,
                    "native_metrics": info,
                }
            )
            self.handle.close()
            self.handle = None
            path = self.directory / "trace.jsonl"
            metrics = {
                dst: float(info[src])
                for src, dst in [
                    ("success", "sr"),
                    ("spl", "spl"),
                    ("ndtw", "ndtw"),
                    ("distance_to_goal", "ne"),
                    ("oracle_success", "oracle_sr"),
                ]
            }
            row = {
                "task_key": self.key,
                "dataset": self.dataset,
                "status": "completed",
                "episode_sequence": self.episode_sequence,
                "metrics": metrics,
                "trace_path": str(path.relative_to(self.root)),
                "trace_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "effective_config_path": "effective-config.yaml",
                "effective_config_sha256": hashlib.sha256(
                    (self.root / "effective-config.yaml").read_bytes()
                ).hexdigest(),
                "termination_reason": reason,
                "primitive_steps": self.steps,
                "model_calls": self.calls,
                "stop_source": stop_source if action == 0 else None,
            }
            temporary = self.directory / "result.json.new"
            with temporary.open("x", encoding="utf-8") as f:
                f.write(json.dumps(safe(row), allow_nan=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            temporary.replace(self.directory / "result.json")
            with (self.root / "results.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(safe(row), allow_nan=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def close(self):
        if self.handle:
            raise RuntimeError("Evaluation exited with an unclosed episode")
