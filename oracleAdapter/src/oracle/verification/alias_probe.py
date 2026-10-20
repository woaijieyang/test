"""Fresh native transitions and rational positive-contact checks for old aliases."""
from dataclasses import asdict
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import time

from oracle.adapters.habitat.native import NativeAdapter, NativeState
from oracle.common.identity import Context, exact_state_key
from oracle.contracts import MotionContract
from oracle.verification.source_scene import SourceScene


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(case_root, config, package_root, output):
    root, package_root, output = map(lambda p: Path(p).resolve(), (case_root, package_root, output))
    if not output.is_relative_to(root / "outputs/oracleAdapter"):
        raise ValueError("Output escaped research root")
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    archive = root / config["historical_receipt"]
    if digest(archive) != config["historical_receipt_sha256"]:
        raise RuntimeError("Historical alias evidence changed")
    old = json.loads(archive.read_text())
    profile_path = root / config["profile"]
    if digest(profile_path) != config["profile_sha256"] or old["profile_sha256"] != config["profile_sha256"]:
        raise RuntimeError("Alias profile mismatch")
    profile = json.loads(profile_path.read_text())
    asset = profile["assets"][f"mp3d/{config['scene']}/{config['scene']}.glb"]
    protocol_path = package_root / config["source_protocol_config"]
    protocol = json.loads(protocol_path.read_text())
    motion = MotionContract(**{k: protocol[k] for k in MotionContract.__dataclass_fields__})
    if profile["agent"] != {"height": motion.body_height_m, "radius": motion.body_radius_m}:
        raise RuntimeError("Body contract differs from profile")
    catalog_path = root / config["geometry_catalog"]
    catalog = json.loads(catalog_path.read_text())
    geometry = next(r for r in catalog["scenes"] if r["scene"] == config["scene"])
    # Historical Landmark profiles bind navmeshes, while their scene identity
    # is bound by the native-loader catalog. Do not assume the formal-model
    # profile schema (scene_path/scene_sha256) also exists in this profile.
    scene_path = root / "data/scene_datasets/mp3d" / config["scene"] / (config["scene"] + ".glb")
    if digest(scene_path) != geometry["scene_sha256"]:
        raise RuntimeError("Original scene identity changed")
    source = SourceScene(geometry["receipt_path"], geometry["receipt_sha256"], protocol, catalog=geometry)
    if source.scene_sha256 != geometry["scene_sha256"]:
        raise RuntimeError("Geometry does not belong to the profiled scene")
    adapter = NativeAdapter(asset["navmesh_path"], asset["navmesh_sha256"], motion)
    replay = NativeAdapter(asset["navmesh_path"], asset["navmesh_sha256"], motion)
    import habitat_sim
    env = {"habitat_sim_version": habitat_sim.__version__, "module_path": inspect.getfile(habitat_sim),
           "body_action_contract": asdict(motion), "scene_sha256": source.scene_sha256,
           "navmesh_sha256": asset["navmesh_sha256"], "source_geometry_sha256": source.geometry_sha256}
    (output / "native_environment.json").write_text(json.dumps(env, indent=2))
    context = Context(source.scene_sha256, config["profile_sha256"],
                      hashlib.sha256(json.dumps(asdict(motion), sort_keys=True).encode()).hexdigest(),
                      digest(archive), digest(protocol_path), digest(__file__),
                      hashlib.sha256(json.dumps(env, sort_keys=True).encode()).hexdigest(), "native_xyz_quaternion_xyzw")
    records = []
    try:
        for row in old["records"]:
            prefix_path = Path(row["prefix_path"])
            if not prefix_path.resolve().is_relative_to(root) or digest(prefix_path) != row["prefix_sha256"]:
                raise RuntimeError("Archived executed prefix changed")
            prefix = json.loads(prefix_path.read_text())
            target = prefix["targets"][len(prefix["boundaries"]) + 1]
            for pair_index, pair in enumerate(row["divergent_forward_legality"]):
                if time.perf_counter() - started > config["max_wall_seconds"]:
                    raise RuntimeError("Predeclared probe wall budget exhausted")
                probes = []
                keys = []
                for label in ("retained", "pruned"):
                    w, x, y, z = pair[label + "_rotation"]
                    state = NativeState(tuple(pair[label + "_position"]), (x, y, z, w))
                    yaw = (2 * math.atan2(y, w)) % (2 * math.pi)
                    legacy_key = [round(v * 100) for v in state.position] + [round(yaw * 1800 / math.pi) % 3600]
                    if legacy_key != pair["key"]:
                        raise RuntimeError("Quaternion convention or legacy key differs")
                    keys.append(exact_state_key(state.key_values(), 0, context))
                    adapter.restore(state)
                    start = adapter.snapshot()
                    actual = adapter.step(config["native_action"])
                    replay.restore(state)
                    replayed = replay.step(config["native_action"])
                    error = math.dist(actual.position, replayed.position)
                    if error != 0.:
                        raise RuntimeError("Native one-step replay differs")
                    horizontal = math.hypot(actual.position[0] - start.position[0], actual.position[2] - start.position[2])
                    vertical = abs(actual.position[1] - start.position[1])
                    distance = adapter.geodesic_distance(actual.position, target)
                    native_ok = (adapter.is_navigable(actual.position)
                                 and horizontal <= motion.forward_m + protocol["horizontal_tolerance_m"]
                                 and vertical <= protocol["maximum_vertical_transition_m"]
                                 and math.dist(start.position, actual.position) >= 1e-5
                                 and math.isfinite(distance))
                    contact = source.contact(start.position, actual.position, certificate=True)
                    probes.append({"label": label, "input_state": asdict(state),
                                   "actual_initial_state": asdict(start), "actual_next_state": asdict(actual),
                                   "old_sampled_legal": pair[label + "_forward_legal"],
                                   "current_native_gate": native_ok, "current_exact_contact": contact,
                                   "current_exact_legal": native_ok and contact is None,
                                   "replay_error": error, "horizontal_m": horizontal, "vertical_m": vertical})
                if keys[0] == keys[1]:
                    raise RuntimeError("Lossless state key still aliases distinct states")
                records.append({"task_key": row["task_key"], "pair_index": pair_index,
                                "legacy_same_key": pair["key"], "lossless_keys_distinct": True,
                                "current_forward_legality_diverges": probes[0]["current_exact_legal"] != probes[1]["current_exact_legal"],
                                "probes": probes})
        total_calls = adapter.native_calls + replay.native_calls
        if len(records) != config["expected_pairs"] or total_calls > config["max_native_calls"]:
            raise RuntimeError("Probe coverage/budget mismatch")
        summary = {"status": "COMPLETE_NATIVE_ALIAS_RECHECK_NOT_ROUTE_ACCEPTANCE", "pairs": len(records),
                   "native_calls_including_replay": total_calls,
                   "current_strict_divergent_pairs": sum(r["current_forward_legality_diverges"] for r in records),
                   "all_lossless_keys_distinct": True, "records": records,
                   "source_queries": source.queries, "triangle_checks": source.triangle_checks,
                   "wall_seconds": time.perf_counter() - started,
                   "historical_receipt_sha256": digest(archive), "profile_sha256": digest(profile_path),
                   "catalog_sha256": digest(catalog_path), "script_sha256": digest(__file__),
                   "limits": "Initializations are explicit isolated counterexample probes, not uninterrupted routes. Oldsampled/trimesh andcurrentexact/native-source predicates differ; no route gain is inferred. Rational positivecontact certificates do not establish physical model correctness or independent no-contact proof."}
        (output / "validation.json").write_text(json.dumps(summary, indent=2))
        return summary
    finally:
        adapter.close()
        replay.close()
