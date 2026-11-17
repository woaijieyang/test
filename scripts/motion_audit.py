"""Evaluator-only shortest-path motion diagnostic; never a model navigation score."""

import argparse, math, os
from workspace import ROOT, owned, atomic_json, read_json, digest
from evaluate import scene_view



def motion_violations(positions, actions, step=0.25, climb=0.30, slope_degrees=45):
    if len(positions)!=len(actions)+1:
        raise ValueError('Movement trace has incomplete endpoints')
    violations=[]
    for i,action in enumerate(actions):
        before,after=positions[i:i+2]
        horizontal=math.hypot(after[0]-before[0],after[2]-before[2])
        vertical=abs(after[1]-before[1])
        max_horizontal=step if action==1 else 0.0
        max_vertical=climb+step*math.tan(math.radians(slope_degrees)) if action==1 else 0.0
        if horizontal>max_horizontal+1e-4 or vertical>max_vertical+1e-4:
            violations.append({'step':i,'action':action,'horizontal_m':horizontal,'vertical_m':vertical})
    return violations


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--profile", required=True)
    p.add_argument("--episode-ids", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--gpu", type=int, required=True)
    a = p.parse_args()
    if not os.environ.get("CASE1_PROTECTION"):
        raise SystemExit("Protected runtime required")
    from evaluate import free_gpus

    if a.gpu not in free_gpus():
        raise RuntimeError("Requested GPU is not idle")
    os.environ["CUDA_VISIBLE_DEVICES"] = str(a.gpu)
    import habitat
    import importlib

    importlib.import_module("habitat_extensions")  # Register the official task and measures.
    from habitat.tasks.nav.shortest_path_follower import ShortestPathFollower
    from vlnce_baselines.config.default import get_config
    from PIL import Image
    from case1_runtime.trace import safe

    output = owned(a.output)
    output.mkdir(parents=True, exist_ok=False)
    ids = [str(x) for x in read_json(a.episode_ids)]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate diagnostic IDs")
    profile = read_json(a.profile)
    scenes = scene_view(profile)
    config = get_config(str(ROOT / "configs/vlnce_baselines/config/rxr_baselines/awarevln.yaml"))
    config.defrost()
    config.TASK_CONFIG.DATASET.NUM_CHUNKS = 1
    config.TASK_CONFIG.DATASET.CHUNK_IDX = 0
    config.TASK_CONFIG.DATASET.SPLIT = "val_unseen"
    config.TASK_CONFIG.DATASET.EPISODES_ALLOWED = ids
    config.TASK_CONFIG.DATASET.SCENES_DIR = str(scenes)
    config.TASK_CONFIG.DATASET.LANGUAGES = ["en-US"]
    config.TASK_CONFIG.DATASET.ROLES = ["guide"]
    config.TASK_CONFIG.TASK.NDTW.SPLIT = "val_unseen"
    config.TASK_CONFIG.ENVIRONMENT.ITERATOR_OPTIONS.SHUFFLE = False
    # Official policy consumes instruction text and RGB only. Oracle observation
    # sensors are unused and RxR lacks their required geodesic_distance field.
    config.TASK_CONFIG.TASK.SENSORS = ["INSTRUCTION_SENSOR"]
    from preflight import configure_dataset
    configure_dataset(config,'rxr')
    config.freeze()
    (output / "effective-config.yaml").write_text(str(config))
    reports = []
    env = habitat.Env(config=config.TASK_CONFIG)
    try:
        for _ in range(len(ids)):
            observations = env.reset()
            ep = env.current_episode
            goal = ep.goals[0].position
            follower = ShortestPathFollower(env.sim, 0.5, False)
            directory = output / str(ep.episode_id)
            directory.mkdir()
            positions = [env.sim.get_agent_state().position.tolist()]
            reset_error=math.dist(positions[0],ep.start_position)
            actions = []
            distances = []
            while not env.episode_over:
                dist = float(env.sim.geodesic_distance(positions[-1], goal))
                distances.append(dist if math.isfinite(dist) else None)
                if not math.isfinite(dist):
                    break
                action = follower.get_next_action(goal)
                if action is None:
                    raise RuntimeError("Follower cannot provide action")
                if len(actions) % 10 == 0:
                    Image.fromarray(observations["rgb"]).save(
                        directory / (str(len(actions)).zfill(4) + ".png")
                    )
                observations = env.step(int(action))
                actions.append(int(action))
                positions.append(env.sim.get_agent_state().position.tolist())
            metrics = env.get_metrics()
            success = bool(metrics.get("success", False))
            violations=motion_violations(positions,actions)
            atomic_json(
                directory / "motion.json",
                {
                    "episode_id": str(ep.episode_id),
                    "positions": positions,
                    "actions": actions,
                    "distances_before_actions": distances,
                    "native_metrics": safe(metrics),
                    "success": success,
                    "reset_position_error_m": reset_error,
                    "nominal_step_deviations": violations,
                },
            )
            reports.append(
                {
                    "episode_id": str(ep.episode_id),
                    "steps": len(actions),
                    "success": success,
                    "reset_position_error_m": reset_error,
                    "nominal_step_deviations": violations,
                    "all_distances_finite": all(x is not None for x in distances),
                    "motion_sha256": digest(directory / "motion.json"),
                }
            )
    finally:
        env.close()
    accepted = (
        len(reports) == len(ids)
        and {r["episode_id"] for r in reports} == set(ids)
        and all(r["success"] and r["all_distances_finite"] and r["reset_position_error_m"]<=1e-4  for r in reports)
    )
    atomic_json(
        output / "motion-audit.json",
        {
            "claim_scope": "oracle_motion_diagnostic_not_model_navigation",
            "profile_sha256": digest(a.profile),
            "status": "EXECUTION_COMPLETE_PENDING_REPLAY" if accepted else "FAIL",
            "tasks": reports,
        },
    )
    if not accepted:
        raise SystemExit("Motion diagnostic failed")
    print({"status": "EXECUTION_COMPLETE_PENDING_REPLAY", "diagnostic_tasks": len(reports)})


if __name__ == "__main__":
    main()
