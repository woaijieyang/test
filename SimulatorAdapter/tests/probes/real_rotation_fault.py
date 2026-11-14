"""Compare the graph pose-only RPC adapter with actual Habitat base state on a real scene."""
from pathlib import Path
from types import SimpleNamespace as NS
import os,json,sys
import numpy as np
import quaternion,habitat_sim
from SimulatorAdapter.host_bridge import pose_rpc_reply,profile_identity,_VectorPoseAdapter,_VectorPoseSource
from graphAdapter.interfaces.pose import PoseReader
from case1_runtime.episode_scope import episode_scope
g=Path('outputs/graph_memory').resolve();run=g/'graph002-pose-dispatch-1953-01'
profile=run/'control/effective-profile.json';os.environ.update(CASE2_HOOK_MODE='on',CASE2_POSE_PROFILE=str(profile),CASE2_RUN_UID='dispatch-geometry-test',CASE2_DATASET_KEY='rxr_us')
member=json.loads((run/'retention_plan.json').read_bytes())['entries'][0]['member']
spec=json.loads((run/'navigation/rxr_us/run_manifest.json').read_bytes());ep=NS(scene_id=member[1],episode_id=member[2],instruction=NS(instruction_id=member[3]))
uid=episode_scope(ep)['episode_uid']
# Use the declared runtime scene, never load goals, semantic sensors or navigation annotations.
scene=Path(spec['scene_assets']['scene_root'])/member[1]
assert scene.is_file(),scene
cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id=str(scene);cfg.create_renderer=False;cfg.load_semantic_mesh=False
agent=habitat_sim.agent.AgentConfiguration();agent.sensor_specifications=[]
sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[agent]))
reader_source=sim.get_agent(0);mode='ok';actual=None
class Source:
    def get_agent_state(self,agent_id):
        global actual
        assert agent_id==0
        measured=reader_source.get_state()
        actual=(np.array(measured.position,copy=True),quaternion.as_rotation_matrix(measured.rotation))
        return NS(position=measured.position,rotation=np.quaternion(0,0,0,0) if mode=='bad' else measured.rotation)
env=NS(_env=NS(sim=Source(),current_episode=ep))
class RPC:
    def call_at(self,i,method,args):
        assert method=='graph_pose_state' and i==0
        return pose_rpc_reply(env,**args)
provider=_VectorPoseAdapter(_VectorPoseSource(RPC(),0,profile_identity(json.loads(profile.read_bytes()))))
from SimulatorAdapter.pose import InvalidSimulatorMeasurement
try:
    provider.reset_episode(uid);origin=actual;read=PoseReader(provider,source='simulator_ground_truth')
    checks=[];B=np.array([[0.,-1.,0.],[0.,0.,1.],[-1.,0.,0.]])
    for i,(xyz,yaw) in enumerate([([0.4,0.1,-1.7],.82),([0.1,0.1,-2.1],1.1),([-0.5,.3,-1.2],-1.3)]):
        state=habitat_sim.AgentState();state.position=xyz;state.rotation=quaternion.from_rotation_vector([0.,yaw,0.]);reader_source.set_state(state)
        mode='bad' if i==1 else 'ok'
        try:frame=read.capture(episode_id=uid,frame_id=f'{uid}:f{i}',timestamp_ns=i)
        except InvalidSimulatorMeasurement:
            assert i==1 and provider.get_status()['frames']==1
            checks.append(dict(step=i,status='rejected'));continue
        assert i in (0,2)
        T=np.array(frame.T_map_base);p,R=actual;p0,R0=origin
        pos=B.T@R0.T@(p-p0);rot=B.T@R0.T@R@B
        assert np.allclose(T[:3,3],pos,atol=1e-9) and np.allclose(T[:3,:3],rot,atol=1e-9)
        checks.append(dict(step=i,status='valid',position_error_m=float(np.max(np.abs(T[:3,3]-pos))),rotation_max_abs=float(np.max(np.abs(T[:3,:3]-rot)))))
    assert len(checks)==3 and checks[1]['status']=='rejected' and provider.get_status()['frames']==2
    report_name='real-rotation-fault.json' if len(sys.argv)==1 else 'real-rotation-'+sys.argv[1]+'.json'
    if Path(report_name).name!=report_name:raise ValueError('Report basename required')
    (g/'graph002-organized-candidate-01/validation/pose-boundary'/report_name).write_text(json.dumps(dict(scene=member[1],checks=checks),indent=2))
    print(checks)
finally:provider.shutdown();sim.close()
