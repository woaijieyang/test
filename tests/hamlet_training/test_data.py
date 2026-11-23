import json
from pathlib import Path
import pytest
import torch
from awarevln_memory.training.artifacts import write_json,write_jsonl,training_path,identity,budget
from awarevln_memory.training.data import ingest,attach_events,select_routes,build_windows,route_key
from awarevln_memory.training.datasets import validate_events,validate_partitions,tcl_triplets
from awarevln_memory.training.cache import FeatureStore
from awarevln_memory.training.evaluation import cumulative_sets,aggregate,choose_candidate,canonical_eval_rows


def route(i=0,dataset='r2r',scene='s',partition='train'):
    return dict(dataset=dataset,source_split='train',language='en-US' if dataset=='rxr' else None,
                scene=scene,instruction_id=str(i),instruction='Turn left after the kitchen doorway.',
                path=['a','b',str(i)],family=identity([scene,i]),source_sha256='a'*64,partition=partition,
                capabilities={'observation':True,'act':True,'reason':False,'replay':False},
                features_raw={'L':i+2,'G':2,'T':i%3,'A':i%5,'V':.2,'Q':1})


def event(r,call,rollout='run'):
    return dict(event_id=f'{route_key(r)}:{rollout}:{call}',route_key=route_key(r),source_split='train',
                rollout_id=rollout,call_id=call,prompt=' '.join(['<image>']*8)+' Original prompt',
                image_paths=['image.png']*8,image_call_ids=[max(0,call-1)]*7+[call],protocol_identity='p',
                target_kind='act',target_text='<BEGIN_OF_ACTION>move forward 25 cm',target_source='expert',
                target_provenance={'source':'test-fixture'},executed_actions=[1],training_position=[float(call)*3,0,0])


def test_official_language_and_split_not_inferred_from_text(tmp_path):
    source=tmp_path/'train.json'
    write_json(source,[dict(scan='s',path=['a','b'],instruction_id=i,language=lang,instruction='English words') for i,lang in enumerate(['en-US','en-IN','hi-IN',None])])
    accepted,rejected=ingest(source,'rxr','train')
    assert len(accepted)==1 and len(rejected)==3
    with pytest.raises(ValueError):ingest(source,'rxr','val_unseen')


def test_r2r_missing_rxr_language_is_not_rejected(tmp_path):
    source=tmp_path/'train.json';write_json(source,[dict(scan='s',path=['a','b'],path_id=5,instructions=['first','second'])])
    rows,rejected=ingest(source,'r2r','train')
    assert not rejected and [r['instruction_id'] for r in rows]==['5_0','5_1']
    assert rows[0]['family']==rows[1]['family'] and rows[0]['language'] is None


def test_ce_r2r_episode_identity_without_path_id(tmp_path):
    source=tmp_path/'train.json';write_json(source,{'episodes':[dict(scene_id='s.glb',episode_id=6,
            reference_path=[[0,0,0],[0,0,1]],instruction={'instruction_text':'go forward'})]})
    rows,rejected=ingest(source,'r2r','train')
    assert not rejected and rows[0]['instruction_id']=='ce-episode:6'


def test_eval_root_and_symlink_are_rejected(tmp_path):
    evalroot=tmp_path/'eval';evalroot.mkdir();(evalroot/'x').touch();alias=tmp_path/'alias';alias.symlink_to(evalroot,target_is_directory=True)
    with pytest.raises(ValueError):training_path(alias/'x',evaluation_root=evalroot)


def test_artifact_is_exclusive(tmp_path):
    path=tmp_path/'a.json';write_json(path,{'v':1})
    with pytest.raises(FileExistsError):write_json(path,{'v':2})
    assert json.loads(path.read_text())=={'v':1}


def test_partial_capabilities_not_whole_route_rejection():
    r=route();e=event(r,1)
    a=attach_events([r],[e])[0]
    assert a['capabilities']['act'] and not a['capabilities']['reason']
    e.pop('target_text');b=attach_events([r],[e])[0]
    assert b['capabilities']['observation'] and not b['capabilities']['act']


def test_selection_determinism_scene_and_family_isolation():
    routes=[route(i,d,s) for s in ['s0','s1','s2','s3'] for d in ['r2r','rxr'] for i in range(12)]
    a,report=select_routes(routes,total=24,pilot=True)
    b,_=select_routes(list(reversed(routes)),total=24,pilot=True)
    assert a==b and len(a)==24
    validate_partitions(a)
    assert max(sum(x['family']==r['family'] for x in a) for r in a)<=2


def test_future_images_rejected_and_recent_gap_not_compressed():
    r=route();events=[event(r,1),event(r,4)]
    rows,_=build_windows([r],events)
    row=next(x for x in rows if x['call_id']==4)
    assert row['past']==[events[0]['event_id'],None,None]
    events[1]['image_call_ids'][-1]=5
    with pytest.raises(ValueError,match='future'):build_windows([r],events)


def test_window_cap_applies_across_rollout_variants():
    r=route();events=[event(r,c,run) for run in ['a','b','c'] for c in range(1,20)]
    rows,_=build_windows([r],events,max_anchors=5)
    assert len(rows)==5


def test_tcl_same_place_revisit_is_not_negative():
    r=route();raw=[event(r,i) for i in (1,2,3)]
    raw[1]['training_position']=raw[0]['training_position'];raw[2]['training_position']=[20,0,0]
    events=validate_events([r],raw);pairs,_=tcl_triplets(events)
    by_id={e['event_id']:e for e in raw}
    assert len(pairs)==3
    assert all(by_id[x['anchor']]['training_position']!=by_id[x['negative']]['training_position'] for x in pairs)


def test_partition_leak_detected():
    with pytest.raises(ValueError):validate_partitions([route(1,partition='train'),route(2,partition='memory-dev')])


def test_feature_store_contract_hash_and_partition(tmp_path):
    contract={'base_identity':'b','protocol_identity':'p','source_identity':'s'}
    store=FeatureStore(tmp_path/'cache',contract,create=True)
    metadata={'source_split':'train','dataset':'rxr','language':'en-US','partition':'train'}
    store.put('x',{'prompt':torch.ones(2,3)},metadata)
    assert store.get('x',partition='train')[0]['prompt'].shape==(2,3)
    with pytest.raises(ValueError):store.get('x',partition='memory-dev')
    with pytest.raises(ValueError):FeatureStore(store.root,dict(contract,base_identity='changed'))
    path=store._stem('x').with_suffix('.safetensors');path.write_bytes(b'bad')
    with pytest.raises(ValueError):store.get('x')


def erow(i,dataset='r2r'):
    return dict(dataset=dataset,source_split='val_unseen',scene='s',instruction_id=str(i),episode_id=str(i),language='en-US')


def test_b_cumulative_disjoint_and_nested_equal():
    a,b,c=[erow(1)],[erow(2)],[erow(3)]
    x,mode=cumulative_sets(a,b,c);y,mode2=cumulative_sets(a,a+b,a+b+c)
    assert mode=='disjoint' and mode2=='nested' and x==y
    with pytest.raises(ValueError):cumulative_sets(a,a+b,b+c)


def test_b_aggregation_not_mean_of_partition_means():
    expected=[erow(i) for i in range(4)]
    rows=[dict(e,checkpoint_sha256='c',protocol_sha256='p',status='complete',sr=int(i==0),spl=0.,ndtw=.2,ne=3.) for i,e in enumerate(expected)]
    result=aggregate(expected,rows,'c','p')
    assert result['sr']==.25
    with pytest.raises(ValueError):aggregate(expected,rows[:1],'c','p')
    rows[0]['checkpoint_sha256']='changed'
    with pytest.raises(ValueError):aggregate(expected,rows,'c','p')


def test_final_selection_does_not_force_new_model():
    summary={d:{'n':10,'episodes_sha256':d,'protocol_sha256':'p','sr':.6,'spl':.5,'ndtw':.6} for d in ('r2r','rxr')}
    assert choose_candidate(summary,{'same':summary})['selected'] is None
    improve={d:dict(s,sr=.7) for d,s in summary.items()}
    assert choose_candidate(summary,{'better':improve})['selected']=='better'


def test_b_raw_ids_resolve_to_original_native_task_key():
    rows=canonical_eval_rows(['7'],'r2r',[{'episode_id':7,'scene_id':'a/s.glb','instruction':{}}])
    assert rows[0]['native_task_key']=='r2r|val_unseen|en|a/s.glb|7|-'


def test_budget_records_exposures_not_arbitrary_8000_steps():
    b=budget(500,4,1,2,8,5000)
    assert b['max_steps']==125 and b['effective_batch']==16
    with pytest.raises(ValueError):budget(0,4,1,2,8,5000)
