"""Actual client->service frozen-input contract using an explicit local RPC bridge."""
from types import SimpleNamespace
import pytest
from test_continuous_graph import item,seeded_service
from graphAdapter.map_memory.worker import MemoryWorkerClient
from graphAdapter.map_memory.storage.store import EpisodeStore,load_episode
from graphAdapter.map_memory.admission_receipt import validated_completion
from poseAdapter.interfaces.mapping import MappingSample


def test_frozen_client_commits_real_service_without_live_pose_queries(tmp_path):
    packet,arrays,sample=item(1)
    store=EpisodeStore(tmp_path/'episode','unit',dataset='r2r')
    try:
        service=seeded_service(store,packet,arrays)
        client=MemoryWorkerClient.__new__(MemoryWorkerClient)
        client.profile={'pose_input_mode':'continuous'};client.active_episode='unit';client.count=0
        operations=[];ready=None
        def dispatch(message):
            nonlocal ready
            operations.append(message['op'])
            if message['op']=='prepare':
                args=dict(arrays);args['bindings']=message['bindings'];args['committed_receipt']=message['receipt']
                ready=service.prepare_endpoint(packet,**args,mapping_sample=MappingSample.from_record(message['mapping_sample']))
                return {'result':ready}
            assert message['op']=='commit' and message['candidate_hash']==ready['candidate_hash']
            pointer=service.publish_prepared(frame_uid=message['frame_uid'],target_pose_map_version=message['target_pose_map_version'])
            return {'result':dict(snapshot_id=pointer['snapshot_id'],versions=pointer['versions'],cutoff=pointer['cutoff'])}
        client.call=dispatch
        result=client.consume(packet,arrays['committed_receipt'],frozen_mapping_sample=sample)
        checked=validated_completion(packet,result)
        assert operations==['prepare','commit'] and client.count==1
        reader=load_episode(store.root)
        try:
            assert reader.snapshot_id==checked['snapshot_id']
            assert reader.verify()['views']==1
        finally:reader.close()
        before=(store.root/'CURRENT.json').read_bytes()
        with pytest.raises(ValueError,match='without a live adapter'):
            client.consume(packet,arrays['committed_receipt'],frozen_mapping_sample=sample,pose_adapter=object())
        assert (store.root/'CURRENT.json').read_bytes()==before
    finally:store.close()


def test_frozen_correction_rejects_future_or_wrong_frame_before_rpc():
    from dataclasses import replace
    from test_correction_channel import correction
    packet,arrays,sample=item(1);target=correction(sample)
    client=MemoryWorkerClient.__new__(MemoryWorkerClient)
    def forbidden(*args,**kwargs):raise AssertionError('Invalid correction reached backend')
    client.call=forbidden
    with pytest.raises(ValueError,match='frame/episode'):
        client.flush_mapping_correction(packet=packet,frozen_correction=replace(target,frame_id='unit:f999'))
    with pytest.raises(ValueError,match='timestamp'):
        client.flush_mapping_correction(packet=packet,frozen_correction=replace(target,timestamp_ns=packet.sensor_timestamp_ns+1))
    result=client.flush_mapping_correction(packet=packet,frozen_correction=None)
    assert result['duplicate'] and result['reason']=='no_published_correction'


def test_commit_ack_must_match_prepared_target_and_source_cutoff():
    from graphAdapter.map_memory.worker import validate_prepared_commit
    packet,_,_=item(2)
    good=dict(versions={'pose_map_version':1},cutoff={'capture_seq':packet.capture_seq,'event_seq':packet.event_seq})
    assert validate_prepared_commit(good,1,packet) is good
    with pytest.raises(RuntimeError,match='pose version'):validate_prepared_commit(good,2,packet)
    with pytest.raises(RuntimeError,match='pose version'):validate_prepared_commit(dict(versions={},cutoff=good['cutoff']),None,packet)
    with pytest.raises(RuntimeError,match='cutoff'):
        validate_prepared_commit(dict(versions={'pose_map_version':1},cutoff={'capture_seq':1,'event_seq':10}),1,packet)
