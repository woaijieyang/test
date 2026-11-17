import os, json, hashlib
from pathlib import Path
from preflight import dataset_base, configure_dataset, SPECS, load, task_key

if not os.environ.get("CASE1_PROTECTION"):
    raise RuntimeError("Use protected runtime")
os.environ["CUDA_VISIBLE_DEVICES"] = ""
from vlnce_baselines.config.default import get_config
import habitat

out = []
for ds in ("r2r", "rxr"):
    c = get_config("configs/vlnce_baselines/config/" + ds + "_baselines/awarevln.yaml")
    c.defrost()
    c.TASK_CONFIG.DATASET.NUM_CHUNKS = 1
    c.TASK_CONFIG.DATASET.CHUNK_IDX = 0
    c.TASK_CONFIG.DATASET.SPLIT = "val_unseen"
    c.TASK_CONFIG.DATASET.ROLES = ["guide"]
    c.TASK_CONFIG.DATASET.LANGUAGES = c.EVAL.LANGUAGES
    configure_dataset(c, ds)
    c.freeze()
    dataset = habitat.make_dataset(
        c.TASK_CONFIG.DATASET.TYPE, config=c.TASK_CONFIG.DATASET
    )
    directory, annotation, gt, count = SPECS[ds]
    raw = load(dataset_base(ds) / annotation)["episodes"]
    raw = [e for e in raw if ds != "rxr" or e["instruction"]["language"] == "en-US"]
    expected = {str(e["episode_id"]): e for e in raw}
    assert set(expected) == {str(e.episode_id) for e in dataset.episodes}
    for e in dataset.episodes:
        original = expected[str(e.episode_id)]
        assert list(e.start_position) == original["start_position"]
        assert [list(g.position) for g in e.goals] == [
            g["position"] for g in original["goals"]
        ]
        assert (
            e.instruction.instruction_text
            == original["instruction"]["instruction_text"]
        )
        assert "/".join(Path(e.scene_id).parts[-3:]) == original["scene_id"]
        if ds == "rxr":
            assert str(e.instruction.instruction_id) == str(
                original["instruction"]["instruction_id"]
            )
    record = {
        "dataset": ds,
        "native_episodes": len(dataset.episodes),
        "height": c.TASK_CONFIG.SIMULATOR.AGENT_0.HEIGHT,
        "radius": c.TASK_CONFIG.SIMULATOR.AGENT_0.RADIUS,
        "step": c.TASK_CONFIG.SIMULATOR.FORWARD_STEP_SIZE,
        "turn": c.TASK_CONFIG.SIMULATOR.TURN_ANGLE,
        "max_steps": c.TASK_CONFIG.ENVIRONMENT.MAX_EPISODE_STEPS,
        "seed": c.TASK_CONFIG.SEED,
    }
    assert record["native_episodes"] == (1839 if ds == "r2r" else 1223), record
    assert (
        record["height"],
        record["radius"],
        record["step"],
        record["turn"],
        record["max_steps"],
    ) == (1.5, 0.1, 0.25, 15, 500)
    record["task_keys_sha256"] = hashlib.sha256(
        json.dumps(sorted(task_key(ds, e) for e in raw)).encode()
    ).hexdigest()
    record["exact_annotations_preserved"] = True
    out.append(record)
Path("outputs/setup/native-dataset-config-probe.json").write_text(
    json.dumps(out, indent=2)
)
print(out)
