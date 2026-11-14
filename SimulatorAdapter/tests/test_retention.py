import copy
import numpy as np
import pytest
from SimulatorAdapter import SimulatorAdapter
from SimulatorAdapter.tests.test_pose import PoseOnly
from SimulatorAdapter.tests.test_simulator_graph_boundary import observation
from graphAdapter.interfaces.pose import PoseReader
from graphAdapter.observation_pose.provider_contract import audit_simulator_endpoints

def test_simulator_sampling_audit_does_not_accept_native_or_mismatched_events():
 sim=PoseOnly();provider=SimulatorAdapter(sim,rotation_matrix=lambda x:x);provider.reset_episode('unit')
 p,a=observation(1,PoseReader(provider,source='simulator_ground_truth'),sim)
 event=dict(kind='pose',frame_uid=p.frame_uid,sensor_sequence=1,canonical=True,sampling_contract=None,runtime_artifacts=None,pose=p.to_record()['pose_record'])
 result=audit_simulator_endpoints([p.to_record()],[event]);assert result['mode']=='simulator_endpoint_pose' and result['native_slam_used'] is False
 with pytest.raises(ValueError,match='subframe'):audit_simulator_endpoints([p.to_record()],[event,dict(kind='pose_sample')])
 with pytest.raises(ValueError,match='Duplicate'):audit_simulator_endpoints([p.to_record()],[event,event])
 changed=copy.deepcopy(event);changed['pose']['timestamp_ns']+=1
 with pytest.raises(ValueError,match='differ'):audit_simulator_endpoints([p.to_record()],[changed])
 changed=copy.deepcopy(event);changed['runtime_artifacts']={}
 with pytest.raises(ValueError,match='native'):audit_simulator_endpoints([p.to_record()],[changed])
 provider.shutdown()


@pytest.mark.parametrize('fault', ['unexpected_failure','orphan_failure','duplicate_failure','canonical_for_missing',
                                    'duplicate_packet','boolean_sequence','other_episode','unknown_sampling'])
def test_pose_audit_requires_one_matching_outcome_per_endpoint(fault):
    from graphAdapter.observation_pose.provider_contract import simulator_pose_record
    from dataclasses import replace
    sim=PoseOnly()
    provider=SimulatorAdapter(sim,rotation_matrix=lambda x:x)
    provider.reset_episode('unit')
    try:
        reader=PoseReader(provider,source='simulator_ground_truth')
        p,_=observation(1,reader,sim)
        record=p.to_record()
        canonical=dict(kind='pose',frame_uid=p.frame_uid,sensor_sequence=1,canonical=True,pose=record['pose_record'])
        failure=dict(kind='geometry_unavailable',frame_uid=p.frame_uid,stage='pose',reason='injected')
        packets=[record]
        events=[canonical]
        if fault=='unexpected_failure':events.append(failure)
        elif fault=='orphan_failure':events.append(dict(failure,frame_uid='unit:orphan'))
        elif fault in ('duplicate_failure','canonical_for_missing'):
            frame=reader.read(episode_id='unit',frame_id=p.frame_uid,timestamp_ns=p.sensor_timestamp_ns)
            missing=replace(frame,valid=False,T_map_base=None,T_odom_base=None,T_map_odom=None)
            packets=[dict(record,pose_record=simulator_pose_record(missing,p.T_base_camera))]
            events=[failure,failure] if fault=='duplicate_failure' else [canonical,failure]
        elif fault=='duplicate_packet':packets.append(dict(record,capture_seq=2))
        elif fault=='boolean_sequence':events=[dict(canonical,sensor_sequence=True)]
        elif fault=='other_episode':events=[dict(canonical,episode_uid='another')]
        else:events=[dict(canonical,sampling_contract='unrecognized')]
        with pytest.raises(ValueError):audit_simulator_endpoints(packets,events)
    finally:
        provider.shutdown()


def test_duplicate_packets_rejected_before_retained_map_is_opened(tmp_path):
    import gzip,json
    from graphAdapter.evaluation.retained import audit_memory_materials
    from graphAdapter.map_memory.storage.lifecycle import LifecycleError
    path=tmp_path/'packets.jsonl.gz'
    with gzip.open(path,'wt') as out:
        for i in range(2):
            out.write(json.dumps(dict(frame_uid='fixture:1'))+chr(10))
    with pytest.raises(LifecycleError,match='Duplicate retained observation packet'):
        audit_memory_materials(tmp_path/'no-map',path,tmp_path/'no-flow',tmp_path/'no-report')
