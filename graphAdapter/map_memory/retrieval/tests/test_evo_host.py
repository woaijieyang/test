from types import SimpleNamespace as NS
import numpy as np
import pytest
from graphAdapter.map_memory.retrieval import evo_host as mod
from graphAdapter.map_memory.retrieval.host_decision import HostDecision
from graphAdapter.map_memory.retrieval.input_audit import separate_attachment_encoding
from graphAdapter.map_memory.retrieval.protocol import retrieval_settings

def test_budget_keeps_native_reference_and_relations_without_duplicate_rgb():
    anchor=dict(uid='f',step=1,room='hallway',evidence=[])
    proof=mod.PinnedEvidence(None,'pin','ep',dict(summary='=== Topo Memory (compact) ===',anchors=[anchor],coverage={}),{}, {})
    d=HostDecision(None,{},'native_plus_attachment',dict(evidence_policy='evo_topology'))
    d.history=NS(budget=8,snapshot_id='pin',images=tuple([None]*8),slots=tuple([NS(frame_uid=None,raw_pixel_hash=None,host_pixel_hash=None)]*7+[NS(frame_uid='f',index=8,raw_pixel_hash='same',host_pixel_hash='same')]))
    d.evo_evidence=proof;d.evo_cutoff_step=2
    logs=[]
    d.emit=lambda *args,**kw:logs.append((args,kw))
    from contextlib import contextmanager
    @contextmanager
    def unopened(*a):
        yield NS(identity={'episode_uid':'ep'})
    from unittest.mock import patch
    with patch.object(mod,'closing_reader',unopened):
        out=mod.compile_evo(d,'original',lambda s:s,lambda s:np.arange(len(s)//4),196,4096)
    assert 'native image 8' in out and '<image>' not in out and d.combined.budget==8
    assert logs[0][1]['attachment_slots']==0 and d.combined.images==d.history.images
    with patch.object(mod,'closing_reader',unopened):
        result=mod.compile_evo(d,'original',lambda s:s,lambda s:np.arange(4096),196,4096)
    assert result=='original' and d.history is None

def test_multi_attachment_encoder_preserves_original_batch_and_restores():
    import torch
    class Model:
        def __init__(self):self.sizes=[]
        def encode_images(self,x):
            self.sizes.append(len(x))
            return torch.ones((len(x),196,4))*len(x)
    m=Model();images=torch.zeros(10,3,4,4)
    with separate_attachment_encoding(m,8,2):
        features=m.encode_images(images)
        assert features.shape==(10,196,4) and torch.all(features[:8]==8) and torch.all(features[8:]==1)
    assert m.sizes==[8,1,1] and 'encode_images' not in vars(m)
    with pytest.raises(RuntimeError):
        with separate_attachment_encoding(m,8,2):
            raise RuntimeError('fault')
    assert 'encode_images' not in vars(m)

def test_source_baseline_and_relation_profile_are_explicit():
    from pathlib import Path
    import json
    root=Path(__file__).resolve().parents[2]/'profiles'
    base=json.loads((root/'001_evo_source_baseline.json').read_bytes())
    enhanced=json.loads((root/'001_evo_topology_candidate.json').read_bytes())
    b=retrieval_settings(base['map_memory']);e=retrieval_settings(enhanced['map_memory'])
    assert b['topology_relations'] is False and e['topology_relations'] is True
    b.pop('topology_relations');e.pop('topology_relations')
    assert b==e and b['evidence_policy']=='evo_topology' and 'landmark_query' not in b

@pytest.mark.parametrize("out,cleared", [("changed instruction",False),("original stale suffix",True)])
def test_host_refuses_changed_question_and_stale_material(out,cleared):
    from graphAdapter.map_memory.retrieval.host_decision import HostInjection
    from graphAdapter.map_memory.storage.store import IntegrityError
    h=NS(images=(None,)*8)
    d=NS(history=h,model_visuals=h,settings=dict(evidence_policy='evo_topology'))
    def compile_question(*args):
        if cleared:d.history=None
        return out
    d.compile=compile_question
    host=HostInjection(d,[],8,lambda images,num_frames: h.images)
    with pytest.raises(IntegrityError):
        host.compile('original',lambda x:x,None,None,None)


def test_global_map_missing_geometry_retains_pinned_native_anchor(monkeypatch):
    from contextlib import nullcontext
    from graphAdapter.map_memory.retrieval import evo_global_map
    uid='f'
    a=dict(uid=uid,step=1,room='hallway',evidence=[])
    d=HostDecision(None,{},'native_plus_attachment',dict(evidence_policy='evo_topology',global_map=True))
    d.history=NS(images=(None,)*8,budget=8,slots=tuple(NS(frame_uid=uid,index=i,raw_pixel_hash='a',host_pixel_hash='a') for i in range(1,9)))
    d.evo_evidence=mod.PinnedEvidence(None,'pin','ep',dict(summary='Topology',anchors=[a],coverage={}),{}, {})
    d.evo_cutoff_step=1
    logs=[]
    d.emit=lambda k,**v: logs.append((k,v))
    leases=[]
    def pin(root,revision,image_cache=None,page_cache=None):
        assert image_cache is None
        leases.append(revision)
        return nullcontext(NS(identity={'episode_uid':'ep'}))
    monkeypatch.setattr(mod,'closing_reader',pin)
    monkeypatch.setattr(evo_global_map,'render_global_map',lambda *args:(None,dict(reason='no_geometry',episode_uid='ep',snapshot_id='pin')))
    result=mod.compile_evo(d,'original',lambda s:s,lambda s:np.arange(len(s)//4),196,4096)
    assert result.startswith('original') and 'native image 8' in result
    assert logs[0]==('GlobalMapUnavailable',dict(snapshot_id='pin',reason='no_geometry'))
    assert logs[-1][1]['map_image'] is None and d.combined.budget==8
    assert leases==['pin']

@pytest.mark.parametrize('reason',['missing_material','undecodable_image'])
def test_missing_whole_group_drops_dependent_crop_but_keeps_other_material(monkeypatch,reason):
    from contextlib import nullcontext
    from graphAdapter.map_memory.storage.archive import UnavailableMaterial
    step=dict(uid='old',room='hallway',step=1,evidence=[dict(member='old:d00000',aggregate_label='bench',label='bench',box_xyxy=[0,0,1,1])])
    good=dict(uid='good',room='entryway',step=2,evidence=[])
    decision=HostDecision(None,{},'native_plus_attachment',dict(evidence_policy='evo_topology'))
    decision.history=NS(budget=8,images=(None,)*8,slots=tuple(NS(frame_uid='good',index=i,raw_pixel_hash='x',host_pixel_hash='x') for i in range(1,9)))
    def read(uid,**kwargs):
        assert uid=='old'
        raise UnavailableMaterial(reason)
    monkeypatch.setattr(mod,'closing_reader',lambda *args:nullcontext(NS(identity={'episode_uid':'ep'},get_view=read)))
    decision.evo_evidence=mod.PinnedEvidence(None,'pin','ep',dict(summary='Topology',anchors=[step,good],coverage={}),{}, {})
    decision.evo_cutoff_step=3
    logs=[];decision.emit=lambda kind,**data:logs.append(data)
    result=mod.compile_evo(decision,'original',str,lambda s:np.arange(len(s)//4),196,4096)
    assert result.startswith('original') and 'native image 8' in result and '<image>' not in result
    assert [a['uid'] for a in logs[-1]['anchors']]==['good']
    assert logs[-1]['dropped']==[dict(role='whole_group',frame='old',reason=reason)]
    assert not logs[-1]['caption_bindings']


def test_observed_door_regions_are_frame_local_and_clip_to_original_grid():
    from graphAdapter.evaluation.evo_material_audit import check_archived_door_boxes
    src=dict(snapshot_id='pin',frame_uid='f',status='available',source_ref={'sha256':'blob'},raw_signature='sig',
             image_hw=[100,200],count=2,door_proposal_indices=[7,19],door_xyxy=[[-2.5,0,10.1,20.9],[120,50,122,55]])
    r=NS(snapshot_id='pin',get_observed_doors=lambda uid,include_masks:src)
    group=mod.observed_door_boxes(r,'f')
    assert group['boxes']==[dict(proposal_index=7,box_xyxy=[0,0,11,21]),dict(proposal_index=19,box_xyxy=[120,50,122,55])]
    source=('blob',[7,19],src['door_xyxy'])
    check_archived_door_boxes(group,source,(200,100))
    with pytest.raises(ValueError):check_archived_door_boxes(group,('blob',[0,1],src['door_xyxy']),(200,100))
    with pytest.raises(ValueError):check_archived_door_boxes(group,source,(100,200))
    src['frame_uid']='other'
    with pytest.raises(mod.IntegrityError):mod.observed_door_boxes(r,'f')
    src.update(frame_uid='f',status='not_recorded')
    assert mod.observed_door_boxes(r,'f') is None


def test_door_projected_pixels_require_depth_and_stay_in_target_grid():
    from graphAdapter.map_memory.retrieval.semantic_topology import _depth_support
    target=dict(depth=np.ones((3,4)),valid=np.ones((3,4),dtype=bool),K=np.eye(3),pose=np.eye(4))
    target['valid'][1,1]=False
    xyz=np.array([[0.,0.,1.],[1.,1.,1.],[4.,0.,1.],[-1.,0.,1.],[2.,0.,2.],[3.,2.,1.],[0.,0.,-1.]])
    same,in_frame,comp,u,v=_depth_support(xyz,np.eye(4),target,0.1,return_pixels=True)
    assert in_frame==4 and comp==3 and list(same)==[0,5]
    assert list(zip(u,v))==[(0,0),(3,2)]


def test_named_history_preserves_collisions_unknowns_turns_and_order():
    views={u:{'capture_seq':n} for n,u in enumerate('abcde',1)}
    rows=[];edges=[]
    for u,v,op,collision,traversed in [('a','b',1,False,True),('b','c',3,False,False),
                                       ('c','d',1,True,False),('d','e',1,False,False)]:
        def edge(kind):
            value=dict(id=kind+u+v,src=u,dst=v,type=kind)
            edges.append(value.copy());return value
        rows.append(dict(pre=u,post=v,action={'action_id':op,'collision':collision},
            motion=dict(temporal=edge('temporal_next'),traversed=edge('traversed') if traversed else None)))
    r=NS(_graph=dict(views=views,edges=edges),cutoff={'capture_seq':5},get_trace=lambda start,end:rows)
    start,end=dict(step=0,uid='a'),dict(step=4,uid='e')
    result=mod.recorded_anchor_route(r,start,end,mod._route_edges(r))
    assert result['runs']==[['forward (measured)',1],['right turn',1],['forward (collision)',1],['forward (no measured traversal)',1]]
    assert result['edge_ids']==[e['id'] for e in edges] and 'from A0 to A4' in mod.anchor_route_caption(result)
    for field,bad in [('src','b'),('dst','d'),('id','unknown')]:
        row=rows[0]['motion']['temporal'];saved=row[field];row[field]=bad
        with pytest.raises(mod.IntegrityError):mod.recorded_anchor_route(r,start,end,mod._route_edges(r))
        row[field]=saved
    rows[0]['action']['action_id']=True
    with pytest.raises(mod.IntegrityError):mod.recorded_anchor_route(r,start,end,mod._route_edges(r))
    rows[0]['action']['action_id']=1
    with pytest.raises(mod.IntegrityError):mod.recorded_anchor_route(r,end,start,mod._route_edges(r))
    rows.pop(1)
    with pytest.raises(mod.IntegrityError):mod.recorded_anchor_route(r,start,end,mod._route_edges(r))

def test_budget_degrades_full_map_compact_map_local_then_native(monkeypatch):
    from PIL import Image
    from contextlib import nullcontext
    from graphAdapter.map_memory.retrieval import evo_global_map
    uid='view';a=dict(uid=uid,step=0,room='hallway',evidence=[])
    manifest=dict(schema_version=2,episode_uid='ep',snapshot_id='pin',cutoff=dict(capture_seq=1),
        pose_map_version=0,current_uid='now',current_status='unknown',current_camera=None,
        caption='Detailed coverage. '*45,nodes=dict(anchors=[dict(id='A1',uid=uid,caption='Historical camera.')],objects=[]),coverage={})
    monkeypatch.setattr(mod,'closing_reader',lambda *a:nullcontext(NS(identity={'episode_uid':'ep'})))
    monkeypatch.setattr(evo_global_map,'render_global_map',lambda *args,**kwargs:(Image.new('RGB',(512,512)),manifest))
    def compile_at(limit):
        dec=HostDecision(None,{},'native_plus_attachment',dict(evidence_policy='evo_topology',global_map=True))
        dec.history=NS(budget=8,images=(None,)*8,slots=tuple(NS(frame_uid=uid,index=i,raw_pixel_hash='rgb',host_pixel_hash='rgb') for i in range(1,9)))
        dec.evo_evidence=mod.PinnedEvidence(None,'pin','ep',dict(summary='Historical room counts',anchors=[a],coverage={}),{}, {})
        dec.evo_cutoff_step=0
        events=[];dec.emit=lambda kind,**kw:events.append((kind,kw))
        answer=mod.compile_evo(dec,'Original',str,lambda text:np.arange(len(text.split())),196,limit)
        rec=next((e for k,e in events if k=='EvoTopologyCompiled'),None)
        if rec:
            assert answer=='Original'+rec['model_suffix']
            assert len(answer.split())+(8+rec['attachment_slots'])*195+256<=limit
            assert len(rec['caption_bindings'])==answer.count('<image>')
            return rec
        assert answer=='Original' and dec.history is None
        return None
    full=compile_at(4096); assert full['map_image'] and 'caption_style' not in full['map_image']
    # Find the exact transition using the test tokenizer; the separate replay uses the checkpoint tokenizer.
    compact=next(r for cap in range(2020,2210,2) if (r:=compile_at(cap)) and r['map_image'] and r['map_image'].get('caption_style')=='compact')
    assert compact['map_image']['caption'] in compact['model_suffix']
    local=compile_at(1980)
    assert local['map_image'] is None and 'native image 8' in local['model_suffix'] and 'Map node' not in local['model_suffix']
    assert any(e['role']=='global_map' and e['reason']=='context_budget' for e in local['dropped'])
    assert compile_at(1817) is None
