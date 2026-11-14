import json
from types import SimpleNamespace
import numpy as np
import pytest
from SimulatorAdapter import SimulatorAdapter
from SimulatorAdapter.tests.test_pose import PoseOnly
from SimulatorAdapter.tests.test_simulator_hook import profile
from graphAdapter.observation_pose.aware_hook import AwarePoseHook
from graphAdapter.observation_pose.tests.fixtures import sensor_spec
from graphAdapter.map_memory.storage.routing import create_run
from graphAdapter.map_memory.tests.test_routing import finish_host
from case1_runtime.episode_scope import episode_scope

def test_routed_simulator_provider_closes_without_native_artifacts(tmp_path,monkeypatch):
    member=['r2r','mp3d/fixture/fixture.glb','1','-']
    plan=dict(owner_roles=['host','source000','pose'],owner_components={'host':'host_trace','source000':'file_owner','pose':'pose_provider'},
        entries=[dict(key='e1',member=member,mode='ordinary',owner_roles_by_side={'control':['host'],'shadow':['host','source000','pose']})],
        max_trace_raw_bytes=4*1024**2,max_trace_compressed_bytes=1024**2,max_diagnostic_bytes=16*1024**2,
        max_expanded_bytes=32*1024**2,max_ordinary_retained_bytes=8*1024**2,max_summary_bytes=1024**2)
    root=tmp_path/'run';common=create_run(root,plan,run_uid='simulator-lifecycle-test')
    monkeypatch.setenv('CASE2_STORAGE_BINDING',json.dumps(dict(common,side='shadow',attempt='a',worker_id='shadow0')))
    monkeypatch.setenv('CASE2_RUN_UID','runtime-shadow');monkeypatch.setenv('CASE2_ATTEMPT_ID','a');monkeypatch.setenv('CASE2_DATASET_KEY','r2r')
    ep=SimpleNamespace(scene_id=member[1],episode_id='1',instruction=SimpleNamespace(instruction_id=None))
    sim=PoseOnly();provider=SimulatorAdapter(sim,rotation_matrix=lambda r:r)
    hook=AwarePoseHook(root/'shards/worker/observation_pose',profile(),adapter_factory=lambda *a:provider)
    try:
        scope=episode_scope(ep);hook.reset(scope['episode_uid'],sensor_spec(),np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32),1,identity=scope)
        recorder=finish_host(root,ep);owner=recorder.storage_episode
        assert owner._state()['state']=='ACTIVE'
        hook.end_episode([])
        assert owner._state()['state']=='DELETED' and not owner.work.exists()
        routes=json.loads((owner.result/'routes.json').read_bytes())
        observed=routes['closed']['pose']['payload']['observed']
        assert observed['component']=='pose_provider' and observed['release']['reader_released']
        assert not any(s['role']=='pose' for s in routes['scopes'])
        assert provider.episode_id is None and provider.closed
        # Provider shutdown does not own or close the simulator itself.
        sim.get_agent_state()
    finally:hook.close()
