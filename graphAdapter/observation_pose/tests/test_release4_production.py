from pathlib import Path
import json,hashlib
"""New production boundary tests; CPU stand-ins do not qualify native accuracy."""
import numpy as np
import pytest
from poseAdapter import release4_input,PoseConfig,Calibration,DepthSpec
from poseAdapter.pose_types import PoseEstimate
from graphAdapter.observation_pose.alignment import RGBDAlignmentBridge
from graphAdapter.observation_pose.pose_bridge import PoseBridge

class Adapter:
    def __init__(self,cfg):
        self.input_config=cfg;self.config=PoseConfig(pose_backend=cfg.pose_backend,**cfg.pose_options);self.calls=[]
    def reset_episode(self,ep,**kw):self.ep=ep
    def push_observation(self,**kw):
        self.calls.append(kw);self.last=PoseEstimate(self.ep,kw['frame_id'],kw['timestamp_ns'],valid=False,source='cuvslam_rtabmap_rgbd');return self.last
    def get_frame_snapshot(self,*args,**kwargs):return self.last,None
    def shutdown(self):pass

def bridge():
    cal=Calibration.optical_mount(8,8,4.,4.,3.5,3.5,1.25);ds=DepthSpec('meters','z','float32',0.,10.)
    cfg=release4_input(cal,forward_step=.25,turn_degrees=15.,forward_samples=12,turn_samples=12,sensor_rate_hz=120);adapter=Adapter(cfg)
    alignment=RGBDAlignmentBridge(cal,cal,ds,np.eye(4));data=alignment.align(np.zeros((8,8,3),np.uint8),np.ones((8,8),np.float32))
    result=PoseBridge(cfg,dict(pose_backend=cfg.pose_backend,**cfg.pose_options),cal,aligned_depth_spec=ds,adapter=adapter,alignment_hash=alignment.calibration_hash,stream_mode=True);result.reset('ep');return result,adapter,data

def test_release4_subframes_do_not_become_host_frames():
    p,a,data=bridge();p.ingest('ep:f000001',p.next_timestamp(),data)
    for i in range(1,12):assert p.ingest_subframe('ep:f000002',data,action='turn_left',sample_index=i)is None
    final=p.ingest('ep:f000002',p.next_timestamp(),data,action='turn_left',collided=False)
    assert final['frame_id']=='ep:f000002'and len(a.calls)==13
    assert len(p.frames)==2 and p.sequence==13
    from poseAdapter.pose_sync import logical_sensor_timestamp
    assert [x['timestamp_ns']for x in a.calls]==[logical_sensor_timestamp(i,120)for i in range(1,14)]
    assert all(x['frame_id'].startswith('ep:f000002:pose')for x in a.calls[1:-1])

def test_release4_stop_has_one_sample_and_no_synthetic_turns():
    p,a,data=bridge();p.ingest('ep:f000001',p.next_timestamp(),data);p.ingest('ep:f000002',p.next_timestamp(),data,action='stop',collided=False)
    assert len(a.calls)==2 and p.sequence==2
    with pytest.raises(RuntimeError):p.ingest('ep:f000003',p.next_timestamp(),data,action='stop',collided=False)

def test_private_sampler_failure_precedes_real_step(tmp_path):
    from graphAdapter.observation_pose.host_wiring import sample_before_environment_step
    class Hook:
        release4=True
        def pose_subframes(self,*args):raise AssertionError('Invalid batch must not reach pose')
        def abort_before_step(self,action,error):raise RuntimeError('abort-before-step')
    class Env:
        def call_at(self,*args):return dict(action_id=1,samples=12,restoration_exact=False,cached_endpoint_unchanged=True,rows=[])
    with pytest.raises(RuntimeError,match='abort-before-step'):sample_before_environment_step(Hook(),Env(),0,1)

def test_stop_does_not_call_sampler():
    from graphAdapter.observation_pose.host_wiring import sample_before_environment_step
    class Hook:release4=True
    class Env:
        def call_at(self,*args):raise AssertionError('STOP rendered extra samples')
    sample_before_environment_step(Hook(),Env(),0,0)

@pytest.mark.parametrize('index,queue,expected',[(1,[],[2,2,2]),(2,[2,2],[2,2]),(3,[2],[2])])
def test_pre_step_cancel_uses_macro_not_queue(tmp_path,index,queue,expected):
    import json
    from graphAdapter.observation_pose.aware_hook import CaptureAttemptAborted
    from case1_runtime.trace import TraceRecorder
    from types import SimpleNamespace
    ep=SimpleNamespace(scene_id='/scene/scan/scan.glb',episode_id='1',instruction=SimpleNamespace(instruction_id='i'))
    r=TraceRecorder(tmp_path,'r2r');r.ensure_episode(ep,dict(elapsed_steps=0))
    error=CaptureAttemptAborted('prestep',dict(primitive_executed=False,primitive_index=index,primitive_count=3,action_id=2))
    r.abort_attempt(error,None,queue)
    rows=[json.loads(l)for l in (r.directory/'trace.jsonl').read_text().splitlines()]
    assert rows[-1]['cancelled_actions']==expected and rows[-1]['host_queue_at_failure']==queue
    assert not any(x['kind']=='primitive_action'for x in rows)

def test_pre_step_unknown_macro_is_unknown(tmp_path):
    import json
    from graphAdapter.observation_pose.aware_hook import CaptureAttemptAborted
    from case1_runtime.trace import TraceRecorder
    from types import SimpleNamespace
    ep=SimpleNamespace(scene_id='/scene/scan/scan.glb',episode_id='1',instruction=SimpleNamespace(instruction_id='i'))
    r=TraceRecorder(tmp_path,'r2r');r.ensure_episode(ep,dict(elapsed_steps=0));r.abort_attempt(CaptureAttemptAborted('unknown',dict(primitive_executed=False)),None,[2])
    assert json.loads((r.directory/'trace.jsonl').read_text().splitlines()[-1])['cancelled_actions']is None

def test_required_sampling_rejects_all_events_missing(tmp_path):
    from graphAdapter.observation_pose.production import audit_samples
    a=tmp_path/'packets';a.write_text('');b=tmp_path/'flow';b.write_text('')
    with pytest.raises(RuntimeError,match='missing'):audit_samples(a,b)

def test_strict_endpoint_comparison_rejects_missing_and_shared_frame_diff(tmp_path):
    import json
    from graphAdapter.map_memory.storage.lifecycle import compare_traces
    a=tmp_path/'a';b=tmp_path/'b'
    state=dict(position=[0,0,0],rotation_xyzw=[0,0,0,1],elapsed_steps=0,episode_over=False,collided=False,endpoint_sensor=dict(rgb_sha256='a'*64,depth_sha256='b'*64))
    reset=dict(kind='reset',task_key='e',state_evaluator_only=state)
    a.write_text(json.dumps(reset)+'\n');b.write_text(json.dumps(dict(reset,state_evaluator_only=dict(state,position=[1,0,0])))+'\n')
    assert not compare_traces(a,b,endpoint_schema=True)['equal']
    missing=dict(kind='reset',task_key='e');a.write_text(json.dumps(missing)+'\n');b.write_text(a.read_text())
    assert not compare_traces(a,b,endpoint_schema=True)['equal']

@pytest.mark.parametrize('segment,worker,ranges,expected', [('first0',0,{'r2r':[0,1],'rxr_us':[0,0]},{'r2r':1,'rxr_us':0}),('rest0',0,{'r2r':[1,None],'rxr_us':[0,None]},{'r2r':152,'rxr_us':102}),('full1',1,{'r2r':[0,None],'rxr_us':[0,None]},{'r2r':153,'rxr_us':102}),('full2',2,{'r2r':[0,None],'rxr_us':[0,None]},{'r2r':153,'rxr_us':102}),('full3',3,{'r2r':[0,None],'rxr_us':[0,None]},{'r2r':153,'rxr_us':101})])
def test_empty_frozen_domain_segment_never_reaches_native_chunker(tmp_path,monkeypatch,segment,worker,ranges,expected):
    """Use actual sealed annotations/native reader; stop before model/process launch."""
    import os
    from graphAdapter.evaluation import runner,admission,registry_binding,resources
    from case1_runtime import scene_assets
    from habitat_extensions.task import VLNCEDatasetV1,RxRVLNCEDatasetV1
    root=Path(__file__).resolve().parents[4]
    b=json.loads((root/'outputs/graph_memory/graph001-release4-fullA-20261108-r4/control/bindings.json').read_text())
    b.update(project_root=str(tmp_path),cpu_assignment=list(os.sched_getaffinity(0)))
    stage=tmp_path/'stage.json';stage.write_text(json.dumps(dict(feature='map_memory',implementation_status='FROZEN_READY_FOR_SHADOW',production_admission={},map_memory=dict(execution_mode='live'))))
    # Presence of the explicit production binding is required by the segment gate.
    v=json.loads(stage.read_text());v['production_admission']={'test':'CPU-boundary'};stage.write_text(json.dumps(v))
    binding_hash=hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    monkeypatch.setattr(admission,'verify_release4_production',lambda *args:dict(bindings_content_sha256=binding_hash,segments={segment:dict(worker_index=worker,ranges=ranges,expected_counts=expected)}))
    real_scene=dict(scene_root=b['scene_root'],assets=json.loads(Path(b['scene_profile']).read_text())['assets'])
    monkeypatch.setattr(scene_assets,'verify_scene_binding',lambda *args:real_scene)
    monkeypatch.setattr(resources,'admit',lambda *args:{})
    monkeypatch.setenv('CASE1_PROTECTION','{}');monkeypatch.setenv('CUDA_VISIBLE_DEVICES','4')
    calls=[]
    for cls in [VLNCEDatasetV1,RxRVLNCEDatasetV1]:
        original=cls.from_json
        def checked(self,string,*args,_original=original,**kw):
            assert json.loads(string)['episodes'];calls.append(len(json.loads(string)['episodes']));return _original(self,string,*args,**kw)
        monkeypatch.setattr(cls,'from_json',checked)
    class Prepared(Exception):pass
    def stop(*args,**kw):raise Prepared()
    monkeypatch.setattr(registry_binding,'source_snapshot',stop)
    with pytest.raises(Prepared):runner.evaluate(b,stage,Path(root/'outputs/graph_memory/registration/case1'),'A',['r2r','rxr_us'],None,tmp_path/'outputs/graph_memory/probe',hook_mode='off',worker_index=worker,worker_count=4,execution_segment=segment)
    assert calls==[expected[d]for d in ['r2r','rxr_us']if expected[d]>0]
