"""Small headless native adapter with explicit quaternion convention."""
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path


@dataclass(frozen=True)
class NativeState:
    position: tuple[float, float, float]
    quaternion_xyzw: tuple[float, float, float, float]

    def __post_init__(self):
        object.__setattr__(self, "position", tuple(float(v) for v in self.position))
        object.__setattr__(self, "quaternion_xyzw", tuple(float(v) for v in self.quaternion_xyzw))
        if len(self.position) != 3 or len(self.quaternion_xyzw) != 4:
            raise ValueError("Explicit xyz / xyzw state required")
        if not all(math.isfinite(float(v)) for v in self.key_values()):
            raise ValueError("Nonfinite state")
        if abs(sum(v * v for v in self.quaternion_xyzw) - 1.) > 1e-4:
            raise ValueError("Invalid quaternion norm")

    def key_values(self):
        return self.position + self.quaternion_xyzw


class NativeAdapter:
    def __init__(self, navmesh_path, navmesh_sha256, motion):
        if not os.environ.get("CASE1_PROTECTION"):
            raise RuntimeError("Protected runtime required")
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        import habitat_sim
        self.habitat_sim = habitat_sim
        self.motion = motion
        path = Path(navmesh_path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != navmesh_sha256:
            raise RuntimeError("Navmesh identity drift")
        cfg = habitat_sim.SimulatorConfiguration()
        cfg.scene_id = "NONE"
        cfg.create_renderer = False
        cfg.enable_physics = False
        cfg.allow_sliding = motion.allow_sliding
        agent = habitat_sim.agent.AgentConfiguration()
        agent.height = motion.body_height_m
        agent.radius = motion.body_radius_m
        agent.sensor_specifications = []
        agent.action_space = {
            1: habitat_sim.agent.ActionSpec("move_forward", habitat_sim.agent.ActuationSpec(amount=motion.forward_m)),
            2: habitat_sim.agent.ActionSpec("turn_left", habitat_sim.agent.ActuationSpec(amount=motion.turn_degrees)),
            3: habitat_sim.agent.ActionSpec("turn_right", habitat_sim.agent.ActuationSpec(amount=motion.turn_degrees)),
        }
        self.sim = habitat_sim.Simulator(habitat_sim.Configuration(cfg, [agent]))
        if not self.sim.pathfinder.load_nav_mesh(str(path)):
            self.sim.close()
            raise RuntimeError("Native navmesh load failed")
        self.native_calls = 0
        self.restore_calls = 0

    def restore(self, state: NativeState):
        """Planning/probe initialization only, never a hidden executed action."""
        from habitat_sim.utils.common import quat_from_coeffs
        import numpy as np
        raw = self.habitat_sim.AgentState()
        raw.position = np.asarray(state.position, dtype=np.float32)
        raw.rotation = quat_from_coeffs(state.quaternion_xyzw)
        self.sim.get_agent(0).set_state(raw)
        self.restore_calls += 1

    def snapshot(self):
        state = self.sim.get_agent(0).get_state()
        return NativeState(tuple(float(v) for v in state.position),
                           (*map(float, state.rotation.imag), float(state.rotation.real)))

    def step(self, action):
        if action not in (1, 2, 3):
            raise ValueError("Only explicit native primitives are supported")
        self.sim.step(action)
        self.native_calls += 1
        state = self.snapshot()
        if not all(math.isfinite(v) for v in state.key_values()):
            raise RuntimeError("Nonfinite native state")
        return state

    def geodesic_distance(self, start, goal):
        path = self.habitat_sim.ShortestPath()
        path.requested_start = start
        path.requested_end = goal
        return float(path.geodesic_distance) if self.sim.pathfinder.find_path(path) else math.inf

    def is_navigable(self, position):
        return bool(self.sim.pathfinder.is_navigable(position))

    def close(self):
        self.sim.close()
