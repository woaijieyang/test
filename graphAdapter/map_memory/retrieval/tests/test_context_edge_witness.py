"""Reject inconsistent one-hop claims before a model can read them."""
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from graphAdapter.map_memory.storage.store import IntegrityError
from graphAdapter.map_memory.retrieval.evo_context_host import verify_context

@pytest.mark.parametrize('fault',['collision','wrong_action','missing_receipt','wrong_motion_id','not_seed_incident','duplicate_edge','duplicate_view','single_visibility','noncanonical_member','negative_class'])
def test_host_does_not_publish_unsupported_context(monkeypatch,fault):
    from graphAdapter.map_memory.retrieval import evo_context_host as mod
    g=dict(views={k:dict(env_step=n,capture_seq=n+1,source_event_seq=n) for n,k in enumerate('abc')},
           scene_state={'epoch':'E'},edges=[dict(id='t',src='a',dst='b',type='traversed')])
    edge=g['edges'][0].copy()
    if fault=='not_seed_incident':edge.update(src='b',dst='c');g['edges'][0]=edge.copy()
    receipt=dict(pre=edge['src'],post=edge['dst'],action=dict(action_id=1,collision=False),motion=dict(traversed=edge.copy()))
    trace=[receipt]
    if fault=='collision':receipt['action']['collision']=True
    if fault=='wrong_action':receipt['action']['action_id']=2
    if fault=='wrong_motion_id':receipt['motion']['traversed']['id']='other'
    if fault=='missing_receipt':trace.clear()
    views=[dict(uid=k,step=n,capture_seq=n+1) for n,k in enumerate('abc')]
    group=dict(seed_ref='a',views=views,edges=[edge],visibility=[])
    if fault=='duplicate_edge':group['edges'].append(edge.copy())
    if fault=='duplicate_view':group['views'].append(views[0].copy())
    if fault in ('single_visibility','noncanonical_member','negative_class'):
        group['visibility']=[dict(uid=u,object_id=1,epoch='E',member=u+':d00000') for u in 'ab']
        if fault=='single_visibility':group['visibility'].pop()
        if fault=='noncanonical_member':group['visibility'][0]['member']='a:d0'
    q=NS(episode_uid='ep',instruction_hash='I',last_reasoning=None,cutoff_event_seq=4,cutoff_capture_seq=4,current_capture_seq=5)
    c=NS(frame_uid='e',source_snapshot_id='pin')
    reply=dict(episode_uid='ep',snapshot_id='pin',current_frame_uid='e',current_source_snapshot_id='pin',
               query=dict(instruction_sha256='I',reasoning_sha256=None),channels={'Q':['a'],'C':[],'V':[]},groups=[group])
    camera=dict(status='available',model_identity=dict(vocabulary_sha256='V'),class_ids=[-1 if fault=='negative_class' else 0])
    r=NS(snapshot_id='pin',_graph=g,get_trace=lambda start,end:trace,get_view_class_ids=lambda uid:camera)
    monkeypatch.setattr(mod,'visible_detection_owners',lambda reader,uid:{0:1})
    with pytest.raises(IntegrityError):verify_context(r,q,c,reply,NS(source_sha256='V',labels=['bed','lamp']))
