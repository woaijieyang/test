"""Durability/read-only/causality component tests; not a navigation result."""
from pathlib import Path
import copy,json,time
import numpy as np
import pytest
from graphAdapter.map_memory.storage.store import (
    EpisodeStore,load_episode,encode_arrays,IntegrityError,NoPublishedSnapshot,
    VersionUnavailable,ConcurrentWriterError,ByteLRU,decode_arrays)

EP="ep-fixture"
def capture(seq,*,available=True):
    return dict(episode_uid=EP,frame_uid=EP+f":f{seq:06d}",capture_seq=seq,event_seq=seq*10,
        env_step=seq-1,pose_record=dict(geometry_status="available"if available else"unavailable"),
        action=dict(action_id=1 if seq>1 else None,terminal=False),capture_monotonic_ns=seq)
def arrays():
    return np.zeros((8,8,3),np.uint8),np.ones((4,4),np.float32),np.ones((8,8),np.float32),np.ones((8,8),bool)
def archive(store,seq,**kw):
    meta=capture(seq,**kw);rgb,raw,aligned,mask=arrays()
    return store.archive_frame(meta,rgb,raw,aligned,mask,host_view=rgb,host_transform={"kind":"identity"})
def graph(seqs,version=0):
    return dict(episode_uid=EP,views={capture(s)["frame_uid"]:dict(frame_uid=capture(s)["frame_uid"],
        capture_seq=s,position_G=[0.,0.,float(-s)],pose_map_version=version)for s in seqs},
        entities=[],aliases=[],edges=[],tiles={},contributions=[])
def publish(store,seqs,version=0,**kw):
    return store.publish(graph(seqs,version),{"pose_map_version":version},
                         {"capture_seq":max(seqs),"event_seq":max(seqs)*10},**kw)

def test_G00_G10_raw_reload_current_pin_and_no_future(tmp_path):
    s=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        archive(s,1);p1=publish(s,[1])
        old=load_episode(s.root)
        archive(s,2);p2=publish(s,[1,2],1)
        archive(s,3)
        current=load_episode(s.root)
        assert old.snapshot_id==p1["snapshot_id"] and current.snapshot_id==p2["snapshot_id"]
        assert old.get_view(capture(1)["frame_uid"])["pose_map_version"]==0
        assert current.get_view(capture(1)["frame_uid"])["pose_map_version"]==1
        with pytest.raises(KeyError):old.get_view(capture(2)["frame_uid"])
        with pytest.raises(KeyError):current.get_view(capture(3)["frame_uid"])
        with pytest.raises(VersionUnavailable):old.require_pose_version(EP,1)
        view=current.get_view(capture(1)["frame_uid"],include_depth=True)
        assert np.array_equal(view["raw_rgb"],view["host_view"])
        with pytest.raises(ValueError):view["raw_rgb"].setflags(write=True)
        with pytest.raises(TypeError):view["position_G"][0]=100
        assert current.verify()["views"]==2
        old.close();current.close()
    finally:s.close()

def test_G10_writer_exclusion_and_explicit_orphan_revision_rejected(tmp_path):
    s=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        with pytest.raises(ConcurrentWriterError):EpisodeStore(s.root,EP,dataset="r2r",create=False)
        archive(s,1);publish(s,[1]);archive(s,2)
        def fault(stage):
            if stage=="sqlite_prepared_committed":raise OSError("pre-pointer crash")
        with pytest.raises(OSError):publish(s,[1,2],1,fault=fault)
        orphan=s.pages.db.execute("SELECT id FROM revisions WHERE id!=?",(s.current["snapshot_id"],)).fetchone()[0]
        r=load_episode(s.root)
        with pytest.raises(KeyError):r.get_view(capture(2)["frame_uid"])
        with pytest.raises(NoPublishedSnapshot):load_episode(s.root,revision=orphan)
        r.close()
    finally:s.close()

def test_G06_prepared_retry_is_idempotent_not_sql_duplicate(tmp_path):
    root=tmp_path/"episode";s=EpisodeStore(root,EP,dataset="r2r")
    archive(s,1);publish(s,[1]);archive(s,2)
    def fault(stage):
        if stage=="sqlite_prepared_committed":raise OSError("crash")
    with pytest.raises(OSError):publish(s,[1,2],1,fault=fault)
    s.close();s=EpisodeStore(root,EP,dataset="r2r",create=False)
    try:
        result=publish(s,[1,2],1)
        r=load_episode(root);assert r.snapshot_id==result["snapshot_id"]
        assert r.verify()["views"]==2;r.close()
    finally:s.close()

def test_G06_raw_duplicate_or_changed_payload(tmp_path):
    s=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        first=archive(s,1);second=archive(s,1)
        assert first==second
        rgb,raw,aligned,mask=arrays()
        with pytest.raises(IntegrityError):s.archive_frame(capture(1),rgb+1,raw,aligned,mask)
        assert np.array_equal(s.read_rgb(capture(1)["frame_uid"]),rgb)
    finally:s.close()

def test_G09_visual_only_not_retroactively_spatial_and_mixed_version_rejected(tmp_path):
    s=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        archive(s,1,available=False)
        with pytest.raises(IntegrityError):publish(s,[1])
        g=graph([1]);g["views"][capture(1)["frame_uid"]]["position_G"]=None
        s.publish(g,{"pose_map_version":None},{"capture_seq":1,"event_seq":10})
        archive(s,2)
        g=graph([1,2]);g["views"][capture(1)["frame_uid"]]["position_G"]=None
        g["views"][capture(2)["frame_uid"]]["pose_map_version"]=7
        with pytest.raises(IntegrityError):s.publish(g,{"pose_map_version":0},{"capture_seq":2,"event_seq":20})
    finally:s.close()

def test_G14_content_addressing_and_codec_shape_checksum_no_pickle(tmp_path):
    s=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        data={"mask":np.ones((4,4),bool),"points":np.zeros((2,3),np.float32)}
        a=s.put_arrays(data);time.sleep(.02);b=s.put_arrays(data)
        assert a==b and len(list((s.root/"blobs").glob("*")))==1
        restored=s.get_arrays(a)
        assert restored["points"].shape==(2,3)
        with pytest.raises(ValueError):restored["points"].setflags(write=True)
        wrong=copy.deepcopy(a);wrong["arrays"]["mask"]["shape"]=[2,8]
        with pytest.raises(IntegrityError):s.get_arrays(wrong)
        with pytest.raises(IntegrityError):s.put_arrays({"object":np.asarray([object()])})
        target=s.root/a["path"];target.write_bytes(b"corrupted")
        with pytest.raises(IntegrityError):s.get_arrays(a)
    finally:s.close()

def test_G14_byte_lru_bounded(tmp_path):
    cache=ByteLRU(100)
    for n in range(10):
        value=cache.get(str(n),lambda:np.zeros(60,np.uint8))
        assert value.nbytes==60 and cache.bytes<=100 and len(cache.items)==1

def test_G00_execution_unique_post_and_pinned_trace(tmp_path):
    s=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        archive(s,1);archive(s,2);archive(s,3)
        a=dict(pre=capture(1)["frame_uid"],post=capture(2)["frame_uid"],macro=1,primitive=1,action_id=1)
        s.add_execution(a);s.add_execution(a)
        changed=dict(a,action_id=2)
        with pytest.raises(IntegrityError):s.add_execution(changed)
        publish(s,[1,2])
        r=load_episode(s.root);assert len(r.get_trace())==1;r.close()
    finally:s.close()

def test_G07_alias_resolution_retired_and_readonly(tmp_path):
    s=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        archive(s,1)
        g=graph([1]);uid=capture(1)["frame_uid"]
        g["entities"]=[dict(epoch="a",id=1,status="alias",view_uids=[],pose_map_version=None),
                       dict(epoch="a",id=2,status="active",view_uids=[uid],pose_map_version=0)]
        g["aliases"]=[dict(epoch="a",src=1,dst_epoch="a",dst=2,status="alias")]
        s.publish(g,{"pose_map_version":0},{"capture_seq":1,"event_seq":10})
        r=load_episode(s.root);obj=r.get_object("a",1)
        assert obj["id"]==2 and obj["requested"]==("a",1)
        with pytest.raises(TypeError):obj["status"]="other"
        r.close()
    finally:s.close()


@pytest.mark.parametrize("stage",[
 "raw_rgb_tmp_fsynced","raw_rgb_renamed","raw_depth_tmp_fsynced","raw_depth_renamed",
 "raw_meta_tmp_fsynced","raw_meta_renamed","raw_index_committed",
 "before_sql_commit","after_sql_commit","after_current_tmp_fsync",
 "after_current_replace","after_current_dir_fsync","memory_installed"])
def test_G10_actual_sigkill_every_publication_boundary_and_reload(tmp_path,stage):
    import subprocess,sys
    root=tmp_path/"episode";s=EpisodeStore(root,EP,dataset="r2r")
    archive(s,1);first=publish(s,[1]);s.close()
    before=(root/"observations"/(capture(1)["frame_uid"]+".rgb.png")).read_bytes()
    script=r'''
import os,signal,sys,numpy as np
from graphAdapter.map_memory.storage.store import EpisodeStore
root,stage=sys.argv[1:];ep="ep-fixture";uid=ep+":f000002"
def stop(point):
    if point==stage:os.kill(os.getpid(),signal.SIGKILL)
s=EpisodeStore(root,ep,dataset="r2r",create=False)
meta=dict(episode_uid=ep,frame_uid=uid,capture_seq=2,event_seq=20,env_step=1,
 pose_record=dict(geometry_status="available"),action=dict(action_id=1,terminal=False),capture_monotonic_ns=2)
rgb=np.zeros((8,8,3),np.uint8);raw=np.ones((4,4),np.float32)
depth=np.ones((8,8),np.float32);mask=np.ones((8,8),bool)
s.archive_frame(meta,rgb,raw,depth,mask,host_view=rgb,host_transform={"kind":"identity"},fault=stop)
views={ep+":"+f"f{x:06d}":dict(frame_uid=ep+":"+f"f{x:06d}",capture_seq=x,
 position_G=[0.,0.,float(-x)],pose_map_version=1)for x in (1,2)}
graph=dict(episode_uid=ep,views=views,entities=[],aliases=[],edges=[],tiles={},contributions=[])
s.publish(graph,{"pose_map_version":1},{"capture_seq":2,"event_seq":20},fault=stop)
raise RuntimeError("Requested fault boundary was not executed")
'''
    result=subprocess.run([sys.executable,"-B","-c",script,str(root),stage],capture_output=True,text=True,timeout=30)
    assert result.returncode==-9,(stage,result.returncode,result.stdout,result.stderr)
    after=load_episode(root)
    committed=stage in {"after_current_replace","after_current_dir_fsync","memory_installed"}
    if committed:
        assert after.snapshot_id!=first["snapshot_id"]
        assert after.get_view(capture(2)["frame_uid"])["pose_map_version"]==1
    else:
        assert after.snapshot_id==first["snapshot_id"]
        with pytest.raises(KeyError):after.get_view(capture(2)["frame_uid"])
    after.verify();after.close()
    assert before==(root/"observations"/(capture(1)["frame_uid"]+".rgb.png")).read_bytes()
    resumed=EpisodeStore(root,EP,dataset="r2r",create=False)
    try:
        archive(resumed,2)
        if not committed:publish(resumed,[1,2],1)
    finally:resumed.close()
    reader=load_episode(root)
    assert reader.verify()["views"]==2;reader.close()

def test_G05_actual_disk_backing_reloads_core_only_without_halo_double_ownership(tmp_path):
    from graphAdapter.map_memory.geometry.core import TSDFSubmapManager,S
    s=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        archive(s,1)
        rgb,raw,depth,mask=arrays()
        depth=np.full_like(depth,2.13);k=np.array([[4.,0,3.5],[0,4.,3.5],[0,0,1.]])
        m=TSDFSubmapManager([0,0,0],voxel_size=.25,core_size=(2,2,2),max_resident_tiles=2,backing=s)
        m.integrate(capture(1)["frame_uid"],rgb,depth,mask,k,S,source_hash="source")
        state=m.export()
        restored=TSDFSubmapManager.restore(state,backing=s)
        assert restored.frames==m.frames and restored.records.keys()==m.records.keys()
        g=graph([1])
        g["tiles"]={m.identifier(key):dict(pose_map_version=0,record=ref)for key,ref in m.records.items()}
        s.publish(g,{"pose_map_version":0},{"capture_seq":1,"event_seq":10})
        reader=load_episode(s.root)
        for key in m.records:
            tile_id=m.identifier(key)
            a=m.core_arrays(tile_id,snapshot_id=reader.snapshot_id)["arrays"]
            b=restored.core_arrays(tile_id,snapshot_id=reader.snapshot_id)["arrays"]
            published=reader.get_geometry(tile_id)["arrays"]
            for name in a:
                np.testing.assert_array_equal(a[name],b[name])
                np.testing.assert_array_equal(a[name],published[name])
                assert published[name].shape==(8,8,8)
        assert len(restored._cache)<=2
        reader.close()
    finally:s.close()

def test_G00_sql_payload_tamper_and_raw_orphan_excluded(tmp_path,tamper_page):
    s=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        archive(s,1);publish(s,[1])
        uid=capture(1)["frame_uid"]
        tamper_page(s.root,s.current["snapshot_id"],("graph","views",uid))
        reader=load_episode(s.root)
        with pytest.raises(IntegrityError):reader.get_view(uid)
        reader.close()
    finally:s.close()


def epoch_graph(seqs,epoch,native_id,previous=None,retired=False):
    g=graph(seqs,len(seqs)-1);g["scene_state"]={"epoch":epoch}
    g["entities"]=[dict(epoch=epoch,id=native_id,status="active",members=[],view_uids=[],pose_map_version=len(seqs)-1)]
    if previous:
        old_epoch,old_id=previous
        g["entities"].append(dict(epoch=old_epoch,id=old_id,status="retired"if retired else"alias",
            attributes=None,view_uids=[],pose_map_version=None))
        g["aliases"]=[dict(epoch=old_epoch,src=old_id,dst_epoch=None if retired else epoch,
            dst=None if retired else native_id,status="retired"if retired else"alias")]
    return g

def test_G07_G09_pinned_ancestor_aliases_reach_current_and_reject_future_or_orphan(tmp_path,tamper_page):
    s=EpisodeStore(tmp_path/"episode",EP,dataset="r2r");readers=[]
    try:
        pointers=[]
        for seq,epoch,native_id,previous in [(1,"a",1,None),(2,"b",2,("a",1)),(3,"c",3,("b",2))]:
            archive(s,seq)
            pointers.append(s.publish(epoch_graph(list(range(1,seq+1)),epoch,native_id,previous),
                {"pose_map_version":seq-1},{"capture_seq":seq,"event_seq":seq*10}))
            readers.append(load_episode(s.root))
        assert readers[2].get_object("a",1)["epoch"]=="c"
        assert readers[1].get_object("a",1)["epoch"]=="b"
        assert readers[0].get_object("a",1)["epoch"]=="a"
        with pytest.raises(KeyError):readers[0].get_object("c",3)
        archive(s,4)
        p4=s.publish(epoch_graph([1,2,3,4],"d",4,("c",3),retired=True),
            {"pose_map_version":3},{"capture_seq":4,"event_seq":40})
        latest=load_episode(s.root);readers.append(latest)
        retired=latest.get_object("a",1)
        assert retired["status"]=="retired"and retired["attributes"]is None and retired["pose_map_version"]is None
        archive(s,5)
        def fail(stage):
            if stage=="sqlite_prepared_committed":raise OSError("orphan")
        with pytest.raises(OSError):
            s.publish(epoch_graph([1,2,3,4,5],"future",9,("a",1)),{"pose_map_version":4},
                {"capture_seq":5,"event_seq":50},fault=fail)
        # Even the same requested key in a prepared future branch cannot change a pinned result.
        assert latest.get_object("a",1)["status"]=="retired"
        assert readers[2].get_object("a",1)["epoch"]=="c"
        tamper_page(s.root,pointers[1]["snapshot_id"],("aliases","a:1"))
        with pytest.raises(IntegrityError):list(latest.iter_verified_history())
    finally:
        for reader in readers:reader.close()
        s.close()


def test_G07_alias_cycle_never_becomes_current(tmp_path):
    s=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        archive(s,1);publish(s,[1]);before=(s.root/"CURRENT.json").read_bytes()
        bad=graph([1]);bad["entities"]=[dict(epoch="a",id=i,status="alias",view_uids=[],pose_map_version=None)for i in (1,2)]
        bad["aliases"]=[dict(epoch="a",src=1,dst_epoch="a",dst=2,status="alias"),
            dict(epoch="a",src=2,dst_epoch="a",dst=1,status="alias")]
        with pytest.raises(IntegrityError,match="alias_cycle"):
            s.publish(bad,{"pose_map_version":0},{"capture_seq":1,"event_seq":10})
        assert before==(s.root/"CURRENT.json").read_bytes()
    finally:s.close()

def test_persistent_history_indexes_preserve_literal_versions_and_old_roots(tmp_path):
    import random
    from graphAdapter.map_memory.storage.pages import BundlePages,SelectiveReader
    from graphAdapter.map_memory.storage.store import canonical,digest
    rng=random.Random(20261108);writer=BundlePages(tmp_path/"maps")
    maps={k:{}for k in ("facts","executions","entities","aliases")}
    old=None
    try:
        for version in range(40):
            changes={k:{}for k in maps}
            for collection in maps:
                for _ in range(12):
                    key=str(rng.randrange(300))
                    value=dict(epoch="epoch-"+str(version),pose_map_version=version,
                        snapshot_hash="binding-"+str(version),nested=[key,version,None])
                    maps[collection][key]=value;changes[collection][key]=value
            graph=dict(versions=dict(pose_map_version=version),pose_bindings=dict(map_version=version),
                scene_state=dict(epoch="epoch-"+str(version)),entities=[])
            public=dict(versions=graph["versions"],cutoff=dict(capture_seq=version+1,event_seq=version+1),
                episode_uid="maps",storage_codec="literal_history_v1")
            bundle=dict(graph=graph,public=public,**maps)
            writer.publish(bundle,digest(canonical(public)),public=public,changes=changes)
            reader=SelectiveReader(writer.root)
            try:assert canonical(reader.graph())==canonical(bundle)
            finally:reader.close()
            if version==0:old=SelectiveReader(writer.root);first=canonical(old.graph())
        assert canonical(old.graph(force=True))==first
    finally:
        if old is not None:old.close()
        writer.close()

def test_gc_rejects_corrupt_child_index_before_removing_any_page(tmp_path):
    s=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    try:
        archive(s,1);publish(s,[1])
        root=s.current["root"]
        row=s.pages.db.execute("SELECT children FROM nodes WHERE id=?",(root,)).fetchone()[0]
        count=s.pages.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        assert row!="[]"
        s.pages.db.execute("UPDATE nodes SET children='[]'WHERE id=?",(root,))
        try:
            with pytest.raises(IntegrityError,match="child index"):s.pages.gc()
            assert s.pages.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]==count
        finally:s.pages.db.execute("UPDATE nodes SET children=?WHERE id=?",(row,root))
        assert s.pages.gc()["published_roots_kept"]==1
    finally:s.close()

def test_failed_raw_constructor_releases_its_writer_lock_even_with_retained_traceback(tmp_path,monkeypatch):
    from graphAdapter.map_memory.storage import archive as raw
    path=tmp_path/"episode";original=raw._write_immutable
    def fail(*args,**kwargs):raise OSError("injected raw initialization failure")
    monkeypatch.setattr(raw,"_write_immutable",fail)
    with pytest.raises(OSError)as held:EpisodeStore(path,EP,dataset="r2r")
    monkeypatch.setattr(raw,"_write_immutable",original)
    recovered=EpisodeStore(path,EP,dataset="r2r",create=False)
    try:assert held.value.args==("injected raw initialization failure",)
    finally:recovered.close()

def test_failed_page_constructor_releases_its_writer_lock_even_with_retained_traceback(tmp_path,monkeypatch):
    from graphAdapter.map_memory.storage import pages
    path=tmp_path/"pages";original=pages.sqlite3.connect
    def fail(*args,**kwargs):raise OSError("injected page initialization failure")
    monkeypatch.setattr(pages.sqlite3,"connect",fail)
    with pytest.raises(OSError)as held:pages.BundlePages(path)
    monkeypatch.setattr(pages.sqlite3,"connect",original)
    recovered=pages.BundlePages(path,create=False)
    try:assert held.value.args==("injected page initialization failure",)
    finally:recovered.close();recovered.close()

def test_close_is_idempotent_releases_reader_pins_and_owned_caches(tmp_path):
    s=EpisodeStore(tmp_path/"episode",EP,dataset="r2r")
    archive(s,1);publish(s,[1])
    reader=load_episode(s.root);reader.get_view(capture(1)["frame_uid"],include_depth=True)
    reader.close();reader.close()
    assert s.pages.gc()["published_roots_kept"]==1
    root=s.root;s.close();s.close()
    assert s.pages is None and s.raw_materializer is None and not s._facts
    reopened=EpisodeStore(root,EP,dataset="r2r",create=False)
    reopened.close()


def test_narrow_execution_read_reuses_pinned_key_and_respects_historical_cutoff(tmp_path):
    store=EpisodeStore(tmp_path/'ep',EP,dataset='r2r')
    try:
        for seq in range(1,10):
            archive(store,seq)
            if seq>1 and seq!=7:
                store.add_execution(dict(pre=capture(seq-1)['frame_uid'],post=capture(seq)['frame_uid'],
                    macro=seq,primitive=1,action_id=1))
            if seq==8:previous=publish(store,list(range(1,9)))['snapshot_id']
        publish(store,list(range(1,10)))
    finally:store.close()
    reader=load_episode(store.root,previous)
    try:
        full=reader.get_trace()
        def reject():raise AssertionError('Narrow read expanded the whole execution map')
        reader._executions.values=reject
        assert list(reader.get_trace(7,9))==[full[-1]]
        assert not reader.get_trace(1,1) and not reader.get_trace(9,9)
    finally:reader.close()
