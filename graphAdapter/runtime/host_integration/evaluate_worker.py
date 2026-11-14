"""Launch the official trainer from tracked src, never upstream or an archive."""

import argparse, os, random, json, datetime, time
from pathlib import Path


def main():
    from case1_runtime.observations import resolve_graph_hook_switch
    _, switch_resolution = resolve_graph_hook_switch(os.environ)
    os.environ['CASE2_SWITCH_PREFLIGHT_AUDIT'] = json.dumps(switch_resolution)
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    start_clock = time.monotonic()
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", choices=["r2r", "rxr"], required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--scenes", required=True)
    p.add_argument("--chunk", type=int, required=True)
    p.add_argument("--chunks", type=int, required=True)
    p.add_argument("--ids", required=True)
    p.add_argument("--dataset-spec", help="Frozen copied annotation and GT identity for checkpoint-choice evaluation")
    a = p.parse_args()
    if not os.environ.get("CASE1_PROTECTION"):
        raise SystemExit("Protected runtime required")
    protection = json.loads(os.environ["CASE1_PROTECTION"])
    if protection.get("results_write") or protection.get("prepare_configs"):
        raise SystemExit("Administrative write permissions cannot be used for model workers")
    launch_manifest=json.loads((Path(os.environ["CASE1_RUN_ROOT"])/"run_manifest.json").read_text())
    if launch_manifest.get("stage") in {"000","001"} or os.environ.get("CASE2_STAGE000") or os.environ.get("CASE2_MAP_MEMORY") == "1":
        from case1_runtime.scene_assets import verify_worker_scenes
        verify_worker_scenes(os.environ["AWAREVLN_ROOT"],os.environ["CASE1_RUN_ROOT"],a.scenes)
    if launch_manifest.get('pose_sampling')=='release4_12'and os.environ.get('CASE2_HOOK_MODE')=='on':
        import poseAdapter
        from graphAdapter.observation_pose.production import verify_package
        verify_package(launch_manifest['pose_package'],actual_import=True)
    from hamlet_v2.policy import bind_worker
    bind_worker(os.environ["AWAREVLN_ROOT"], os.environ["CASE1_RUN_ROOT"])
    import numpy as np, torch
    if os.environ.get("CASE1_TORCH_BUDGET_MIB"):
        torch_budget=int(os.environ["CASE1_TORCH_BUDGET_MIB"])
        total_budget=int(os.environ["CASE1_GPU_TOTAL_BUDGET_MIB"])
        if (torch_budget,total_budget)!=(22528,24576):raise ValueError("Unexpected shared GPU budget")
        torch.cuda.set_per_process_memory_fraction(torch_budget*1024**2/torch.cuda.get_device_properties(0).total_memory,0)
    from vlnce_baselines.config.default import get_config
    from habitat_baselines.common.baseline_registry import baseline_registry
    from habitat import logger

    root = Path(os.environ["AWAREVLN_ROOT"]).resolve()
    out = Path(a.output).resolve()
    if root / "outputs" not in out.parents:
        raise ValueError("Worker output outside outputs")
    if os.environ.get('CASE2_STORAGE_BINDING'):
        from graphAdapter.map_memory.storage.routing import from_environment,create_process_scope,bind_process_scope
        from graphAdapter.map_memory.storage.lifecycle import process_identity
        route=from_environment();create_process_scope(route.root,out,'host_output')
        bind_process_scope(route.root,out,process_identity(os.getpid()))
    else:out.mkdir(parents=True, exist_ok=False)
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
    if a.dataset_spec:
        from workspace import digest
        spec_path=Path(a.dataset_spec).resolve()
        run=Path(os.environ["CASE1_RUN_ROOT"]).resolve()
        if spec_path.parent!=run:raise ValueError("Dataset binding must belong to this run")
        manifest=json.loads((run/"run_manifest.json").read_text())
        if digest(spec_path)!=manifest["dataset_spec_sha256"]:raise ValueError("Dataset spec drift")
        spec=json.loads(spec_path.read_text())
        for key in ("annotation","gt"):
            if digest(spec[key])!=spec[key+"_sha256"]:raise ValueError("Dataset input drift")
        config.TASK_CONFIG.DATASET.DATA_PATH=spec["annotation"]
        config.TASK_CONFIG.TASK.NDTW.GT_PATH=spec["gt"]
        if a.chunks!=1 or a.chunk!=0:raise ValueError("Fixed selected IDs require unchunked source reader")
        import inspect
        import vlnce_baselines.awarevln_trainer as loaded_trainer
        from habitat_extensions import task as loaded_dataset
        modules={"worker":str(Path(__file__).resolve()),"trainer":str(Path(inspect.getfile(loaded_trainer)).resolve()),"dataset":str(Path(inspect.getfile(loaded_dataset)).resolve())}
        frozen={f["path"]:f["sha256"] for f in manifest["frozen_files"]}
        for path in modules.values():
            if path not in frozen or digest(path)!=frozen[path]:raise ValueError("Actual worker import is not frozen source: "+path)
        (out/"launch-binding.json").write_text(json.dumps({"modules":{k:{"path":v,"sha256":digest(v)} for k,v in modules.items()},"manifest_sha256":digest(run/"run_manifest.json"),"dataset_spec_sha256":digest(spec_path),"ids_sha256":digest(a.ids),"chunks":a.chunks,"chunk":a.chunk,"resource_budget":manifest.get("resource_budget"),"torch_allocator_budget_mib":os.environ.get("CASE1_TORCH_BUDGET_MIB")},indent=2))
    if os.environ.get("CASE2_STAGE000") or os.environ.get("CASE2_POSE_PROFILE"):
        config.TASK_CONFIG.ENVIRONMENT.ITERATOR_OPTIONS.GROUP_BY_SCENE = False
    if os.environ.get("CASE2_HOOK_MODE")=="off" and (os.environ.get("CASE2_POSE_PROFILE") or os.environ.get("POSEADAPTER_BROKER") or os.environ.get("GRAPH_MEMORY_BROKER")):
        raise RuntimeError("No-hook worker received hook configuration/broker")
    if os.environ.get("CASE2_MAP_MEMORY")=="1":
        if tuple(config.RL.POLICY.OBS_TRANSFORMS.ENABLED_TRANSFORMS):
            raise RuntimeError("001 identity host-view profile cannot omit enabled observation transforms")
        (out/"host-transform.json").write_text(json.dumps(dict(kind="identity",enabled_transforms=[],
            source="actual common-host config;rawRGB=batchRGB before unchanged model visual processor"),indent=2))
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
