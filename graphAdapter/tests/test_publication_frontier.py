import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[3]/'src/graphAdapter/map_memory/tests'))
from test_storage import archive,publish,graph,EP
from graphAdapter.map_memory.storage.store import EpisodeStore,load_episode,VersionUnavailable,IntegrityError

@pytest.mark.parametrize('failure',['cutoff','event','version','missing_view'])
def test_late_derived_result_cannot_rewind_or_drop_committed_input(tmp_path,failure):
    store=EpisodeStore(tmp_path/'episode',EP,dataset='r2r')
    try:
        archive(store,1);publish(store,[1],1);archive(store,2);publish(store,[1,2],2)
        before=(store.root/'CURRENT.json').read_bytes()
        value=graph([1,2],2);versions={'pose_map_version':2};cutoff={'capture_seq':2,'event_seq':20}
        if failure=='cutoff':cutoff['capture_seq']=1
        elif failure=='event':cutoff['event_seq']=10
        elif failure=='version':value=graph([1,2],1);versions['pose_map_version']=1
        else:value=graph([1],2)
        with pytest.raises((VersionUnavailable,IntegrityError)):
            store.publish(value,versions,cutoff)
        assert (store.root/'CURRENT.json').read_bytes()==before
        reader=load_episode(store.root)
        try:assert len(reader._graph['views'])==2 and reader.versions['pose_map_version']==2
        finally:reader.close()
        # Same-cutoff corrections remain supported and retain both observations.
        pointer=publish(store,[1,2],3)
        assert pointer['versions']['pose_map_version']==3
    finally:store.close()


def test_same_cutoff_late_candidate_cannot_replace_newer_publication(tmp_path):
    from graphAdapter.map_memory.storage.store import ConcurrentWriterError
    store=EpisodeStore(tmp_path/'episode',EP,dataset='r2r')
    try:
        archive(store,1)
        first=store.publish(graph([1],1),{'pose_map_version':1},{'capture_seq':1,'event_seq':10},expected_parent_id=None)
        fresh=graph([1],1);fresh['scope']='newly_materialized_content'
        second=store.publish(fresh,{'pose_map_version':1},{'capture_seq':1,'event_seq':10},expected_parent_id=first['snapshot_id'])
        before=(store.root/'CURRENT.json').read_bytes()
        with pytest.raises(ConcurrentWriterError,match='base'):
            store.publish(graph([1],1),{'pose_map_version':1},{'capture_seq':1,'event_seq':10},expected_parent_id=first['snapshot_id'])
        assert (store.root/'CURRENT.json').read_bytes()==before
        reader=load_episode(store.root)
        try:assert reader.snapshot_id==second['snapshot_id'] and reader._graph['scope']=='newly_materialized_content'
        finally:reader.close()
    finally:store.close()


def test_service_reloads_new_base_after_prepared_publication_is_rejected(tmp_path):
    import json,numpy as np
    from test_service_integration import bound_packet,seeded_service,seed_camera
    from graphAdapter.map_memory.storage.store import canonical,ConcurrentWriterError
    store=EpisodeStore(tmp_path/'episode','unit',dataset='r2r')
    try:
        bindings=dict(episode_id='unit',map_version=0,optimized_keyframes={'10':np.eye(4).tolist()})
        first,a1=bound_packet(1,10,bindings);service=seeded_service(store,first,a1);service.ingest(first,**a1)
        second,a2=bound_packet(2,10,bindings);seed_camera(service,second,a2)
        prepared=service.prepare_endpoint(second,**a2)
        newer=json.loads(canonical(service.graph));newer['scope']='newer-base-content'
        current=store.publish(newer,{'pose_map_version':0},dict(service.pointer['cutoff']))
        with pytest.raises(ConcurrentWriterError,match='base'):
            service.publish_prepared(frame_uid=second.frame_uid,target_pose_map_version=0)
        assert service.pointer==current and service.graph['scope']=='newer-base-content'
        assert service.prepared is None
        result=service.ingest(second,**a2)
        assert result['snapshot_id']==store.current['snapshot_id']
        assert store.current['cutoff']['capture_seq']==2
    finally:store.close()
