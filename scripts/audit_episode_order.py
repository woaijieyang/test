"""Compare exact model-visible histories/actions for the same episode in two schedules."""

import argparse
from workspace import read_json, atomic_json, digest, owned
from result_contract import rows

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--paired-run", required=True)
    p.add_argument("--single-run", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    left = owned(a.paired_run)
    right = owned(a.single_run)
    lm = read_json(left / "run_manifest.json")
    rm = read_json(right / "run_manifest.json")
    for field in ("source_sha256", "model_sha256", "config_sha256", "navmesh_sha256"):
        if lm[field] != rm[field]:
            raise ValueError("Compared different identities: " + field)
    lrows = {r["task_key"]: r for r in rows(left / "results.jsonl")}
    rrows = rows(right / "results.jsonl")
    comparisons = []
    for row in rrows:
        other = lrows[row["task_key"]]
        left_trace = left / other["trace_path"]
        right_trace = right / row["trace_path"]
        paired_sequence = rows(left_trace)[0]["episode_sequence"]
        single_sequence = rows(right_trace)[0]["episode_sequence"]
        if paired_sequence <= 1 or single_sequence != 1:
            raise ValueError("Comparison did not actually move B from after A to the first episode")
        paired_device = read_json(left_trace.parents[2] / "worker-done.json")[
            "CUDA_VISIBLE_DEVICES"
        ]
        single_device = read_json(right_trace.parents[2] / "worker-done.json")[
            "CUDA_VISIBLE_DEVICES"
        ]
        if paired_device != single_device:
            raise ValueError("Use the same physical GPU to isolate the episode-order variable")

        def view(run, r):
            result = []
            for event in rows(run / r["trace_path"]):
                if event["kind"] == "model_call":
                    result.append(
                        {
                            "kind": "model_call",
                            "prompt": event["prompt"],
                            "images": [x["pixel_sha256"] for x in event["images"]],
                            "input_ids": event["input_ids"],
                            "processed_image_sha256": event["processed_image_sha256"],
                            "output_ids": event["output_ids"],
                            "normalized_output": event["normalized_output"],
                        }
                    )
                elif event["kind"] == "primitive_action":
                    result.append(
                        {
                            "kind": "primitive_action",
                            "action": event["action"],
                            "before": event["before_evaluator_only"]["position"],
                            "after": event["after_evaluator_only"]["position"],
                        }
                    )
            return result

        equal = view(left, other) == view(right, row)
        comparisons.append(
            {
                "task_key": row["task_key"],
                "paired_sequence": paired_sequence,
                "single_sequence": single_sequence,
                "physical_gpu": paired_device,
                "equal_model_inputs_outputs_and_actions": equal,
            }
        )
    if not comparisons:
        raise ValueError("No shared actual episodes")
    result = {
        "status": (
            "PASS"
            if all(r["equal_model_inputs_outputs_and_actions"] for r in comparisons)
            else "FAIL"
        ),
        "source_sha256": lm["source_sha256"],
        "navmesh_sha256": lm["navmesh_sha256"],
        "comparisons": comparisons,
        "run_manifests": [
            {"path": str(p / "run_manifest.json"), "sha256": digest(p / "run_manifest.json")}
            for p in (left, right)
        ],
    }
    atomic_json(a.output, result)
    if result["status"] != "PASS":
        raise SystemExit("Real episode order check differs; investigate before full evaluation")
    print(result["status"])
