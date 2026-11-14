"""Fault injection at the actual Habitat call dispatcher, with a deterministic pose-only fixture."""
from pathlib import Path
import json,os,sys,traceback
from types import SimpleNamespace as NS
import numpy as np,quaternion
from habitat.core.vector_env import VectorEnv,CALL_COMMAND,CLOSE_COMMAND
from vlnce_baselines.common.environments import VLNCEDaggerEnv
from case1_runtime.episode_scope import episode_scope
from SimulatorAdapter.host_bridge import profile_identity
from SimulatorAdapter import SimulatorAdapter
g=Path.cwd()/'outputs/graph_memory';v=g/'graph002-organized-candidate-01/validation/pose-boundary'
profile=g/'graph002-read-wait-r2r120-01/control/effective-profile.json'
os.environ.update(CASE2_HOOK_MODE='on',CASE2_POSE_PROFILE=str(profile),CASE2_RUN_UID='dispatch-fixture',CASE2_DATASET_KEY='r2r')
ep=NS(scene_id='test/test.glb',episode_id='fixture',instruction=NS(instruction_id=1))
args=dict(pose_session=None,expected_episode_uid=episode_scope(ep)['episode_uid'],profile_sha256=profile_identity(json.loads(profile.read_bytes())))
class Scene:
    def __init__(self):
        self.n=0;self.closed=False
        self._env=NS(current_episode=ep,sim=NS(get_agent_state=self.get_state))
    def get_state(self,agent):
        self.n+=1
        position=[float('nan'),0,0] if self.n==2 else [self.n,0,0]
        return NS(position=position,rotation=np.quaternion(1,0,0,0))
    graph_pose_state=VLNCEDaggerEnv.graph_pose_state
    def close(self):self.closed=True
env=Scene();commands=iter([(CALL_COMMAND,('graph_pose_state',args))]*3+[(CLOSE_COMMAND,None)])
replies=[];failure=None
try:VectorEnv._worker_env(lambda:next(commands),replies.append,lambda:env,(),False,False)
except Exception as err:failure=dict(type=type(err).__name__,message=str(err))
state=NS(position=np.zeros(3),rotation=np.quaternion(1,0,0,0))
provider=SimulatorAdapter(NS(get_agent_state=lambda _:state));provider.reset_episode('ep')
rotations={}
for i,q in enumerate([[0,0,0,0],[1e-180,0,0,0],[1e180,0,0,0],[float('nan'),0,0,0],[2,0,0,0],[-1,0,0,0]]):
    state.rotation=np.quaternion(*q)
    try:
        value=provider.push_observation(frame_id=f'ep:f{i}',timestamp_ns=i)
        rotations[str(q)]=dict(valid=value.valid)
    except Exception as err:rotations[str(q)]=dict(type=type(err).__name__)
provider.shutdown()
out=dict(reads=env.n,closed=env.closed,replies=replies,failure=failure,direct=rotations)
(v/('pose-dispatch-'+sys.argv[1]+'.json')).write_text(json.dumps(out,indent=2));print(out)
