import os, json, math, hashlib, argparse

os.environ["CUDA_VISIBLE_DEVICES"] = ""
from pathlib import Path
import habitat_sim
from habitat_sim.utils.common import quat_from_coeffs

parser = argparse.ArgumentParser()
parser.add_argument("--motion-dir", required=True)
parser.add_argument("--profile", required=True)
a = parser.parse_args()
from workspace import ROOT, owned, digest, atomic_json
from preflight import dataset_base

if not os.environ.get("CASE1_PROTECTION"):
    raise RuntimeError("Use protected runtime")
root = ROOT
directory = owned(a.motion_dir)
audit = json.loads((directory / "motion-audit.json").read_text())
profile = json.loads(Path(a.profile).read_text())
assert digest(a.profile) == audit["profile_sha256"]

import gzip

with gzip.open(dataset_base("rxr") / "val_unseen_guide.json.gz", "rt") as f:
    raw = json.load(f)["episodes"]
episodes = {str(e["episode_id"]): e for e in raw}
results = []
sc = habitat_sim.SimulatorConfiguration()
sc.scene_id = "NONE"
sc.create_renderer = False
sc.enable_physics = False
agent = habitat_sim.agent.AgentConfiguration()
agent.height = 1.5
agent.radius = 0.1
agent.sensor_specifications = []
agent.action_space = {
    1: habitat_sim.agent.ActionSpec(
        "move_forward", habitat_sim.agent.ActuationSpec(amount=0.25)
    ),
    2: habitat_sim.agent.ActionSpec(
        "turn_left", habitat_sim.agent.ActuationSpec(amount=15)
    ),
    3: habitat_sim.agent.ActionSpec(
        "turn_right", habitat_sim.agent.ActuationSpec(amount=15)
    ),
}
sim = habitat_sim.Simulator(habitat_sim.Configuration(sc, [agent]))
try:
    for task in audit["tasks"]:
        eid = task["episode_id"]
        ep = episodes[eid]
        trace_path = directory / eid / "motion.json"
        trace = json.loads(trace_path.read_text())
        mesh = profile["assets"][ep["scene_id"]]["navmesh_path"]
        assert sim.pathfinder.load_nav_mesh(mesh)
        state = habitat_sim.AgentState()
        state.position = ep["start_position"]
        state.rotation = quat_from_coeffs(ep["start_rotation"])
        sim.initialize_agent(0, state)
        errors = [
            math.dist(
                list(sim.get_agent(0).get_state().position), trace["positions"][0]
            )
        ]
        for i, action in enumerate(trace["actions"]):
            if action != 0:
                sim.step(action)
            errors.append(
                math.dist(
                    list(sim.get_agent(0).get_state().position),
                    trace["positions"][i + 1],
                )
            )
        max_vertical = max(
            (
                abs(b[1] - a[1])
                for a, b in zip(trace["positions"], trace["positions"][1:])
            ),
            default=0,
        )
        all_finite = all(
            math.isfinite(v) for point in trace["positions"] for v in point
        )
        results.append(
            {
                "max_vertical_displacement_m": max_vertical,
                "no_cross_floor_jump": max_vertical <= 0.5,
                "all_positions_finite": all_finite,
                "episode_id": eid,
                "steps": len(trace["actions"]),
                "max_position_error_m": max(errors),
                "matches": max(errors) < 1e-5,
                "trace_sha256": hashlib.sha256(trace_path.read_bytes()).hexdigest(),
            }
        )
finally:
    sim.close()
result = {
    "scope": "CPU native action replay against recorded RGB environment trajectories; no policy inference",
    "profile_sha256": audit["profile_sha256"],
    "tasks": results,
    "status": (
        "PASS"
        if all(
            x["matches"] and x["no_cross_floor_jump"] and x["all_positions_finite"]
            for x in results
        )
        else "FAIL"
    ),
    "motion_audit_sha256": digest(directory / "motion-audit.json"),
    "method": "native_action_replay_same_profile_v1",
}
atomic_json(directory / "motion-replay.json", result)
print(
    {
        "status": result["status"],
        "episodes": len(results),
        "max_error": max(x["max_position_error_m"] for x in results),
    }
)
