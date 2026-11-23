"""Adversarial train-rollout joins; synthetic metadata, no navigation content."""
from awarevln_memory.training.rollouts import extract_rollout
from awarevln_memory.training.artifacts import write_jsonl, identity


def _route():
    return dict(dataset='rxr', source_split='train', language='en-US',
                scene='s', instruction_id='42', episode_id='episode-42',
                instruction='Turn right.', path=['a', 'b'],
                family=identity(['s', ['a', 'b']]), source_sha256='f' * 64)


def _raw(task_key):
    return dict(dataset='rxr', scene='s', instruction_id='42',
                event_id='event-1', rollout_id='rollout-1', call_id=1,
                prompt='<image>', image_paths=['frame.png'] * 8,
                image_call_ids=[1] * 8, protocol_identity='locked',
                task_key=task_key)


def _extract(tmp_path,task_key):
    path=tmp_path/'source.jsonl'
    write_jsonl(path, [_raw(task_key)])
    fields={k:k for k in ('event_id','rollout_id','call_id','prompt',
                           'image_paths','image_call_ids','protocol_identity')}
    join={'scene':'scene','instruction_id':'instruction_id','dataset':'dataset'}
    return extract_rollout(path, [_route()], {'fields':fields,'route_join':join})


def test_train_native_matching_instruction_and_episode(tmp_path):
    accepted,rejected=_extract(tmp_path,'rxr|train|en-US|s.glb|episode-42|42')
    assert len(accepted)==1 and not rejected


def test_train_native_different_instruction_rejected(tmp_path):
    accepted,rejected=_extract(tmp_path,'rxr|train|en-US|s.glb|episode-42|999')
    assert not accepted and rejected[0]['reason']=='NATIVE_TRACE_INSTRUCTION_MISMATCH'


def test_train_native_different_episode_rejected(tmp_path):
    accepted,rejected=_extract(tmp_path,'rxr|train|en-US|s.glb|episode-99|42')
    assert not accepted and rejected[0]['reason']=='NATIVE_TRACE_EPISODE_MISMATCH'


def test_train_native_missing_instruction_rejects_without_episode_proof(tmp_path):
    accepted,rejected=_extract(tmp_path,'rxr|train|en-US|s.glb|episode-42|-')
    assert len(accepted)==1 and not rejected
    # Raw route has no authoritative episode identity -> do not trust '-' ID.
    from awarevln_memory.training.rollouts import extract_rollout
    from awarevln_memory.training.artifacts import write_jsonl
    path=tmp_path/'unknown-episode.jsonl';write_jsonl(path, [_raw('rxr|train|en-US|s.glb|episode-42|-')])
    fields={k:k for k in ('event_id','rollout_id','call_id','prompt',
                           'image_paths','image_call_ids','protocol_identity')}
    route=_route(); route['episode_id']=None
    accepted,rejected=extract_rollout(path,[route],{'fields':fields,'route_join':{'scene':'scene','instruction_id':'instruction_id','dataset':'dataset'}})
    assert not accepted and rejected[0]['reason']=='NATIVE_TRACE_UNVERIFIED_INSTRUCTION_AND_EPISODE'


def test_native_route_annotation_requires_train_source_provenance(tmp_path):
    from awarevln_memory.training.data import ingest
    from awarevln_memory.training.artifacts import write_json
    value=[{'scan':'s','path':['a','b'],'path_id':'7','instructions':['go']}]
    anonymous=tmp_path/'episode-export.json';write_json(anonymous,value)
    accepted,rejected=ingest(anonymous,'r2r','train')
    assert not accepted and rejected[0]['reason']=='SOURCE_SPLIT_UNVERIFIED'
    # Original records with an explicit split are not inferred from filenames.
    declared=tmp_path/'nondescript.json';write_json(declared,[dict(value[0],split='train')])
    accepted,rejected=ingest(declared,'r2r','train')
    assert len(accepted)==1 and not rejected
    # Explicit val-unseen always wins over a filename resembling train.
    misnamed=tmp_path/'r2r_train.json';write_json(misnamed,[dict(value[0],split='val_unseen')])
    accepted,rejected=ingest(misnamed,'r2r','train')
    assert not accepted and rejected[0]['reason']=='SPLIT_NOT_TRAIN'
