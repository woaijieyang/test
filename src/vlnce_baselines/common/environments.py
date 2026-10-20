from typing import Any, Dict, Optional, Tuple

import habitat
from habitat import Config, Dataset
from habitat.core.simulator import Observations
from habitat_baselines.common.baseline_registry import baseline_registry


@baseline_registry.register_env(name="VLNCEDaggerEnv")
class VLNCEDaggerEnv(habitat.RLEnv):
    def __init__(self, config: Config, dataset: Optional[Dataset] = None):
        super().__init__(config.TASK_CONFIG, dataset)

    def case1_evaluator_state(self):
        state = self._env.sim.get_agent_state()
        return {"position": state.position.tolist(), "rotation_xyzw": [float(state.rotation.x), float(state.rotation.y), float(state.rotation.z), float(state.rotation.w)], "elapsed_steps": self._env._elapsed_steps, "episode_over": self._env.episode_over, "collided": bool(self._env.sim.previous_step_collided)}

    def get_reward_range(self) -> Tuple[float, float]:
        return (0.0, 0.0)

    def get_reward(self, observations: Observations) -> float:
        return 0.0

    def get_done(self, observations: Observations) -> bool:
        return self._env.episode_over

    def get_info(self, observations: Observations) -> Dict[Any, Any]:
        return self.habitat_env.get_metrics()
