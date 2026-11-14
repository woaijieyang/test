from types import SimpleNamespace
import numpy as np
import pytest
from graphAdapter.map_memory.retrieval import semantic_topology as topology
from graphAdapter.map_memory.storage.store import IntegrityError


def test_causal_semantic_topology_and_binding(monkeypatch):
    graph = dict(views={"f1": {"capture_seq": 1}}, entities=[dict(id=3,status="active",members=["f1:d00000"])],
                 scene_state={"objects":[dict(id=3,class_name="bed",bbox={"kind":"aabb"},num_detections=1)]},
                 vsm=dict(anchors={"f1":dict(objects=[3],position=[0,0,0],room_type_hint="bedroom")},
                          visibility_edges=[("f1",3)]), edges=[])
    reader = SimpleNamespace(_graph=graph, identity={"episode_uid":"one"}, snapshot_id="pin",
                             cutoff={"capture_seq":1}, versions={"pose_map_version":0})
    monkeypatch.setattr(topology, "slice_points", lambda r,h:(np.array([[1.,2.,3.]]),np.array([1]),{"floor_id":None}))
    def read(**overrides):
        opts=dict(episode_uid="one",snapshot_id="pin",decision_capture_seq=2)
        return topology.read_semantic_topology(reader,**dict(opts,**overrides))
    reader.get_view_class_ids=lambda uid:dict(status="unavailable")
    result=read()
    def reject_slice(*args):
        raise AssertionError("Selection-only read touched geometry tiles")
    with monkeypatch.context() as m:
        m.setattr(topology,"slice_points",reject_slice)
        menu=topology.TopologyMenu.from_reader(reader,episode_uid="one",snapshot_id="pin",decision_capture_seq=2,decision_id=4)
        assert menu.entries==[]

    assert result["points"]==[[1.,3.]] and result["states"]==[1]
    assert result["visibility"]==[["f1",3]] and result["objects"][0]["sources"]==["f1:d00000"]
    for args in [dict(episode_uid="two"),dict(snapshot_id="other"),dict(decision_capture_seq=0)]:
        with pytest.raises(IntegrityError):read(**args)
    reader.cutoff["capture_seq"]=3
    with pytest.raises(IntegrityError):read()
    reader.cutoff["capture_seq"]=1
    graph["vsm"]["visibility_edges"]=[]
    with pytest.raises(IntegrityError):read()


def test_coverage_unknown_duplicate_and_conflict():
    d=dict(geometry_slice=dict(voxel_size_m=.1,sampled_height_m=.2),
           views={"v":dict(base=np.eye(4))},points=[[0,0],[0,0],[0,0],[.1,0],[1.,1.]],states=[1,1,2,1,2])
    stats=topology.coverage_at_view(d,"v",radius_cells=1)
    assert [stats[k] for k in ("unknown","free","surface","conflict")]==[7,1,0,1]
    d["points"]=[];d["states"]=[]
    assert topology.coverage_at_view(d,"v",radius_cells=1)["unknown"]==9

def test_menu_strict_scope_and_same_frame_decisions():
    d=dict(episode_uid="ep",snapshot_id="pin",cutoff={"capture_seq":2},
           objects=[dict(id=3,label="bed",sources=["view:d00000"])],
           views={"view":{"seq":2}},visibility=[["view",3]],
           anchors=[dict(uid="view",objects=[3],room="bedroom")])
    scope=dict(episode_uid="ep",snapshot_id="pin",decision_capture_seq=4,decision_id=10)
    m=topology.TopologyMenu(d,**scope)
    assert m.resolve("A",**scope)==("view",("view:d00000",))
    assert m.resolve("NONE",**scope) is None
    assert m.suggested_view("leave the bedroom", "in the bedroom")=="A"
    assert m.suggested_view("leave the bedroom", "turn right") is None
    assert m.suggested_view("leave the bedroom", None) is None
    finished = "<BEGIN_OF_REASONING> I have passed the bed. The next plan is to turn right."
    assert m.suggested_view("pass the bed and turn right", finished) is None
    assert m.suggested_view("leave the bedroom", "<BEGIN_OF_REASONING> I am in the bedroom.") is None
    future = "<BEGIN_OF_REASONING> I finished turning. The next plan is to face the bed."
    assert m.suggested_view("turn then face the bed", future) == "A"
    assert m.suggested_view("face the bed", future.replace("to face", "to avoid")) is None
    with pytest.raises(ValueError):m.resolve("turn right",**scope)
    with pytest.raises(IntegrityError):m.resolve("A",**dict(scope,decision_id=11))



def test_landmark_position_uses_unique_class_consistent_owner_and_current_optical_pose():
    old=SimpleNamespace(identity={"episode_uid":"ep"},snapshot_id='old',cutoff={"capture_seq":4},versions={"pose_map_version":0})
    T=np.eye(4);T[0,3]=1
    live=SimpleNamespace(identity=old.identity,snapshot_id="now",cutoff={"capture_seq":5},
        get_view=lambda *a,**k:dict(capture={"episode_uid":"ep"},frame_uid="f5",capture_seq=5,snapshot_id="now",pose_map_version=0,T_G_cv=T))
    member="f2:d00003"
    obj=dict(epoch="e",id=2,status="active",members=[member],pose_map_version=0,
             attributes=dict(class_name="bed",class_id=[0,0],bbox=dict(kind="aabb",minimum=[2.,0,4.],maximum=[4.,1.,6.])))
    old._graph=dict(entities=[obj],scene_state={"epoch":"e"},vsm={"visibility_edges":[["f2",2]]})
    cue=SimpleNamespace(episode_uid="ep",snapshot_id="old",source_snapshot_id="now",frame_uid="f5",capture_seq=5,pose_map_version=0)
    attachment=SimpleNamespace(record=SimpleNamespace(source_refs=(member,)),slot=SimpleNamespace(index=9,frame_uid="f2",env_step=1,sensor_seq=2,source_snapshot_id="old"))
    call=lambda:topology.selected_object_position(old,live,cue,attachment,SimpleNamespace(landmark="bed",observed_step=1),SimpleNamespace(labels=("bed","chair")))
    fields,proof=call();assert fields==dict(right_m=2.,forward_m=5.) and proof["center_G"]==[3.,.5,5.]
    obj['attributes']['class_id']=[0,1];assert call() is None
    obj['attributes']['class_id']=[0];cue.pose_map_version=1;assert call() is None
    cue.pose_map_version=0;old._graph['entities'].append(dict(obj,id=3));assert call() is None
    old.cutoff['capture_seq']=6
    with pytest.raises(IntegrityError):call()

    

def test_menu_keeps_anchor_detection_separate_from_fused_entity_label():
    scope=dict(episode_uid="ep",snapshot_id="pin",decision_capture_seq=3,decision_id=1)
    d=dict(episode_uid="ep",snapshot_id="pin",cutoff={"capture_seq":2},
           objects=[dict(id=1,label="window",sources=["old:d00000","new:d00001"])],
           views={"old":{"seq":1},"new":{"seq":2}},visibility=[["new",1]],
           anchors=[dict(uid="new",objects=[1],room="unknown")])
    legacy=topology.TopologyMenu(d,**scope)
    assert legacy.entries[0]["label_scope"]=="aggregate_only"
    d["anchor_detection_labels"]={"new":{"new:d00001":"coffee kettle"}}
    menu=topology.TopologyMenu(d,**scope)
    assert menu.entries[0]["objects"]==["coffee kettle"] and menu.entries[0]["label_scope"]=="anchor_detections"
    assert menu.resolve("A",**scope)==("new",("new:d00001",))
    d["anchor_detection_labels"]={"new":{}}
    assert not topology.TopologyMenu(d,**scope).entries



def test_menu_display_mutations_do_not_change_selected_source():
    d=dict(episode_uid="ep",snapshot_id="pin",cutoff={"capture_seq":2},
           objects=[dict(id=3,label="chair",sources=["view:d00000"])],views={"view":{"seq":2}},
           visibility=[["view",3]],anchors=[dict(uid="view",objects=[3],room="office")],
           anchor_detection_labels={"view":{"view:d00000":"bench"}})
    scope=dict(episode_uid="ep",snapshot_id="pin",decision_capture_seq=4,decision_id=10)
    m=topology.TopologyMenu(d,**scope)
    exposed=m.entries;exposed[0]["objects"].append("bed");exposed[0]["option"]="B"
    assert m.entries[0]["option"]=="A" and m.entries[0]["objects"]==["bench"]
    assert m.materialize("NONE",None,**scope) is None
    with pytest.raises(IntegrityError):
        m.materialize("A",SimpleNamespace(identity={"episode_uid":"wrong"},snapshot_id="pin"),**scope)


@pytest.mark.parametrize("record_uid,record_pin",[("other","pin"),("view","older")])
def test_menu_rejects_swapped_detector_rows(record_uid,record_pin):
    scope=dict(episode_uid="ep",snapshot_id="pin",decision_capture_seq=4,decision_id=10)
    data=dict(episode_uid="ep",snapshot_id="pin",cutoff={"capture_seq":2},
              objects=[dict(id=1,label="bench",sources=["view:d00000"])],
              views={"view":{"seq":2}},visibility=[["view",1]],
              anchors=[dict(uid="view",objects=[1],room="unknown")],
              anchor_detection_labels={"view":{"view:d00000":"bench"}})
    menu=topology.TopologyMenu(data,**scope)
    source=dict(status="available",capture_seq=2,snapshot_id=record_pin,frame_uid=record_uid)
    reader=SimpleNamespace(identity={"episode_uid":"ep"},snapshot_id="pin",
                           get_view_class_ids=lambda *args,**kwargs:source)
    with pytest.raises(IntegrityError,match="detection record differs"):
        menu.materialize("A",reader,**scope)

def test_anchor_uses_object_membership_before_detector_confidence():
    from graphAdapter.map_memory.retrieval.semantic_topology import visible_detection_owners
    from graphAdapter.map_memory.retrieval.candidates import propose_anchor
    uid='a'
    graph=dict(scene_state={'epoch':'active'},vsm=dict(anchors={uid:{'objects':[8]}},visibility_edges=[(uid,8)]),
               entities=[dict(id=8,epoch='active',status='active',members=['a:d00001']),
                         dict(id=9,epoch='active',status='active',members=['a:d00002']),
                         dict(id=3,epoch='old',status='retired',members=['a:d00000'])])
    rd=SimpleNamespace(_graph=graph,get_view_class_ids=lambda uid,*,include_confidence:dict(status='available',
        class_ids=[0,0,0],confidence=[.99,.71,.88]))
    assert visible_detection_owners(rd,uid)=={1:8}
    with pytest.raises(TypeError):visible_detection_owners(rd,uid)[0]=3
    nodes=[SimpleNamespace(frame_uid=uid,capture_seq=1)]
    result=propose_anchor(nodes,SimpleNamespace(capture_seq=4),graph['vsm'],rd,SimpleNamespace(labels=['bed']),
                          'approach the bed',8,native_uids=set(),query_cues=('bed',))
    assert result==[dict(kind='landmark',uid='a',index=1,label='bed')]
    from graphAdapter.map_memory.retrieval.host_decision import verify_anchor_proposal
    receipt=dict(epoch='active',object_id=8,member='a:d00001')
    reply=dict(additional_evidence=result,anchor_object=receipt)
    assert verify_anchor_proposal(rd,reply)==receipt
    for bad in (dict(receipt,object_id=9),dict(receipt,epoch='old'),dict(receipt,member='a:d00002')):
        with pytest.raises(IntegrityError):verify_anchor_proposal(rd,dict(reply,anchor_object=bad))
    with pytest.raises(IntegrityError):verify_anchor_proposal(rd,dict(reply,additional_evidence=[]))
    with pytest.raises(IntegrityError):verify_anchor_proposal(rd,dict(reply,additional_evidence=[dict(result[0],index=0)]))
    graph['entities'].append(dict(id=10,epoch='active',status='active',members=['a:d00001']))
    with pytest.raises(IntegrityError,match='owned'):
        visible_detection_owners(SimpleNamespace(_graph=graph),'a')
    graph['vsm']['visibility_edges']=[]
    with pytest.raises(IntegrityError,match='visibility'):
        visible_detection_owners(SimpleNamespace(_graph=graph),'a')

def test_matching_native_slot_requires_the_same_member_class_revision_and_pixel_grid():
    from graphAdapter.map_memory.retrieval.semantic_topology import native_object_slot
    vocabulary=SimpleNamespace(labels=['chair','couch'],source_sha256='v')
    owner=dict(epoch='e',object_id=7,member='old:d00000')
    obj=dict(epoch='e',id=7,status='active',members=['old:d00000','first:d00000','last:d00001'])
    def slot(uid,index,seq):
        return SimpleNamespace(frame_uid=uid,index=index,sensor_seq=seq,env_step=seq-1,source_snapshot_id='p',raw_pixel_hash='h',host_pixel_hash='h')
    hist=SimpleNamespace(snapshot_id='p',slots=[slot('first',1,2),slot('last',2,4)],
                         images=[SimpleNamespace(size=(8,8)),SimpleNamespace(size=(8,8))])
    data=dict(first=dict(status='available',frame_uid='first',capture_seq=2,snapshot_id='p',class_ids=[1],xyxy=[[0,0,2,2]],model_identity={'vocabulary_sha256':'v'}),
              last=dict(status='available',frame_uid='last',capture_seq=4,snapshot_id='p',class_ids=[1,0],xyxy=[[0,0,4,4],[2,2,5,5]],model_identity={'vocabulary_sha256':'v'}))
    rd=SimpleNamespace(snapshot_id='p',cutoff={'capture_seq':4},get_object=lambda *args,**kw:obj,get_view_class_ids=lambda uid,**kw:data[uid])
    match=lambda:native_object_slot(rd,hist,owner,'couch',vocabulary)
    assert match()['slot']==1  # latest image also detects couch, but for another member
    data['last']['class_ids'][1]=1
    assert match()==dict(slot=2,step=3,member='last:d00001',box_xyxy=(2,2,5,5))
    hist.slots[1].source_snapshot_id='future';hist.slots[0].host_pixel_hash='resized'
    assert match() is None
    hist.slots[1].source_snapshot_id='p';data['last']['capture_seq']=5
    with pytest.raises(IntegrityError):match()
    data['last']['capture_seq']=4;obj['status']='retired'
    with pytest.raises(IntegrityError):match()


def test_same_class_menu_members_require_unique_owners():
    scope=dict(episode_uid="e",snapshot_id="s",decision_capture_seq=3,decision_id=2)
    d=dict(episode_uid="e",snapshot_id="s",cutoff={"capture_seq":2},
           objects=[dict(id=1,label="mat",sources=["v:d00000"]),dict(id=2,label="mat",sources=["v:d00001"])],
           views={"v":{"seq":2}},visibility=[["v",1],["v",2]],anchors=[dict(uid="v",objects=[1,2],room="bathroom")],
           anchor_detection_labels={"v":{"v:d00000":"mat","v:d00001":"mat"}})
    menu=topology.TopologyMenu(d,**scope)
    assert menu.resolve("A",**scope)[1]==("v:d00000","v:d00001")
    d["objects"][1]["sources"]=["v:d00000"]
    with pytest.raises(IntegrityError,match="more than once"):
        topology.TopologyMenu(d,**scope)


def test_ranked_landmarks_preserve_same_label_witnesses(monkeypatch):
    from graphAdapter.map_memory.retrieval.host_decision import checked_landmark_ranks
    vocab=SimpleNamespace(labels=("mat","chair"),source_sha256="v")
    def read(uid):
        return dict(status="available",frame_uid=uid,snapshot_id="pin",capture_seq={"first":2,"second":3}[uid],
                    class_ids=[0],model_identity={"vocabulary_sha256":"v"})
    rd=SimpleNamespace(snapshot_id="pin",cutoff={"capture_seq":3},get_view_class_ids=read)
    monkeypatch.setattr(topology,"visible_detection_owners",lambda reader,uid:{0:{"first":42,"second":56}[uid]})
    records=[dict(kind="landmark",uid=u,index=0,label="mat",object_id=oid) for u,oid in (("second",56),("first",42))]
    reply=dict(landmark_query_cues=["mat"],ranked_landmarks=records,channels={"EvoAnchor":["second","first"]},
               additional_evidence=[{k:v for k,v in records[0].items() if k!="object_id"}])
    def verify(response=reply,native=(),seq=4):
        return checked_landmark_ranks(rd,response,vocab,native,seq)
    assert [r["object_id"] for r in verify()]==[56,42]
    for key,value in [("object_id",56),("index",-1),("label","chair")]:
        with pytest.raises(IntegrityError):
            verify(dict(reply,ranked_landmarks=[records[0],dict(records[1],**{key:value})]))
    with pytest.raises(IntegrityError):verify(native=["first"])
    with pytest.raises(IntegrityError):verify(seq=3)
    with pytest.raises(IntegrityError):verify(dict(reply,additional_evidence=[]))


def test_competing_anchors_check_unranked_detections_without_reading_images(monkeypatch):
    vocab=SimpleNamespace(labels=("mat","chair"),source_sha256="v")
    views={key:{"capture_seq":i} for i,key in enumerate(("old","shown","now"),1)}
    graph={"vsm":{"anchors":dict.fromkeys(views)}, "views":views}
    owners={"old":{0:4},"shown":{0:4,1:9},"now":{0:17}}
    seen=[]
    def record(uid):
        seen.append(uid)
        return dict(frame_uid=uid,status="available",snapshot_id="pin",capture_seq=views[uid]["capture_seq"],
                    model_identity={"vocabulary_sha256":"v"},class_ids=[0,0])
    monkeypatch.setattr(topology,"visible_detection_owners",lambda reader,uid:owners[uid])
    rd=SimpleNamespace(_graph=graph,cutoff={"capture_seq":3},snapshot_id="pin",get_view_class_ids=record)
    first=dict(label="mat",object_id=4,frame_uid="old")
    check=lambda rows:topology.competing_anchor_member(rd,first,rows,vocab,3)
    assert check([first])["source"]["member"]=="shown:d00001" and seen==["shown"]
    seen.clear()
    assert check([first,dict(label="mat",object_id=9)])["origin"]=="ranked" and not seen
    rd.get_view_class_ids=lambda uid:dict(frame_uid=uid,snapshot_id="pin",status="unavailable")
    assert check([first])["status"]=="incomplete"
    owners["shown"]={0:4}
    assert check([first])["status"]=="no_competitor"
    graph["views"]["now"]["capture_seq"]=4
    with pytest.raises(IntegrityError):check([first])


def test_native_preflight_only_opens_matching_frame_and_rejects_wrong_pixels():
    v=SimpleNamespace(labels=['chair','couch'],source_sha256='vocab')
    owner=dict(epoch='e',object_id=4,member='old:d00000')
    obj=dict(id=4,epoch='e',status='active',members=['old:d00000','seen:d00003','other:d00000'])
    refs=[SimpleNamespace(episode_uid='ep',frame_uid=uid,source_snapshot_id='pin',capture_seq=i+1,env_step=i,
                          event_seq=10+i,image_hash='raw',host_image_hash='host') for i,uid in enumerate(['seen','other','live'])]
    pics=[np.full((3,4,3),i,dtype=np.uint8) for i in range(3)]
    opened=[]
    def view(uid,**flags):
        assert flags==dict(include_images=True,include_depth=False)
        opened.append(uid);ref=next(r for r in refs if r.frame_uid==uid);pic=pics[ref.env_step]
        return dict(snapshot_id='pin',frame_uid=uid,capture_seq=ref.capture_seq,raw_rgb_ref={'sha256':'raw'},
                    host_view_ref={'sha256':'host'},raw_rgb=pic.copy(),host_view=pic.copy(),
                    capture=dict(episode_uid='ep',frame_uid=uid,event_seq=ref.event_seq,env_step=ref.env_step))
    def classes(uid,**flags):
        seq=1 if uid=='seen' else 2
        return dict(status='available',frame_uid=uid,capture_seq=seq,snapshot_id='pin',class_ids=[0,0,0,1],
                    xyxy=[[0,0,4,3]]*4,model_identity={'vocabulary_sha256':'vocab'})
    rd=SimpleNamespace(snapshot_id='pin',cutoff={'capture_seq':2},get_object=lambda *a,**kw:obj,
                       get_view_class_ids=classes,get_view=view)
    def check(images):
        return topology.preflight_native_object(rd,refs,[None,'seen','other','live'],images,owner,'couch',v)
    assert check(pics)==dict(slot=2,step=0,member='seen:d00003',box_xyxy=(0,0,4,3))
    assert opened==['seen']
    with pytest.raises(IntegrityError,match='pixels differ'):check([pics[1],pics[0],pics[2]])
    rd.get_view=lambda u,**kw:dict(view(u,**kw),raw_rgb=pics[1])
    assert check(pics) is None
    rd.get_view=lambda u,**kw:dict(view(u,**kw),snapshot_id='wrong')
    with pytest.raises(IntegrityError,match='archive identity'):check(pics)
