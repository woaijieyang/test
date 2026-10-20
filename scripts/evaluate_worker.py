"""Launch the official trainer from tracked src, never upstream or an archive."""

import argparse, os, random, json, datetime, time
from pathlib import Path


def main():
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    start_clock = time.monotonic()
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", choices=["r2r", "rxr"], required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--scenes", required=True)
    p.add_argument("--chunk", type=int, required=True)
    p.add_argument("--chunks", type=int, required=True)
    p.add_argument("--ids", required=True)
    a = p.parse_args()
    if not os.environ.get("CASE1_PROTECTION"):
        raise SystemExit("Protected runtime required")
    protection = json.loads(os.environ["CASE1_PROTECTION"])
    if protection.get("results_write") or protection.get("prepare_configs"):
        raise SystemExit("Administrative write permissions cannot be used for model workers")
    import numpy as np, torch
    from vlnce_baselines.config.default import get_config
    from habitat_baselines.common.baseline_registry import baseline_registry
    from habitat import logger

    root = Path(os.environ["AWAREVLN_ROOT"]).resolve()
    out = Path(a.output).resolve()
    if root / "outputs" not in out.parents:
        raise ValueError("Worker output outside outputs")
    out.mkdir(parents=True, exist_ok=False)
    config = get_config(
        str(root / "configs/vlnce_baselines/config" / f"{a.dataset}_baselines/awarevln.yaml")
    )
    config.defrost()
    config.EVAL_CKPT_PATH_DIR = str(root / "models/awarevln")
    config.RESULTS_DIR = str(out / "native")
    config.LOG_FILE = str(out / "native.log")
    config.TENSORBOARD_DIR = str(out / "tensorboard")
    config.VIDEO_OPTION = []
    config.TASK_CONFIG.DATASET.SCENES_DIR = a.scenes
    config.TASK_CONFIG.DATASET.EPISODES_ALLOWED = json.loads(Path(a.ids).read_text())
    # Official policy consumes instruction text and RGB only. Oracle observation
    # sensors are unused and RxR lacks their required geodesic_distance field.
    # Both datasets provide the original instruction on current_episodes().
    # RxR has no numeric instruction tokens; batching this unused None fails.
    config.TASK_CONFIG.TASK.SENSORS = []
    from preflight import configure_dataset
    configure_dataset(config,a.dataset)
    config.freeze()
    (out / "launch-config.yaml").write_text(str(config))
    logger.add_filehandler(config.LOG_FILE)
    if (
        config.TASK_CONFIG.SIMULATOR.AGENT_0.HEIGHT != 1.5
        or config.TASK_CONFIG.SIMULATOR.AGENT_0.RADIUS != 0.1
    ):
        raise ValueError("Native robot dimensions differ from accepted profile")
    if (
        config.TASK_CONFIG.SIMULATOR.FORWARD_STEP_SIZE != 0.25
        or config.TASK_CONFIG.SIMULATOR.TURN_ANGLE != 15
        or config.TASK_CONFIG.ENVIRONMENT.MAX_EPISODE_STEPS != 500
    ):
        raise ValueError("Official action/budget contract changed")
    random.seed(config.TASK_CONFIG.SEED)
    np.random.seed(config.TASK_CONFIG.SEED)
    torch.manual_seed(config.TASK_CONFIG.SEED)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.set_num_threads(1)
    os.environ["CASE1_TRACE_ROOT"] = str(out)
    os.environ["CASE1_DATASET"] = a.dataset
    trainer = baseline_registry.get_trainer(config.TRAINER_NAME)(config, a.chunks, a.chunk)
    trainer.eval()
    (out / "worker-done.json").write_text(
        json.dumps(
            {
                "started_at": started_at,
                "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "elapsed_seconds": time.monotonic() - start_clock,
                "pid": os.getpid(),
                "cpu_affinity": sorted(os.sched_getaffinity(0)),
                "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
                "status": "execution_complete_pending_audit",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
