from typing import Any, Dict, Optional, Tuple

import os
import habitat
from case1_runtime.observations import graph_hook_enabled, native_subframes_enabled
from habitat import Config, Dataset
from habitat.core.simulator import Observations
from habitat_baselines.common.baseline_registry import baseline_registry


@baseline_registry.register_env(name="VLNCEDaggerEnv")
class VLNCEDaggerEnv(habitat.RLEnv):
    def __init__(self, config: Config, dataset: Optional[Dataset] = None):
        super().__init__(config.TASK_CONFIG, dataset)
        self._graph_execution_spec = {
            "forward_step_m": float(config.TASK_CONFIG.SIMULATOR.FORWARD_STEP_SIZE),
            "turn_degrees": float(config.TASK_CONFIG.SIMULATOR.TURN_ANGLE),
            "max_episode_steps": int(config.TASK_CONFIG.ENVIRONMENT.MAX_EPISODE_STEPS),
        }


    def reset(self,*args,**kwargs):
        if hasattr(self,'_graph_pose_generation'):
            from SimulatorAdapter.host_bridge import invalidate_pose_binding
            invalidate_pose_binding(self)
        return super().reset(*args,**kwargs)

    def graph_pose_state(self,expected_episode_uid,profile_sha256,pose_session):
        if not graph_hook_enabled(os.environ):
            return dict(episode_uid=expected_episode_uid,pose_error='profile_rejected')
        # Delegate pose-only acquisition; no truth fields are read in this host module.
        from SimulatorAdapter.host_bridge import pose_rpc_reply
        return pose_rpc_reply(self,expected_episode_uid=expected_episode_uid,profile_sha256=profile_sha256,pose_session=pose_session)

    def graph_static_sensor_spec(self):
        """Only static pinhole camera configuration and projection matrices."""
        if not graph_hook_enabled(os.environ):return dict(observation_error='hook_disabled')
        import numpy as np
        result = {}
        for name in ("rgb", "depth"):
            sensor = self._env.sim.sensor_suite.sensors[name]
            cfg = sensor.config
            native = self._env.sim._sensors[name]
            import math
            import hashlib
            from pathlib import Path
            camera = native._sensor_object
            if "pinhole" not in str(camera.camera_type).lower():
                raise ValueError("Only the verified pinhole projection is supported")
            width, height = int(camera.width), int(camera.height)
            native_spec = camera.specification()
            hfov = float(native_spec.parameters["hfov"])
            near, far = float(camera.near_plane_dist), float(camera.far_plane_dist)
            if (width, height) != (cfg.WIDTH, cfg.HEIGHT) or abs(hfov-cfg.HFOV) > 1e-5:
                raise ValueError("Native camera/config calibration mismatch")
            # This legacy binding exposes native frustum parameters, not projectionMatrix_.
            # Reconstruct CameraSensor::recomputeBaseProjectionMatrix's symmetric OpenGL frustum.
            focal = 1. / math.tan(math.radians(hfov)/2)
            projection = np.zeros((4,4))
            projection[0,0] = focal
            projection[1,1] = focal*width/height
            projection[2,2] = -(far+near)/(far-near)
            projection[2,3] = -2*far*near/(far-near)
            projection[3,2] = -1
            source = Path(__file__).resolve().parents[3] / "upstream/habitat-sim/src/esp/sensor/CameraSensor.cpp"
            result[name] = dict(width=width, height=height, hfov=hfov,
                projection_source="CameraSensor.cpp symmetric OpenGL frustum; native width/height/fov/clip parameters",
                projection_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                position=[float(x) for x in native_spec.position], orientation=[float(x) for x in native_spec.orientation],
                projection=projection.tolist())
            if name == "depth":
                result[name].update(near=cfg.MIN_DEPTH, far=cfg.MAX_DEPTH,
                    normalize_depth=cfg.NORMALIZE_DEPTH, raw_units="meters",
                    raw_definition="z", raw_invalid_value=0.)
        result["execution"] = dict(self._graph_execution_spec)
        return result

    def graph_pose_subframes(self, action_id, samples):
        """Private real samples; restore before the single canonical full step."""
        if not native_subframes_enabled(os.environ):
            return dict(sampling_error='native_subframes_disabled')
        import math,time,hashlib
        import numpy as np
        import magnum as mn
        import habitat_sim
        if type(action_id) is not int or action_id not in (1,2,3) or type(samples) is not int or samples!=12:raise ValueError('Fixed release4 primitive sampling required')
        simulator=self._env.sim;agent=simulator.get_agent(0);node=agent.body.object
        t=mn.Vector3(node.translation);r=mn.Quaternion(node.rotation.vector,node.rotation.scalar);scale=mn.Vector3(node.scaling)
        matrix=np.asarray(node.transformation).copy()
        cached=self._env.sim._prev_sim_obs
        def hashes():return {k:hashlib.sha256(np.ascontiguousarray(cached[k]).tobytes()).hexdigest()for k in ('rgb','depth')}
        before=hashes();rows=[]
        def restore():node.translation=t;node.rotation=r;node.scaling=scale
        try:
            for index in range(1,samples):
                restore()
                if action_id==1:
                    agent.controls.action(node,'move_forward',habitat_sim.agent.ActuationSpec(
                        amount=self._graph_execution_spec['forward_step_m']*index/samples),apply_filter=True)
                else:
                    direction=1 if action_id==2 else-1
                    node.rotate_y_local(mn.Rad(math.radians(direction*self._graph_execution_spec['turn_degrees']*index/samples)))
                raw=simulator.get_sensor_observations()
                rows.append(dict(sample_index=index,rgb=np.array(raw['rgb'][...,:3],copy=True),
                    depth=np.array(raw['depth'],copy=True),capture_monotonic_ns=time.monotonic_ns()))
        finally:
            restore()
            if not np.array_equal(np.asarray(node.transformation),matrix):raise RuntimeError('Pose sampling changed canonical pre-action transform')
            if before!=hashes():raise RuntimeError('Pose sampling changed cached host endpoint pixels')
        return dict(action_id=action_id,samples=samples,restoration_exact=True,cached_endpoint_unchanged=True,rows=rows)

    def graph_raw_depth_endpoint(self):
        """Copy already rendered same-frame depth, without rendering another observation."""
        if not graph_hook_enabled(os.environ):return dict(observation_error='hook_disabled')
        import numpy as np
        import time
        return dict(depth=np.array(self._env.sim._prev_sim_obs["depth"], copy=True),
                    capture_monotonic_ns=time.monotonic_ns(),
                    collision=bool(self._env.sim.previous_step_collided))

    def case1_evaluator_state(self):
        state = self._env.sim.get_agent_state()
        import numpy as np,hashlib
        def content(value):
            value=np.ascontiguousarray(value);h=hashlib.sha256();h.update(str(value.dtype).encode());h.update(str(value.shape).encode());h.update(value.tobytes());return h.hexdigest()
        raw=self._env.sim._prev_sim_obs
        # Evaluator-only digests of existing observations; no sensor render/model input.
        evidence=dict(rgb_sha256=content(raw['rgb'][...,:3]),depth_sha256=content(raw['depth']))
        return {"position": state.position.tolist(), "rotation_xyzw": [float(state.rotation.x), float(state.rotation.y), float(state.rotation.z), float(state.rotation.w)], "elapsed_steps": self._env._elapsed_steps, "episode_over": self._env.episode_over, "collided": bool(self._env.sim.previous_step_collided),"endpoint_sensor":evidence}

    def get_reward_range(self) -> Tuple[float, float]:
        return (0.0, 0.0)

    def get_reward(self, observations: Observations) -> float:
        return 0.0

    def get_done(self, observations: Observations) -> bool:
        return self._env.episode_over

    def get_info(self, observations: Observations) -> Dict[Any, Any]:
        return self.habitat_env.get_metrics()
