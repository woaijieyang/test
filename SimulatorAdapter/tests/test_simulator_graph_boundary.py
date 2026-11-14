from dataclasses import replace
import hashlib
import numpy as np
import pytest
from SimulatorAdapter import SimulatorAdapter
from graphAdapter.interfaces.pose import PoseReader
from SimulatorAdapter.tests.test_pose import PoseOnly
from test_continuous_graph import item,seeded_service,seed_camera
from graphAdapter.observation_pose.provider_contract import simulator_pose_record
from graphAdapter.observation_packet import geometry_input,perception_input,require_same_frame
from graphAdapter.map_memory.storage.store import EpisodeStore,canonical,IntegrityError

def observation(n,reader,sim):
    packet,args,_=item(n);sim.position=np.array([0.,0.,-n*.1])
    frame=reader.capture(episode_id='unit',frame_id=packet.frame_uid,timestamp_ns=packet.sensor_timestamp_ns)
    packet=replace(packet,pose_provider='simulator_ground_truth',pose_record=simulator_pose_record(frame,packet.T_base_camera))
    args['committed_receipt']['packet_record_hash']=hashlib.sha256(canonical(packet.to_record())).hexdigest()
    return packet,args

def test_simulator_packet_rejects_extra_truth_and_unselected_provider():
    sim=PoseOnly();adapter=SimulatorAdapter(sim,rotation_matrix=lambda x:x);adapter.reset_episode('unit')
    reader=PoseReader(adapter,source='simulator_ground_truth');p,a=observation(1,reader,sim)
    assert require_same_frame(geometry_input(p),perception_input(p))
    assert geometry_input(p).pose_provider=='simulator_ground_truth'
    with pytest.raises(ValueError,match='unauthorized'):replace(p,pose_record=dict(p.to_record()['pose_record'],goal_position=[1,2,3]))
    with pytest.raises(ValueError,match='explicit provider'):replace(p,pose_provider='cuvslam_rtabmap_rgbd')

def test_simulator_pose_reaches_geometry_and_storage_without_slam_metadata(tmp_path):
    sim=PoseOnly();adapter=SimulatorAdapter(sim,rotation_matrix=lambda x:x);adapter.reset_episode('unit')
    reader=PoseReader(adapter,source='simulator_ground_truth');p,a=observation(1,reader,sim)
    store=EpisodeStore(tmp_path/'map','unit',dataset='r2r')
    try:
        service=seeded_service(store,p,a);result=service.ingest(p,**a)
        assert not result['duplicate'] and service.version==0
        p2,a2=observation(2,reader,sim);seed_camera(service,p2,a2);service.ingest(p2,**a2)
        snapshot=store.open_reader()
        try:
            assert snapshot.verify()['views']==2
            assert snapshot._graph['pose_provider']=='simulator_ground_truth'
            assert snapshot._graph['views'][p2.frame_uid]['geometry_status']=='available'
            assert snapshot._graph['views'][p2.frame_uid]['pose_binding']['kind']=='simulator_pose_snapshot'
            assert snapshot._graph['tiles']
            traces = snapshot.get_trace()
            assert len(traces) == 1
            edge = traces[0]['motion']['traversed']
            assert edge['src'] == p.frame_uid and edge['dst'] == p2.frame_uid
            assert edge['direction'] == 'recorded_only'
            assert edge['current_passability'] == 'unknown'
            assert any(e['type'] == 'traversed' and e['id'] == edge['id'] for e in snapshot._graph['edges'])
        finally:snapshot.close()
        native,arrays,sample=item(3)
        with pytest.raises(IntegrityError,match='provider'):service.ingest(native,**arrays,mapping_sample=sample)
    finally:store.close();adapter.shutdown()
