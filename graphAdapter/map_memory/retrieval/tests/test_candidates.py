import hashlib,json
import numpy as np
import pytest
from graphAdapter.map_memory.storage.store import IntegrityError,canonical,digest
from graphAdapter.map_memory.retrieval.contracts import MemoryQuery,EncodedQuery,ViewRef,CategoryVocabulary
from graphAdapter.map_memory.retrieval.candidates import get_candidates,match_category_cues

VOCAB=('door','chair','picture','sofa')
VOCAB_SOURCE=CategoryVocabulary.from_bytes(('\n'.join(VOCAB)+'\n').encode())
MODEL={'preprocess_hash':'pre','weights':{'clip':'fixed'},'vocabulary_sha256':VOCAB_SOURCE.source_sha256}
class Reader:
    snapshot_id='fixed'
    identity={'episode_uid':'episode'}
    cutoff={'capture_seq':21,'event_seq':210}
    versions={'pose_map_version':2}
    def __init__(self,reverse=False):
        self.views={}
        for i in range(1,22):
            self.views[f'f{i}']=ViewRef('episode','fixed',f'f{i}',i,i*10,i-1,
                f'hash{i}',f'host{i}',None if i%2 else (float(i),0.,0.),2,(),None)
        if reverse:self.views=dict(reversed(list(self.views.items())))
    def get_retrieval_index(self):return {'view_uids':tuple(self.views),'model_identity':MODEL}
    def get_retrieval_view(self,uid):return self.views[uid]
    def get_view_features(self,uid):
        i=int(uid[1:]); vec=np.array([1.,0.,0.]) if i==1 else np.array([0.,1.,0.])
        return {'status':'available','model_identity_hash':digest(canonical(MODEL)),
                'full_clip':vec,'object_clip':np.empty((0,3)),
                'class_ids':np.array([],dtype=int),'confidence':np.array([])}

def query(**kw):
    values=dict(episode_uid='episode',snapshot_id='fixed',current_frame_uid='f21',
        current_capture_seq=21,cutoff_capture_seq=21,cutoff_event_seq=210,
        instruction='Pass the chair and stop at the door.',current_position=None,pose_map_version=2)
    values.update(kw);return MemoryQuery(**values)
def encoded(q):
    return EncodedQuery(q.instruction_hash,digest(canonical(MODEL)),'tokenizer',np.array([[0.,1.,0.],[1.,0.,0.]]))

def test_R00_last_window_can_recall_old_nonanchor_without_pose():
    q=query();result=get_candidates(Reader(),q,encoded(q),VOCAB_SOURCE)
    assert len(result.views)==20
    assert 'f1' in result.channels['Q']
    assert result.ranked[0].view.frame_uid in {v.frame_uid for v in result.views}
    assert all(c.view.frame_uid!='f21' for c in result.ranked)
    assert len(result.ranked)<=24 and all(len(v)<=8 for v in result.channels.values())
    assert any(v.position is None for v in result.views)

def test_R10_order_independent_and_fixed_rrf():
    q=query();a=get_candidates(Reader(),q,encoded(q),VOCAB_SOURCE);b=get_candidates(Reader(True),q,encoded(q),VOCAB_SOURCE)
    assert a==b
    for candidate in a.ranked:
        expected=sum({'Q':.5,'V':.25,'C':.25}[name]/(60+rank)for name,rank in candidate.ranks)
        assert candidate.score==pytest.approx(expected)

@pytest.mark.parametrize('kw',[{'snapshot_id':'wrong'},{'episode_uid':'other'}, {'cutoff_event_seq':211}])
def test_R03_query_identity_mismatch_fails_closed(kw):
    q=query(**kw)
    with pytest.raises(IntegrityError):get_candidates(Reader(),q,encoded(q),VOCAB_SOURCE)

def test_full_vocabulary_identity_is_required():
    q=query()
    with pytest.raises(IntegrityError):get_candidates(Reader(),q,encoded(q),CategoryVocabulary.from_bytes(('\n'.join(VOCAB+('invented',))+'\n').encode()))

def test_query_features_cannot_come_from_another_instruction_or_model():
    q=query();e=encoded(q)
    for other in [EncodedQuery('wrong',e.model_identity_hash,'tokenizer',e.windows),EncodedQuery(e.instruction_hash,'wrong','tokenizer',e.windows)]:
        with pytest.raises(IntegrityError):get_candidates(Reader(),q,other,VOCAB_SOURCE)

def test_category_cues_use_words_and_explicit_aliases_only():
    assert match_category_cues('Go through the doorway, not the door.',VOCAB)==('door',)
    assert match_category_cues('Go through the doorway.',VOCAB)==()
    assert match_category_cues('Turn at the couch.',VOCAB,aliases={'couch':'sofa'})==('sofa',)
    with pytest.raises(ValueError):match_category_cues('desk',VOCAB,aliases={'desk':'unknown'})

def test_R03_future_view_rejected_and_invalid_geometry_still_in_pool():
    q=query();reader=Reader();reader.views['future']=ViewRef('episode','fixed','future',22,220,21,'x','y',None,2,(),None)
    result=get_candidates(reader,q,encoded(q),VOCAB_SOURCE)
    assert 'future' not in {v.frame_uid for v in result.views}
    assert ('future','future') in result.rejected
    assert any(v.position is None for v in result.views)


def test_repeated_REASON_is_causal_after_snapshot_but_before_current_decision():
    q=query(last_reasoning='The door is still ahead.',last_reasoning_event_seq=215,decision_event_seq=220)
    assert q.cutoff_event_seq==210 and q.last_reasoning_event_seq<q.decision_event_seq
    with pytest.raises(ValueError):query(last_reasoning='future',last_reasoning_event_seq=221,decision_event_seq=220)


def test_current_frame_ordinal_must_match():
    q=query(current_frame_uid='f20')
    with pytest.raises(IntegrityError):get_candidates(Reader(),q,encoded(q),VOCAB_SOURCE)


def test_vocabulary_preserves_source_identity_and_original_parser_order():
    a=CategoryVocabulary.from_bytes(b'door\nchair\nunknown\ndoor\n')
    b=CategoryVocabulary.from_bytes(b'door\r\nchair\r\nunknown\r\ndoor\r\n')
    assert a.labels==b.labels==('door','chair')
    assert a.ordered_labels_sha256==b.ordered_labels_sha256
    assert a.source_sha256!=b.source_sha256

def test_coverage_spread_matches_pairwise_reference_with_ties_and_missing_geometry():
    from types import SimpleNamespace
    from graphAdapter.map_memory.retrieval.candidates import _coverage_order,_time_order
    rng=np.random.default_rng(771)
    for n in (1,7,23):
        views=[SimpleNamespace(frame_uid=f'f{i}',capture_seq=i,position=None if i%7==0 else tuple(rng.integers(-2,3,3)),
                               pose_map_version=i%3) for i in range(n)]
        q=SimpleNamespace(current_position=(0,0,0),pose_map_version=1)
        for limit in range(1,9):
            eligible=[v for v in views if v.position is not None and v.pose_map_version==1]
            distance=lambda a,b:np.linalg.norm(np.asarray(a)-np.asarray(b))
            nearby=sorted(eligible,key=lambda v:(distance(v.position,q.current_position),v.capture_seq,v.frame_uid))
            spread=[];rest=list(eligible)
            while rest and len(spread)<limit:
                refs=[v.position for v in spread] or [q.current_position]
                nxt=min(rest,key=lambda v:(-min(distance(v.position,p)for p in refs),v.capture_seq,v.frame_uid))
                spread.append(nxt);rest.remove(nxt)
            expected=[]
            for i in range(limit):
                for channel in (_time_order(views,limit),nearby,spread):
                    if i<len(channel) and channel[i].frame_uid not in expected:expected.append(channel[i].frame_uid)
            assert [v.frame_uid for v in _coverage_order(views,q,limit)]==expected[:limit]

def test_camera_scores_reuse_stable_features_but_not_changed_payloads_or_encodings():
    from graphAdapter.map_memory.retrieval.candidates import CameraTextScores
    c=CameraTextScores(1);mat=np.array([[1.,0.]])
    source=dict(source_ref={'sha256':'A'},full_clip=np.array([1.,0.]))
    ident=('text','model','tokenizer')
    c.bind(mat,ident)
    assert c.score(mat,source)==1 and c.score(mat,source)==1 and (c.hits,c.misses)==(1,1)
    other=dict(source_ref={'sha256':'B'},full_clip=np.array([0.,1.]))
    assert c.score(mat,other)==0 and len(c.rows)==1 and 'A' not in c.rows
    new=np.array([[0.,1.]])
    c.bind(new,ident)
    assert c.score(new,other)==1 and c.hits==1
    c.bind(new,('different-reason','model','tokenizer'));assert not c.rows
    c.clear();assert c.embedding is None and c.identity is None
    zero=CameraTextScores(0);zero.bind(mat,ident)
    assert zero.score(mat,source)==zero.score(mat,source)==1 and not zero.rows and zero.hits==0

def test_reasoning_replacement_recomputes_supplement_while_view_channel_tracks_current():
    from dataclasses import replace
    from graphAdapter.map_memory.retrieval.candidates import CameraTextScores
    r=Reader()
    get=r.get_view_features
    r.get_view_features=lambda uid:dict(get(uid),source_ref={'sha256':uid})
    q=query(last_reasoning='first',last_reasoning_event_seq=215,decision_event_seq=220)
    full=encoded(q)
    ins=CameraTextScores();supp=CameraTextScores()
    for text,vec,current_vec in [('first',[1.,0.,0.],[1.,0.,0.]),('second',[0.,1.,0.],[0.,1.,0.])]:
        query_now=replace(q,last_reasoning=text)
        enc=replace(full,reasoning=np.array([vec]),reasoning_hash=hashlib.sha256(text.encode()).hexdigest())
        visual=dict(get('f21'),full_clip=np.array(current_vec),frame_uid='f21',capture_seq=21)
        baseline=get_candidates(r,query_now,enc,VOCAB_SOURCE,current_features=visual)
        cached=get_candidates(r,query_now,enc,VOCAB_SOURCE,current_features=visual,instruction_scores=ins,reasoning_scores=supp)
        assert cached==baseline
        if text=='first':previous=cached.channels['V']
        else:assert previous!=cached.channels['V']
    assert (ins.hits,ins.misses)==(20,20) and (supp.hits,supp.misses)==(0,40)
