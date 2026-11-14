from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).parents[3]/"src/graphAdapter/map_memory/tests"))
from test_perception import scene,payload,fuse

def test_cow_matches_original_and_keeps_parent_clouds_unchanged():
    parent=scene({"e:f1":payload(2),"e:f2":payload(1)})
    fuse(parent,"e:f1")
    before={oid:(np.asarray(obj["pcd"].points).copy(),list(obj["class_id"])) for oid,obj in parent.objects.items()}
    candidate=parent.fork(copy_on_write=True)
    reference=parent.fork()
    for oid,obj in parent.objects.items():
        assert candidate.objects[oid]["pcd"] is obj["pcd"]
        assert candidate.objects[oid] is not obj
    fuse(candidate,"e:f2",2);fuse(reference,"e:f2",2)
    assert candidate.copy_metrics["shared_clouds"]==len(before)
    assert candidate.copy_metrics["cloned_clouds"]<=1
    for oid,obj in parent.objects.items():
        np.testing.assert_array_equal(np.asarray(obj["pcd"].points),before[oid][0])
        assert obj["class_id"]==before[oid][1]
    for oid,obj in candidate.objects.items():
        np.testing.assert_array_equal(np.asarray(obj["pcd"].points),np.asarray(reference.objects[oid]["pcd"].points))
        np.testing.assert_array_equal(np.asarray(obj["pcd"].colors),np.asarray(reference.objects[oid]["pcd"].colors))
        assert obj["class_id"]==reference.objects[oid]["class_id"]
        assert obj["num_detections"]==reference.objects[oid]["num_detections"]
    assert candidate.members==reference.members and candidate.aliases==reference.aliases

def test_cow_cleanup_remains_parent_isolated():
    parent=scene({"e:f1":payload(2),"e:f2":payload(1)})
    fuse(parent,"e:f1")
    before={oid:np.asarray(obj["pcd"].points).copy() for oid,obj in parent.objects.items()}
    candidate=parent.fork(copy_on_write=True)
    reference=parent.fork()
    candidate.periodic_cleanup_objects(12,np.zeros(3))
    reference.periodic_cleanup_objects(12,np.zeros(3))
    for oid,obj in parent.objects.items():np.testing.assert_array_equal(np.asarray(obj["pcd"].points),before[oid])
    assert set(candidate.objects)==set(reference.objects)
    for oid,obj in candidate.objects.items():
        np.testing.assert_array_equal(np.asarray(obj["pcd"].points),np.asarray(reference.objects[oid]["pcd"].points))


def test_unchanged_object_blob_is_verified_and_reused(tmp_path,monkeypatch):
    from graphAdapter.map_memory.storage.store import EpisodeStore
    s=scene({"e:f1":payload(2)})
    fuse(s,"e:f1")
    store=EpisodeStore(tmp_path/"map","e",dataset="r2r")
    calls=[]
    original=store.put_arrays
    def tracked(arrays):
        calls.append(1)
        return original(arrays)
    monkeypatch.setattr(store,"put_arrays",tracked)
    try:
        state,_,_=s.snapshot(store,0)
        assert len(calls)==len(s.objects)
        again,_,_=s.snapshot(store,0)
        assert len(calls)==len(s.objects)
        assert state==again
        s.objects[1]["pcd"].translate([.01,0,0])
        s.snapshot(store,0)
        assert len(calls)==len(s.objects)+1
        assert s.copy_metrics["blob_hits"]>=len(s.objects)
    finally:store.close()
