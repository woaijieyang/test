from types import SimpleNamespace as NS
import numpy as np
import pytest
from graphAdapter.map_memory.retrieval.dynamic_context import DecisionGate
from graphAdapter.map_memory.retrieval.candidates import propose_anchor,label_from_upstream
from graphAdapter.map_memory.retrieval.input_audit import separate_attachment_encoding
from graphAdapter.map_memory.storage.archive import IntegrityError

def test_events_are_edge_triggered_and_session_scoped():
    g=DecisionGate()
    def check(frame,collision,reason=None,session='A'):
        ev=g.trigger(('ep',session),frame,{'action_id':1,'collision':collision},reason)
        return g.consume_event(ev)
    assert not check('f1',False)
    assert check('f2',True)
    assert not check('f2',True) and not check('f3',True)
    assert check('f3',True,10) and not check('f3',True,10)
    assert not check('f4',False,10) and check('f5',True,10)
    g.delivered.add(('old',))
    assert not check('f1',False,None,'B') and not g.delivered

def test_real_anchor_selector_and_prompt_pairing():
    views=[NS(frame_uid=str(i),capture_seq=i)for i in range(1,25)]
    c=NS(views=views[:-1],category_cues=('bed',))
    idx={'anchors':{'2':{'room_type_hint':'bedroom'},'3':{'room_type_hint':'kitchen'},'22':{'room_type_hint':'bedroom'}}}
    reader=NS(get_view_class_ids=lambda uid,*,include_confidence:dict(status='available',class_ids=[0],confidence=[.8]))
    reader._graph=dict(scene_state={'epoch':'e'},vsm=dict(anchors={u:{'objects':[int(u)]}for u in idx['anchors']},
        visibility_edges=[(u,int(u))for u in idx['anchors']]),entities=[dict(status='active',epoch='e',id=int(u),
        members=[u+':d00000'])for u in idx['anchors']])
    selected=propose_anchor(c.views,views[-1],idx,reader,NS(labels=['bed']),'bed in the bedroom',8)
    assert selected[0]['uid']=='22' and all(x['label']=='bed' for x in selected)
    attach=NS(image=np.full((2,2,3),42,np.uint8))
    assert label_from_upstream('Find the bed',attach,'bedroom')=='Anchor View 0 (room: bedroom)'

def test_encoder_groups_and_exception_cleanup():
    import torch
    class Model:
        def encode_images(self,x):return x.flatten(1)[:,None,:]+x.shape[0]
    model=Model();x=torch.ones(9,3,2,2)
    expected=model.encode_images(x[:8])
    with separate_attachment_encoding(model,8):
        assert torch.equal(model.encode_images(x)[:8],expected)
    assert 'encode_images' not in vars(model)
    with pytest.raises(IntegrityError),separate_attachment_encoding(model,8):model.encode_images(x[:7])
    assert 'encode_images' not in vars(model)


def test_current_plan_landmarks_are_causal_and_instruction_bound():
    from graphAdapter.map_memory.retrieval.evidence import landmark_query_cues
    vocab=('bed','poster','chair','stand','door')
    task='Walk past the bed and stand beside the poster.'
    assert landmark_query_cues(task,None,vocab)==('bed','poster')
    assert landmark_query_cues(task,'I passed the bed. The next plan is to stand beside the poster.',vocab)==('poster',)
    for reason in ('I see the bed.','The next plan is to avoid the bed.',
                   'The next plan is to go to the chair.','The next plan is to turn. I see a bed.'):
        assert landmark_query_cues(task,reason,vocab)==()
    assert landmark_query_cues('Approach the stand.','The next plan is to approach the stand.',vocab)==('stand',)
