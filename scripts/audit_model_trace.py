"""Replay official output normalization/parser and reconcile every executed primitive."""

import argparse, hashlib, re, os, io, json, datetime
from workspace import ROOT, atomic_json, digest, owned
from result_contract import rows


def normalize(text, stop, sep2):
    if text.endswith(stop):
        text = text[: -len(stop)].strip()
    if text.endswith(sep2):
        text = text[: -len(sep2)].strip()
    if text.startswith("<|begin_of_text|>"):
        text = text[len("<|begin_of_text|>") :].strip()
    return text


def parse(text):
    if text.startswith("<BEGIN_OF_REASONING>"):
        return [], True, False
    if text.startswith("<BEGIN_OF_ACTION>"):
        text = text[len("<BEGIN_OF_ACTION>") :].strip()
    patterns = [r"\bstop\b", "move forward", "turn left", "turn right"]
    matches = [i for i, p in enumerate(patterns) if re.search(p, text, re.I)]
    action = matches[0] if matches else 1
    if action == 0:
        return [0], False, False
    unit = 25 if action == 1 else 15
    expression = {
        1: r"move forward (\d+) cm",
        2: r"turn left (\d+) degree",
        3: r"turn right (\d+) degree",
    }[action]
    match = re.search(expression, text)
    value = int(match.group(1)) if match else unit
    if value % unit:
        value = min([unit, unit * 2, unit * 3], key=lambda x: abs(x - value))
    return [action] * max(1, value // unit), False, not matches


def inspect(events):
    queue = []
    reasons = 0
    errors = []
    fallbacks = 0
    call = 0
    steps = 0
    if not events or events[0]["kind"] != "reset" or events[-1]["kind"] != "terminal":
        return ["unclosed trace"], 0
    for event in events:
        if event["kind"] == "model_call":
            if queue:
                errors.append("model called with pending primitive queue")
            call += 1
            text = normalize(event["raw_decoded_output"], event["stop_str"], event["sep2"])
            if text != event["normalized_output"]:
                errors.append("normalization differs from official parser")
            actions, reason, fallback = parse(text)
            fallbacks += int(fallback)
            if reason:
                reasons += 1
            else:
                queue = actions
            if event["call_id"] != call:
                errors.append("nonsequential model call identity")
            if event["generation"] != {
                "do_sample": False,
                "temperature": 0.0,
                "max_new_tokens": 256,
            }:
                errors.append("generation protocol changed")
        elif event["kind"] == "primitive_action":
            steps += 1
            if event["step"] != steps:
                errors.append("nonsequential primitive identity")
            expected = 0 if reasons > 3 else queue.pop(0) if queue else None
            if event["action"] != expected:
                errors.append("executed action differs from official parser/queue")
            if event["last_call_id"] != call:
                errors.append("action linked to wrong model call")
            reasons = 0
    if call == 0 or steps == 0:
        errors.append("missing real model or primitive evidence")
    if events[-1].get("steps") != steps or events[-1].get("model_calls") != call:
        errors.append("terminal counters differ from trace")
    return errors, fallbacks


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True)
    a = p.parse_args()
    if not os.environ.get("CASE1_PROTECTION"):
        raise SystemExit("Use protected runtime for model trace auditing")
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    run = owned(a.run)
    errors = []
    keys = []
    fallbacks = 0
    verified_images = {}
    consumed_traces = []
    from PIL import Image
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        str(ROOT / "models/awarevln/llm"), local_files_only=True
    )

    for row in rows(run / "results.jsonl"):
        trace_path = owned(run / row["trace_path"]).resolve()
        if run.resolve() not in trace_path.parents:
            raise ValueError("Trace escaped the run")
        trace_bytes = trace_path.read_bytes()
        trace_sha = hashlib.sha256(trace_bytes).hexdigest()
        if trace_sha != row["trace_sha256"]:
            raise ValueError("Trace changed before semantic audit")
        events = [
            json.loads(line) for line in trace_bytes.decode("utf-8").splitlines() if line.strip()
        ]
        consumed_traces.append(
            {"task_key": row["task_key"], "path": row["trace_path"], "sha256": trace_sha}
        )
        task_errors, count = inspect(events)
        fallbacks += count
        inputs = {e["call_id"]: e for e in events if e["kind"] == "model_input"}
        if len(inputs) != sum(e["kind"] == "model_input" for e in events):
            task_errors.append("duplicate pre-generation model input")
        for event in events:
            if event["kind"] != "model_call":
                continue
            decoded = tokenizer.batch_decode(event["output_ids"], skip_special_tokens=False)[
                0
            ].strip()
            if decoded != event["raw_decoded_output"]:
                task_errors.append("stored text differs from decoded actual model token IDs")
            before = inputs.get(event["call_id"])
            if before is None:
                task_errors.append("model input not persisted before generation")
            elif any(event.get(k) != v for k, v in before.items() if k not in ("kind", "task_key")):
                task_errors.append("model input/result pairing changed")
            if (
                not event["prompt"]
                or not event["images"]
                or not event["input_ids"]
                or not event["processed_image_sha256"]
            ):
                task_errors.append("missing actual model input evidence")
            for ref in event["images"]:
                image_path = owned(run / ref["path"]).resolve()
                if run.resolve() not in image_path.parents:
                    raise ValueError("Image reference escapes run")
                name = image_path.relative_to(run.resolve()).as_posix()
                if name not in verified_images:
                    blob = image_path.read_bytes()
                    with Image.open(io.BytesIO(blob)) as im:
                        pixel_hash = hashlib.sha256(
                            im.mode.encode() + str(im.size).encode() + im.tobytes()
                        ).hexdigest()
                    verified_images[name] = {
                        "sha256": hashlib.sha256(blob).hexdigest(),
                        "pixel_sha256": pixel_hash,
                    }
                value = verified_images[name]["pixel_sha256"]
                if value != ref["pixel_sha256"]:
                    task_errors.append("model image hash mismatch")
        errors.extend({"task_key": row["task_key"], "error": e} for e in task_errors)
        keys.append(row["task_key"])
    atomic_json(
        run / "semantic_audit.json",
        {
            "method": "model_action_trace_audit_v1",
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "manifest_sha256": digest(run / "run_manifest.json"),
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "task_keys": keys,
            "official_fallback_calls": fallbacks,
            "trace_files": consumed_traces,
            "image_files": [
                {"path": path, **record} for path, record in sorted(verified_images.items())
            ],
            "scope": "Source-frozen model inputs and parser-to-action execution consistency; not proof of semantic navigation success.",
        },
    )
    if errors:
        raise SystemExit("Model/action audit failed")
    print({"tasks": len(keys), "official_fallback_calls": fallbacks})


if __name__ == "__main__":
    main()
