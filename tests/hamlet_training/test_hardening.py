"""Synthetic fixtures for I/O safety and missing-asset behavior, not train data."""
import pytest
import torch
from PIL import Image
from awarevln_memory.training.artifacts import write_json
from awarevln_memory.training.observations import audit_observations
from awarevln_memory.training.preprocess import audit_cache_coverage
from awarevln_memory.training.cache import FeatureStore
from test_data import route,event


def test_output_cannot_enter_checkpoint_choice():
    with pytest.raises(ValueError,match='evaluation-only'):
        write_json('/data/zy/vln/data/checkpoint-choice/unsafe-new-report.json',{'not':'written'})


def test_asset_audit_keeps_repeated_native_frames_and_repairs_missing(tmp_path):
    path=tmp_path/'observed.png';Image.new('RGB',(4,4)).save(path)
    good=event(route(),1);good['image_paths']=[str(path)]*8
    bad=event(route(),2);bad['image_paths']=[str(path)]*7+[str(tmp_path/'missing.png')]
    ready,repairs,files,report=audit_observations([good,bad])
    assert len(ready)==1 and len(repairs)==1 and len(files)==2
    assert report['valid_unique_files']==1 and len(ready[0]['image_asset_checks'])==8


def test_asset_audit_refuses_eval_even_when_images_exist(tmp_path):
    e=event(route(),1);e['source_split']='val_unseen'
    with pytest.raises(ValueError):audit_observations([e])


def test_missing_past_can_be_explicitly_masked_not_reordered(tmp_path):
    from awarevln_memory.training.artifacts import identity
    c={'base_identity':'b','protocol_identity':'p','source_identity':'s'}
    prompts=FeatureStore(tmp_path/'p',c,create=True);moments=FeatureStore(tmp_path/'m',c,create=True)
    meta={'source_split':'train','dataset':'r2r','language':None,'partition':'train',
          'route_key':'r','rollout_id':'roll','call_id':4,'input_identity':'i',
          'verified_target':True,'mode_compatible':True,'target_sha256':identity('answer')}
    prompts.put('cur',{'prompt':torch.ones(2,8),'target_ids':torch.tensor([1,2])},meta)
    moments.put('cur',{'moment':torch.ones(4,8)},meta)
    moments.put('past1',{'moment':torch.ones(4,8)},dict(meta,call_id=1))
    row={'source_split':'train','dataset':'r2r','partition':'train','scene':'s','family':'f',
         'route_key':'r','rollout_id':'roll','call_id':4,'current':'cur','past':['past1','missing',None],
         'target_kind':'act','target_text':'answer','window_id':'w'}
    accepted,rejected=audit_cache_coverage([row],prompts,'reader',moments)
    assert not accepted and len(rejected)==1
    accepted,rejected=audit_cache_coverage([row],prompts,'reader',moments,mask_missing_past=True)
    assert not rejected and accepted[0]['past']==['past1',None,None]
    assert accepted[0]['missing_past_repairs'][0]['slot']==1
    # Corruption is a hard failure, not silently relabeled as a missing observation.
    moments._stem('past1').with_suffix('.safetensors').write_bytes(b'corrupt')
    accepted,rejected=audit_cache_coverage([row],prompts,'reader',moments,mask_missing_past=True)
    assert not accepted and len(rejected)==1


def test_existing_unseen_trace_cannot_be_relabelled_train(tmp_path):
    from awarevln_memory.training.rollouts import extract_rollout
    from awarevln_memory.training.artifacts import write_jsonl
    r=route();e=event(r,1);e['task_key']='r2r|val_unseen|en|s.glb|0|-'
    path=tmp_path/'apparently_train.jsonl';write_jsonl(path,[e])
    fields={k:k for k in ('route_key','event_id','rollout_id','call_id','prompt','image_paths','image_call_ids','protocol_identity')}
    ready,rejected=extract_rollout(path,[r],{'fields':fields})
    assert not ready and rejected[0]['reason']=='NATIVE_TRACE_IS_NOT_TRAIN'


def test_legacy_train_rows_join_authoritative_route_without_inventing_key(tmp_path):
    from awarevln_memory.training.rollouts import extract_rollout
    from awarevln_memory.training.artifacts import write_jsonl
    r=route();e=event(r,1);e.pop('route_key');e.update(scan='s',instruction_id='0',dataset='r2r')
    path=tmp_path/'train.jsonl';write_jsonl(path,[e])
    fields={k:k for k in ('event_id','rollout_id','call_id','prompt','image_paths','image_call_ids','protocol_identity')}
    ready,rejected=extract_rollout(path,[r],{'fields':fields,'route_join':{'scene':'scan','instruction_id':'instruction_id','dataset':'dataset'}})
    assert not rejected and ready[0]['route_key']=='r2r:s:0'


def test_dev_percentile_extremes_are_clipped_not_refitted():
    from awarevln_memory.training.data import _rank
    assert _rank([1,2,3],100)==1 and _rank([1,2,3],-100)==0


def test_only_consumed_observations_enter_expensive_prompt_cache():
    from awarevln_memory.training.preprocess import select_cache_events
    events=[{'event_id':str(i)} for i in range(20)]
    triplets=[{'anchor':'4','negative':'10'}]
    windows=[{'current':'4','past':['1','2','3']}]
    assert set(select_cache_events(events,triplets,windows))=={'1','2','3','4','10'}
    with pytest.raises(ValueError):select_cache_events(events,triplets,[{'current':'unknown','past':[None]*3}])
