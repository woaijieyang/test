from pathlib import Path
import sys,json,hashlib,time,dataclasses
from types import SimpleNamespace
import numpy as np
import torch,open_clip
ROOT=Path('/data/zy/vln/case2')
sys.path.insert(0,str(ROOT/'vendor_sources/EvoMemNav'))
from graphAdapter.map_memory.storage.store import load_episode,canonical,digest,file_hash
from graphAdapter.map_memory.storage.features import EpisodeFeatureCache
from graphAdapter.map_memory.retrieval.query_adapter import QueryEncoder
from graphAdapter.map_memory.retrieval.contracts import MemoryQuery,EncodedQuery,CategoryVocabulary
from graphAdapter.map_memory.retrieval.candidates import get_candidates
from graphAdapter.map_memory.retrieval.bundles import build_bundles
from graphAdapter.map_memory.retrieval.selector import select_history
OUT=ROOT/'outputs/graph_memory/graph002-work-20261113'
MAP=ROOT/'outputs/graph_memory/graph001-organized-20261113/validation/cold-readback/map'
torch.set_num_threads(4)
reader=load_episode(MAP)
try:
    identity=reader._graph['model_identity'];weight=ROOT/'models/graph001/open_clip_pytorch_model.bin'
    assert file_hash(weight)==identity['weights'][weight.name]
    model=open_clip.create_model('ViT-B-32',pretrained=str(weight),device='cpu').eval()
    tokenizer=open_clip.get_tokenizer('ViT-B-32')
    assert model.context_length==tokenizer.context_length
    text=('Walk along the hall, passing the pictures and benches. '*10)+'Stop near the telephone.'
    latest=max(reader._graph['views'],key=lambda uid:reader._graph['views'][uid]['capture_seq'])
    current=reader.get_retrieval_view(latest)
    q=MemoryQuery(reader.identity['episode_uid'],reader.snapshot_id,latest,current.capture_seq,
        reader.cutoff['capture_seq'],reader.cutoff['event_seq'],text,current.position,reader.versions['pose_map_version'])
    vocab=CategoryVocabulary.from_file(ROOT/'vendor_sources/EvoMemNav/data/scannet200_classes.txt')
    models=SimpleNamespace(clip_model=model,clip_tokenizer=tokenizer,clip_model_hash=identity['weights'][weight.name],
        preprocess_hash=identity['preprocess_hash'],class_vocabulary_hash=vocab.ordered_labels_sha256)
    encoder=QueryEncoder(models,identity,vocab)
    rng=torch.get_rng_state().clone();encoded=encoder.encode(q);batches=encoder.model_batches
    reused=encoder.encode(q)
    assert encoder.model_batches==batches and encoded.windows is reused.windows and torch.equal(rng,torch.get_rng_state())
    windows=encoder.audit(text)['windows']
    started=time.perf_counter();candidates=get_candidates(reader,q,encoded,vocab)
    graph_bundles=build_bundles(candidates,reader.get_retrieval_index(),pose_map_version=q.pose_map_version)
    graph=select_history(candidates,graph_bundles,current,budget=8)
    flat=select_history(candidates,build_bundles(candidates,reader.get_retrieval_index(),pose_map_version=q.pose_map_version,expand=False),current,budget=8)
    elapsed=time.perf_counter()-started
    second=get_candidates(reader,q,encoded,vocab)
    assert candidates==second
    fresh=load_episode(MAP,revision=reader.snapshot_id)
    try:
        reloaded=get_candidates(fresh,q,encoded,vocab)
        restored=select_history(reloaded,build_bundles(reloaded,fresh.get_retrieval_index(),pose_map_version=q.pose_map_version),fresh.get_retrieval_view(latest),budget=8)
        assert reloaded==candidates and restored==graph
    finally:fresh.close()
    report=dict(status='PASS_REAL_ARCHIVE_OPEN_LOOP_DIAGNOSTIC',scope='Real stored RGB identities and CLIP features plus actual matching CLIP text encoder; diagnostic instruction, not recorded navigation instruction or relevance accuracy',snapshot_id=reader.snapshot_id,
        instruction=text,windows=windows,query_encoder_batches=encoder.model_batches,query_encoder_cache_hits=encoder.cache_hits,query_encoder_cache_bytes=encoder.cache_bytes,query_feature_same_array_on_reuse=encoded.windows is reused.windows,pool=len(candidates.views),
        channels=dict(candidates.channels),category_cues=candidates.category_cues,
        graph_slots=[v.capture_seq for v in graph.slots],flat_slots=[v.capture_seq for v in flat.slots],
        graph_groups=[dict(seed=b.seed_ref,frames=[v.capture_seq for v in b.views],edge_types=b.edge_types,reason=b.selection_reason)for b in graph.groups],
        graph_fallback=graph.fallback_reason,flat_fallback=flat.fallback_reason,
        deterministic_reload=True,selection_seconds=elapsed,navigation_run=False,main_model_injection=False,
        pixel_materialization_or_tensor_audit=False,pose_or_simulator_started=False)
    (OUT/'REAL_QUERY_ENCODER_RETRIEVAL.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items()if k not in ('instruction','windows','channels','graph_groups')},indent=2))
finally:
    if 'encoder'in globals():encoder.close()
    reader.close()
