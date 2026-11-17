"""Build one explicit, immutable factor profile; no score-driven parameter search."""

import argparse, os
from workspace import ROOT, owned, atomic_json, digest
from preflight import SPECS, load


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument(
        "--variant",
        choices=["default-body150", "cellheight005", "climb030", "cellheight005-climb030"],
    )
    p.add_argument("--cell-height", type=float)
    p.add_argument("--max-climb", type=float)
    p.add_argument("--gpu", type=int, required=True)
    a = p.parse_args()
    if not os.environ.get("CASE1_PROTECTION"):
        raise SystemExit("Use protected runtime")
    if not a.name or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in a.name
    ):
        raise ValueError("Unsafe immutable profile name")
    variant = a.variant or a.name
    allowed = {
        "default-body150": (None, None),
        "cellheight005": (0.05, None),
        "climb030": (None, 0.30),
        "cellheight005-climb030": (0.05, 0.30),
    }
    if variant not in allowed or (a.cell_height, a.max_climb) != allowed[variant]:
        raise ValueError("Name/parameter mismatch")
    from evaluate import free_gpus

    if a.gpu not in free_gpus():
        raise RuntimeError("GPU is not idle")
    os.environ["CUDA_VISIBLE_DEVICES"] = str(a.gpu)
    import habitat_sim

    output = owned(ROOT / "data/derived/navmeshes" / a.name)
    if output.exists():
        raise ValueError("Immutable profile already exists")
    output.mkdir(parents=True)
    scenes = set()
    for ds, (directory, anno, gt_name, count) in SPECS.items():
        episodes = load(ROOT / "data/datasets" / directory / "val_unseen" / anno)["episodes"]
        scenes.update(
            e["scene_id"]
            for e in episodes
            if ds != "rxr" or e["instruction"]["language"] == "en-US"
        )
    profile = {
        "schema_version": 1,
        "profile_id": a.name,
        "variant": variant,
        "simulator_version": habitat_sim.__version__,
        "agent": {"height": 1.5, "radius": 0.1},
        "assets": {},
        "status": "BUILT_PENDING_STATIC_AND_MOTION_VALIDATION",
        "construction_reason": "Isolate voxel-height discretization and explicit 0.30m climb historical candidate; no navigation-score selection.",
        "construction_renderer": {
            "resolution": [16, 16],
            "position": [0, 1.25, 0],
            "purpose": "Geometry loading for Habitat-Sim 0.1.7 only; not a model observation",
        },
    }
    for scene_id in sorted(scenes):
        scene = ROOT / "data/scene_datasets" / scene_id
        original = scene.with_suffix(".navmesh")
        mesh = original
        settings_values = None
        if scene.stem == "oLBMNvg9in8":
            sc = habitat_sim.SimulatorConfiguration()
            sc.scene_id = str(scene)
            sc.create_renderer = True
            sc.enable_physics = False
            sc.gpu_device_id = 0
            agent = habitat_sim.agent.AgentConfiguration()
            agent.height = 1.5
            agent.radius = 0.1
            sensor = (
                habitat_sim.CameraSensorSpec()
                if hasattr(habitat_sim, "CameraSensorSpec")
                else habitat_sim.SensorSpec()
            )
            sensor.uuid = "build_rgb"
            sensor.sensor_type = habitat_sim.SensorType.COLOR
            sensor.resolution = [16, 16]
            sensor.position = [0.0, 1.25, 0.0]
            agent.sensor_specifications = [sensor]
            sim = habitat_sim.Simulator(habitat_sim.Configuration(sc, [agent]))
            try:
                settings = habitat_sim.NavMeshSettings()
                settings.set_defaults()
                settings.agent_height = 1.5
                settings.agent_radius = 0.1
                if a.cell_height is not None:
                    settings.cell_height = a.cell_height
                if a.max_climb is not None:
                    settings.agent_max_climb = a.max_climb
                settings_values = {
                    n: getattr(settings, n)
                    for n in dir(settings)
                    if not n.startswith("_")
                    and isinstance(getattr(settings, n), (float, int, bool))
                }
                mesh = output / (scene.stem + ".navmesh")
                if not sim.recompute_navmesh(sim.pathfinder, settings):
                    raise RuntimeError("Recompute failed")
                if not sim.pathfinder.save_nav_mesh(str(mesh)):
                    raise RuntimeError("Save failed")
            finally:
                sim.close()
        profile["assets"][scene_id] = {
            "scene_path": str(scene),
            "scene_sha256": digest(scene),
            "original_navmesh_sha256": digest(original),
            "navmesh_path": str(mesh),
            "navmesh_sha256": digest(mesh),
            "build_settings": settings_values,
        }
    atomic_json(output / "profile.json", profile)
    print(str(output / "profile.json"))


if __name__ == "__main__":
    main()
