from types import SimpleNamespace
import pytest
from graphAdapter.map_memory.retrieval.evidence import resolve,append_evidence
from graphAdapter.map_memory.retrieval.tests.test_session import recorded,VOCAB,Encoder,request,capture,EP
from graphAdapter.map_memory.retrieval.session import MemoryRetrievalSession
from graphAdapter.map_memory.storage.store import load_episode,IntegrityError
from graphAdapter.map_memory.retrieval.protocol import native_slot_indices

def test_additive_channel_returns_only_offscreen_step_evidence(tmp_path):
    root,ids=recorded(tmp_path)
    session=MemoryRetrievalSession(root,EP,'session',Encoder(),VOCAB,evidence_policy='additive_text')
    q=request(ids,mode='facts_only');q['budget']=3
    reader=load_episode(root,revision=ids[0])
    try:
        reply=session.read(q,current_snapshot_id=ids[1])
        assert reply['selection'] is None
        refs=reply['uniform_views']
        native={refs[i]['frame_uid'] for i in native_slot_indices(len(refs),3)}
        proposals=reply['additional_evidence'];assert proposals and all(x['uid'] not in native for x in proposals)
        facts=resolve(proposals,reader,VOCAB,5,q['query']['instruction'])
        original='Go past the door.';text,used=append_evidence(original,facts,len,lambda _:True,200)
        assert text.startswith(original) and used and 'possible door' in text and '<image>' not in text
        assert append_evidence(original,facts,len,lambda _:False,200)==(original,())
        with pytest.raises(IntegrityError):resolve([dict(proposals[0],label='wall')],reader,VOCAB,5,'Go past the door.')
    finally:reader.close();session.close()

def test_turn_evidence_rejects_changed_side_and_future():
    from graphAdapter.map_memory.retrieval.tests.test_bundles_selector import view
    # Pure execution evidence can come from an undisplayed observation.
    e={'post':'f2','pre':'f1','action':{'action_id':3,'collision':False},
       'motion':{'temporal':{'id':'edge','src':'f1','dst':'f2'}}}
    reader=SimpleNamespace(snapshot_id='snap',identity={'episode_uid':'ep'},cutoff={'event_seq':20,'capture_seq':2},
        get_retrieval_view=lambda uid:view(int(uid[1:])),get_trace=lambda:[e])
    proposal=dict(kind='turn',pre='f1',post='f2',side='right')
    facts=resolve([proposal],reader,VOCAB,3,'Turn right at the end.')
    assert len(facts)==1 and facts[0].source_refs==('f1','f2','edge')
    with pytest.raises(IntegrityError):resolve([dict(proposal,side='left')],reader,VOCAB,3,'Turn left.')
    with pytest.raises(IntegrityError):resolve([proposal],reader,VOCAB,2,'Turn right.')

