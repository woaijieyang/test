"""Metadata group tests with the recorded RxR2182 publications and frozen CLIP."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

from graphAdapter.map_memory.retrieval.bundles import build_bundles
from graphAdapter.map_memory.retrieval.candidates import CameraTextScores,get_candidates
from graphAdapter.map_memory.retrieval.contracts import CategoryVocabulary,MemoryQuery
from graphAdapter.map_memory.retrieval.evo_context import read_context_bundle
from graphAdapter.map_memory.retrieval.query_adapter import QueryEncoder
from graphAdapter.map_memory.retrieval.selector import select_history
from graphAdapter.map_memory.storage.store import IntegrityError,load_episode


ROOT = Path('/data/zy/vln/case2')
MAP = ROOT/'outputs/graph_memory/candidate_detached_correction001-20261113/review/seal-profile/real-long-prefix/map'
PINS = ['8615bc229e7d341c6583a10ff016e71bc6942be7049e4eb7147ab286e863e370',
        '48e22244a6f160d8df78a52f224ed2b5fc835c05c6feaada87ec98c470243939']


@pytest.fixture(scope='module')
def session():
    import open_clip
    vocab = CategoryVocabulary.from_file(ROOT/'vendor_sources/EvoMemNav/data/scannet200_classes.txt')
    path = ROOT/'models/graph001/open_clip_pytorch_model.bin'
    # Offline fixture: use the published weights on CPU. Online reuses the existing worker model.
    original_threads = torch.get_num_threads()
    torch.set_num_threads(min(original_threads,4))
    try:
        with closing(load_episode(MAP,revision=PINS[0])) as r:
            identity = r._graph['model_identity']
        model = open_clip.create_model('ViT-B-32',pretrained=str(path),device='cpu').eval()
        provider = SimpleNamespace(clip_model=model,clip_tokenizer=open_clip.get_tokenizer('ViT-B-32'),
                                   clip_model_hash=identity['weights'][path.name],preprocess_hash=identity['preprocess_hash'],
                                   class_vocabulary_hash=vocab.ordered_labels_sha256)
        with closing(QueryEncoder(provider,identity,vocab)) as enc:
            yield SimpleNamespace(encoder=enc,vocabulary=vocab,instruction_scores=CameraTextScores(64),
                                  reasoning_scores=CameraTextScores(64))
    finally:
        torch.set_num_threads(original_threads)


@pytest.mark.parametrize('i,reason',[(0,None),(1,'I see a door')])
def test_context_preserves_existing_selection_and_scope(session,i,reason):
    with closing(load_episode(MAP,revision=PINS[i])) as r:
        cap = r.cutoff['capture_seq']
        uid = f"{r.identity['episode_uid']}:f{cap:06d}"
        current = r.get_retrieval_view(uid)
        instruction = 'Continue along the corridor. '*24 + 'At the end, turn by the column.'
        q = MemoryQuery(current.episode_uid,r.snapshot_id,uid,cap,cap,r.cutoff['event_seq'],
                        instruction,current.position,current.pose_map_version,reason,
                        1 if reason else None,r.cutoff['event_seq']+1)
        result = read_context_bundle(session,r,q,current,r,8)
        assert result['status']=='selected' and result['query']['instruction_windows']>1
        assert bool(result['query']['reasoning_windows']) == bool(reason)
        assert set(result['channels'])=={'Q','V','C'}
        encoded = session.encoder.encode(q)
        pool = get_candidates(r,q,encoded,session.vocabulary,current_features=r.get_view_features(uid))
        bundles = build_bundles(pool,r.get_retrieval_index(),pose_map_version=r.versions['pose_map_version'])
        expected = select_history(pool,bundles,current,budget=8)
        assert result['counts']['historical_views']==cap-1
        assert result['channels']=={k:list(v) for k,v in pool.channels.items()}
        assert [g['seed_ref'] for g in result['groups']]==[g.seed_ref for g in expected.groups]
        source_edges = {(e['id'],e['type'],e['src'],e['dst']) for e in r._graph['edges']}
        visible = set(map(tuple,r._graph['vsm']['visibility_edges']))
        for g in result['groups']:
            assert all(v['uid']!=uid and v['capture_seq']<cap for v in g['views'])
            for e in g['edges']:
                assert (e['id'],e['type'],e['src'],e['dst']) in source_edges
            for m in g['visibility']:
                assert (m['uid'],m['object_id']) in visible
                assert m['member'] in r.get_object(m['epoch'],m['object_id'],revision=r.snapshot_id)['members']
        before = session.encoder.model_batches
        again = read_context_bundle(session,r,q,current,r,8)
        assert result==again and before==session.encoder.model_batches
        with pytest.raises(IntegrityError):
            read_context_bundle(session,r,q,replace(current,source_snapshot_id='other'),r,8)
