"""Build only the explicitly authorized nine-episode derivative; prove every difference."""

import copy, gzip, io, json, os, math
from workspace import ROOT, atomic_json, digest
from preflight import load


def diff(before, after, path=""):
    if (
        isinstance(before, float)
        and isinstance(after, float)
        and math.isnan(before)
        and math.isnan(after)
    ):
        return []
    if type(before) != type(after):
        return [{"field": path, "before": before, "after": after}]
    if isinstance(before, dict):
        if set(before) != set(after):
            raise ValueError("Dictionary keys changed")
        return [
            r for k in before for r in diff(before[k], after[k], path + "/" + str(k))
        ]
    if isinstance(before, list):
        if len(before) != len(after):
            raise ValueError("Array length changed")
        return [
            r
            for i, (a, b) in enumerate(zip(before, after))
            for r in diff(a, b, path + "/" + str(i))
        ]
    return (
        [] if before == after else [{"field": path, "before": before, "after": after}]
    )


def compressed(path, data):
    payload = json.dumps(
        data, ensure_ascii=False, separators=(",", ":"), allow_nan=True
    ).encode()
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as f:
        f.write(payload)
    if path.exists():
        if path.read_bytes() != buffer.getvalue():
            raise RuntimeError("Immutable derived artifact mismatch")
    else:
        path.write_bytes(buffer.getvalue())


def main():
    if not os.environ.get("CASE1_PROTECTION"):
        raise RuntimeError("Use protected runtime")
    cfg = json.loads((ROOT / "configs/annotation-protocol.json").read_text())
    source = ROOT / "data/datasets/RxR_VLNCE_v0/val_unseen"
    out = ROOT / cfg["dataset_roots"]["rxr"] / "val_unseen"
    if (ROOT / "data/derived") not in out.resolve().parents:
        raise RuntimeError("Derivative escapes owned root")
    out.mkdir(parents=True, exist_ok=True)
    inputs = {
        n: digest(source / n)
        for n in (
            "val_unseen_guide.json.gz",
            "val_unseen_guide_gt.json.gz",
            "val_unseen_follower_gt.json.gz",
        )
    }
    original = load(source / "val_unseen_guide.json.gz")
    annotations = copy.deepcopy(original)
    gt_before = load(source / "val_unseen_guide_gt.json.gz")
    gt = copy.deepcopy(gt_before)
    starts = set(cfg["start_episode_ids"])
    goals = set(cfg["goal_episode_ids"])
    all_ids = starts | goals
    if len(all_ids) != 9 or starts & goals:
        raise ValueError("Unexpected authorized scope")
    changes = []
    seen = set()
    for index, (before, after) in enumerate(
        zip(original["episodes"], annotations["episodes"])
    ):
        eid = str(before["episode_id"])
        if eid in all_ids:
            assert (
                before["instruction"]["language"] == "en-US"
                and before["scene_id"] == cfg["scene_id"]
            )
            seen.add(eid)
            if eid in starts:
                assert before["start_position"] == cfg["old_position"]
                after["start_position"] = cfg["new_position"][:]
            if eid in goals:
                assert (
                    len(before["goals"]) == 1
                    and before["goals"][0]["position"] == cfg["old_position"]
                )
                after["goals"][0]["position"] = cfg["new_position"][:]
            # Preserve the reference path, changing only exact occurrences of this same
            # corrected physical node within the explicitly authorized episodes.
            for i, position in enumerate(after.get("reference_path", [])):
                if position == cfg["old_position"]:
                    after["reference_path"][i] = cfg["new_position"][:]
            if eid in starts:
                assert gt[eid]["locations"][0] == cfg["old_position"]
                gt[eid]["locations"][0] = cfg["new_position"][:]
        delta = diff(before, after)
        if delta:
            if eid not in all_ids:
                raise ValueError("Unapproved episode modification")
            changes.append(
                {
                    "episode_id": eid,
                    "instruction_id": before["instruction"]["instruction_id"],
                    "roles": ["start"] if eid in starts else ["goal"],
                    "annotation_changes": delta,
                    "gt_changes": diff(gt_before[eid], gt[eid]),
                }
            )
    assert seen == all_ids and {r["episode_id"] for r in changes} == all_ids
    gt_changed = {k for k in gt if gt[k] != gt_before[k]}
    assert gt_changed == starts
    for name, data in [
        ("val_unseen_guide.json.gz", annotations),
        ("val_unseen_guide_gt.json.gz", gt),
    ]:
        compressed(out / name, data)
    follower = out / "val_unseen_follower_gt.json.gz"
    target = source / "val_unseen_follower_gt.json.gz"
    if follower.is_symlink():
        assert follower.resolve() == target.resolve()
    elif follower.exists():
        raise RuntimeError("Unexpected follower entity")
    else:
        follower.symlink_to(target.resolve())
    assert inputs == {n: digest(source / n) for n in inputs}, "Original inputs changed"
    receipt = {
        "protocol_id": cfg["protocol_id"],
        "source_files": [
            {"path": str((source / n).resolve()), "sha256": sha}
            for n, sha in inputs.items()
        ],
        "derived_files": [
            {"path": str(out / n), "sha256": digest(out / n)} for n in inputs
        ],
        "protocol_sha256": digest(ROOT / "configs/annotation-protocol.json"),
        "all_guide_episodes": len(annotations["episodes"]),
        "en_us_episodes": sum(
            e["instruction"]["language"] == "en-US" for e in annotations["episodes"]
        ),
        "changed_episodes": len(changes),
        "changed_gt_records": len(gt_changed),
        "all_other_episode_and_gt_values_identical": True,
        "changes": changes,
        "status": "DIFFERENCE_VALIDATED_PENDING_RUNTIME",
    }
    atomic_json(out.parent / "manifest.json", receipt)
    atomic_json(ROOT / "outputs/preflight/derived-annotation-diff.json", receipt)
    if json.loads(os.environ["CASE1_PROTECTION"]).get("prepare_configs"):
        atomic_json(ROOT / "configs/diagnostics/annotation-diff.json", receipt)
    print(
        {
            "changed_episodes": len(changes),
            "changed_gt_records": len(gt_changed),
            "others_unchanged": True,
        }
    )


if __name__ == "__main__":
    main()
