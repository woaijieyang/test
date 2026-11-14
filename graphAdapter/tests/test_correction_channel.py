import copy,json
import numpy as np
import pytest
from poseAdapter.interfaces.mapping import CorrectionSnapshot
from graphAdapter.evaluation.publications import index_publications
from graphAdapter.map_memory.storage.store import EpisodeStore,load_episode
from test_continuous_graph import item
from test_service_integration import seeded_service,seed_camera

def correction(sample):
    return CorrectionSnapshot(sample.episode_id,sample.episode_instance,sample.frame_id,
        sample.timestamp_ns,sample.native_map_version,sample.bindings_json,sample.odometry_epoch)

def test_independent_correction_uses_committed_facts_without_readmitting_packet(tmp_path):
    p,a,m=item(1);store=EpisodeStore(tmp_path/"episode","unit",dataset="r2r")
    try:
        s=seeded_service(store,p,a);s.ingest(p,**a,mapping_sample=m)
        p,a,m=item(2);seed_camera(s,p,a);s.ingest(p,**a,mapping_sample=m)
        _,_,target=item(3)
        update=correction(target)
        before=(store.root/"CURRENT.json").read_bytes()
        ready=s.prepare_correction(update)
        assert ready["replayed_frames"]==2
        assert (store.root/"CURRENT.json").read_bytes()==before
        assert s.mapping_chart.applied_map_version==1
        s.publish_prepared(frame_uid=p.frame_uid,target_pose_map_version=3)
        assert s.mapping_chart.applied_map_version==3
        assert s.prepare_correction(update)["duplicate"]
        r=load_episode(store.root)
        try:
            assert r.verify()["views"]==2 and len(r.get_trace())==1
        finally:r.close()
    finally:store.close()

def test_correction_wire_and_publication_identity():
    _,_,m=item(1);c=correction(m)
    assert CorrectionSnapshot.from_record(c.to_record())==c
    packet={"frame_uid":"e:f1","capture_seq":1,"event_seq":4}
    base=dict(frame_uid="e:f1",source_packet_event_seq=4,cutoff_event_seq=4,versions={"pose_map_version":0})
    events=[dict(base,kind="PublishedSnapshot",snapshot_id="a"),dict(base,kind="MapCorrectionPublished",snapshot_id="b")]
    endpoints,revisions=index_publications(events,{"e:f1":packet})
    assert len(endpoints)==1 and len(revisions)==2
    with pytest.raises(ValueError,match="precedes"):index_publications(events[1:],{"e:f1":packet})
    with pytest.raises(ValueError,match="Duplicate"):index_publications(events+[events[1]],{"e:f1":packet})
    broken=copy.deepcopy(events);broken[1]["cutoff_event_seq"]=5
    with pytest.raises(ValueError,match="cutoff"):index_publications(broken,{"e:f1":packet})
