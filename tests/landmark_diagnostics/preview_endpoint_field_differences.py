"""Describe every prospective field change using the existing nine-task derivative rule."""
import copy,datetime,json,os,sys
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
from preflight import SPECS,dataset_base,load,task_key
from build_derived_annotations import diff
assert os.environ.get('CASE1_PROTECTION')
O=R/'outputs/connectivity/formal-endpoint-repair-preview-v2';proposal=json.loads((O/'validation.json').read_text());audit=json.loads((O/'independent-prospective-validation.json').read_text());assert audit['status']=='PASS_ALL_PROSPECTIVE_ENDPOINTS_NOT_APPLIED' and audit['proposal_sha256']==digest(O/'validation.json')
changes={r['task_key']:r for r in proposal['changes']};assert len(changes)==106
reports=[];inputs=[];dataset_counts={};gt_count=0
for dataset,spec in SPECS.items():
    ap=dataset_base(dataset)/spec[1];gp=dataset_base(dataset)/spec[2];inputs.extend([{'path':str(p),'sha256':digest(p)} for p in [ap,gp]])
    original=load(ap);gt_original=load(gp);annotations=copy.deepcopy(original);gt=copy.deepcopy(gt_original);selected=set();changed_gt=set()
    for before,after in zip(original['episodes'],annotations['episodes']):
        if dataset=='rxr' and before['instruction']['language']!='en-US':
            assert not diff(before,after);continue
        key=task_key(dataset,before)
        if key not in changes:
            assert not diff(before,after);continue
        change=changes[key];old,new=change['old'],change['proposed'];assert new is not None
        eid=str(before['episode_id']);selected.add(key)
        if change['kind']=='start':
            assert before['start_position']==old and gt[eid]['locations'][0]==old
            after['start_position']=new[:];gt[eid]['locations'][0]=new[:];changed_gt.add(eid)
        else:
            index=int(change['kind'].split(':')[1]);assert before['goals'][index]['position']==old
            after['goals'][index]['position']=new[:]
            # Existing approved rule preserves goal GT: no last GT point equals oldgoal.
            assert gt[eid]['locations'][-1]!=old
        occurrences=0
        for i,point in enumerate(before.get('reference_path',[])):
            if point==old:after['reference_path'][i]=new[:];occurrences+=1
        assert occurrences==1
        delta=diff(before,after);gt_delta=diff(gt_original[eid],gt[eid]);assert delta
        assert all(r['field'].startswith(('/start_position/','/goals/','/reference_path/')) for r in delta)
        assert all(r['field'].startswith('/locations/0/') for r in gt_delta)
        reports.append({'task_key':key,'dataset':dataset,'episode_id':eid,'role':change['kind'],'annotation_changes':delta,'gt_changes':gt_delta,'reference_occurrences':occurrences})
    assert selected=={k for k,c in changes.items() if c['dataset']==dataset}
    actual_changed_gt={k for k in gt if diff(gt_original[k],gt[k])};assert actual_changed_gt==changed_gt
    dataset_counts[dataset]={'annotation_records':len(selected),'gt_records':len(changed_gt),'all_input_episodes':len(original['episodes'])};gt_count+=len(changed_gt)
assert len(reports)==106 and gt_count==63
assert all(digest(r['path'])==r['sha256'] for r in inputs)
output=O/'field-diff.json';assert not output.exists()
atomic_json(output,{'status':'REVIEWABLE_FIELD_DIFF_ONLY_NOT_APPLIED','changed_annotation_records':106,'changed_gt_records':63,'dataset_counts':dataset_counts,'changes':reports,'source_files':inputs,'proposal_sha256':digest(O/'validation.json'),'independent_endpoint_check_sha256':digest(O/'independent-prospective-validation.json'),'existing_derivative_rule_sha256':digest(R/'scripts/build_derived_annotations.py'),'script_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'Only in-memory copies edited. Original and existing derived files unchanged. No new data directory, protocol activation, formal rerun or registration. Exact matching reference nodes and63GT starts follow existing authorized nine-task transformation semantics; authorization to expand scope remains pending.'})
print(dataset_counts,'GT',gt_count)

