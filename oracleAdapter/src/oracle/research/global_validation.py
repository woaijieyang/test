"""Uniform source-priority mapping selection and complete Landmark validation."""
from collections import Counter
import copy,hashlib,json
from pathlib import Path
from oracle.common.artifacts import content_digest,digest,owned_output,write_json,package_sources,freeze_sources,timestamp
from oracle.common.task_index import merkle_index
from oracle.research.full_worker import load_task


def select_task(original,body,dense,held,source_digest):
    if original['dataset']!='landmark_rxr':raise ValueError('Sealed R2R/RxR excluded')
    passed=body['status']=='PASS_GLOBAL_PROPOSAL_RATIONAL_STATIC_NOT_MOTION'
    if held and (passed or dense is not None):raise ValueError('Held task cannot acquire a new mapping')
    t=copy.deepcopy(original);family='unchanged'
    if passed:
        if (body['task_key']!=t['task_key'] or body['old_targets']!=t['targets']
                or body['original_heading']!=t['raw_heading'] or body['legacy_source_record_sha256']!=t['legacy_source_record_sha256']):raise ValueError('Body mapping identity mismatch')
        chosen=body;family='source_bounded_body'
        if dense is not None:
            if (dense['task_key']!=t['task_key'] or dense['old_targets']!=t['targets']
                    or dense['original_heading']!=t['raw_heading'] or dense['source_record_sha256']!=t['source_record_sha256']):raise ValueError('Dense mapping identity mismatch')
            chosen=dense;family='official_dense_trace'
        points=chosen['proposed_targets']
        if not points or len(points)!=len(t['targets']):raise ValueError('Ordered occurrence count changed')
        t['targets']=copy.deepcopy(points)
        # A changed reference protocol cannot silently inherit a whole-episode
        # action prefix solely because the old initial pose happened to match.
        t.pop('official_demonstration',None);t.pop('reference_action_pose_relation',None)
        t['privileges']=[x for x in t['privileges'] if x!='official_actions']
        t['method_selection']={'official_policy':'none','reason':'Changed mapping uses matched pure-search protocol; no inherited unaligned action prefix'}
    elif dense is not None:raise ValueError('Dense priority outside frozen audited candidate scope')
    t['module_source_sha256']=source_digest
    t['global_mapping_selection']={'family':family,'held_preserved':held,'old_task_sha256':content_digest(original),
        'old_targets_sha256':content_digest(original['targets']),'executed_targets_sha256':content_digest(t['targets']),
        'navigation_results_used_for_selection':False,'raw_annotation_unchanged':True}
    t['cohort']='landmark_global_cached::'+family+'::'+t['method_selection']['official_policy']
    return t


def prepare(case_root,output):
    root=Path(case_root).resolve();output=owned_output(root,output);package,sources=package_sources()
    if output.exists():raise FileExistsError(output)
    cfg_path=package/'configs/experiments/global_landmark_validation_v1.json';cfg=json.loads(cfg_path.read_text())
    paths={k:root/v['path'] for k,v in cfg['inputs'].items()}
    for k,p in paths.items():
        if digest(p)!=cfg['inputs'][k]['sha256']:raise ValueError('Frozen prerequisite changed: '+k)
    ga=json.loads(paths['global_audit'].read_text());gr_path=paths['global_audit'].parent/'all33954-records.json'
    if digest(gr_path)!=ga['records_sha256'] or ga['records']!=33954:raise ValueError('Global static audit incomplete/changed')
    body={r['task_key']:r for r in json.loads(gr_path.read_text())}
    if len(body)!=33954:raise ValueError('Global static task identity duplicates')
    da=json.loads(paths['dense_audit'].read_text());dr_path=paths['dense_audit'].parent/'records.json';ds_path=paths['dense_audit'].parent/'sealed-proposal-hashes.json'
    if digest(dr_path)!=da['records_sha256'] or digest(ds_path)!=da['sealed_proposal_hashes_sha256']:raise ValueError('Dense source audit changed')
    sealed=json.loads(ds_path.read_text());dense={}
    for r in json.loads(dr_path.read_text()):
        if r['status']!='PASS_INDEPENDENT_STATIC_NOT_MOTION':raise ValueError('Dense priority includes failed static result')
        p=root/'outputs/oracleAdapter/dense-ordered-mapping-v1/tasks'/f"{r['task_key'].replace(':','-')}.json"
        if digest(p)!=r['proposal_sha256'] or digest(p)!=sealed[str(p.resolve())]:raise ValueError('Dense coordinates changed')
        dense[r['task_key']]=json.loads(p.read_text())
    positive={k for k,r in body.items() if r['status']=='PASS_GLOBAL_PROPOSAL_RATIONAL_STATIC_NOT_MOTION'}
    if len(positive)!=2654 or len(dense)!=93 or not set(dense)<=positive:raise ValueError('Declared mapping selection scope changed')
    held=set(json.loads(paths['held'].read_text())['task_keys'])
    if len(held)!=114 or held&positive:raise ValueError('Held scope changed')
    parent=paths['parent_manifest'].parent;pm=json.loads(paths['parent_manifest'].read_text())
    if digest(parent/'tasks.jsonl')!=pm['tasks_file_sha256'] or digest(parent/'index.json')!=pm['index_sha256']:raise ValueError('Frozen parent stream changed')
    indexes=json.loads((parent/'index.json').read_text())
    previous=json.loads(paths['old_full_review'].read_text())['cumulative_charged_cpu_upper_bound_seconds']
    previous+=json.loads(paths['matrix_closure'].read_text())['charged_cpu_upper_bound_seconds']
    previous+=json.loads(paths['D7_closure'].read_text())['charged_cpu_upper_bound_seconds']
    if previous+cfg['total_cpu_budget_hours']*3600>720*3600:raise ValueError('Original720CPUh cap exceeded')
    cache=json.loads((package/'configs/methods/reference_progress_cache_v1.json').read_text())['planning_query_cache']
    method={**pm['base_method'],'planning_query_cache':cache}
    output.mkdir();entries=[];selection=[];counts=Counter();splits=Counter();changed_count=0
    with (output/'tasks.jsonl').open('xb') as f:
        for e in indexes:
            if e['record']['dataset']!='landmark_rxr':continue
            original,_=load_task(root,pm,e,parent/'tasks.jsonl');key=original['task_key']
            task=select_task(original,body[key],dense.get(key),key in held,content_digest(sources))
            changed=task['targets']!=original['targets'];changed_count+=changed
            family=task['global_mapping_selection']['family'];counts[task['cohort']]+=1;splits[task['split']]+=1
            data=(json.dumps(task,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode();offset=f.tell();f.write(data)
            entries.append({'task_key':key,'dataset':'landmark_rxr','offset':offset,'bytes':len(data),
                'sha256':hashlib.sha256(data).hexdigest(),'cohort':task['cohort']})
            selection.append({'task_key':key,'family':family,'targets_changed':changed,'held':key in held,
                'original_task_sha256':content_digest(original),'executed_task_sha256':content_digest(task),
                'old_targets_sha256':content_digest(original['targets']),'new_targets_sha256':content_digest(task['targets'])})
    if len(entries)!=33954 or len({e['task_key'] for e in entries})!=33954 or set(body)!={e['task_key'] for e in entries}:raise ValueError('Full Landmark scope differs')
    if changed_count!=2654 or sum(r['held'] for r in selection)!=114:raise ValueError('Mapping/held alteration count differs')
    merkle,index=merkle_index(entries);write_json(output/'index.json',index);write_json(output/'selection33954.json',selection)
    config={**pm['config'],'max_workers':cfg['max_workers'],'total_cpu_budget_hours':cfg['total_cpu_budget_hours'],
        'maximum_infrastructure_attempts':1,'expected':{'landmark_rxr':33954},'scope':cfg['scope'],
        'policy':cfg['selection_policy'],'method_config':'frozen_base_method_with_exact_query_cache'}
    manifest={'status':'FROZEN_FULL33954_SOURCE_PRIORITY_CACHED_VALIDATION','created_at':timestamp(),
        'config':config,'protocol':pm['protocol'],'base_method':method,'sources':sources,'task_count':33954,
        'datasets':{'landmark_rxr':33954},'splits':dict(splits),'information_mapping_groups':dict(counts),
        'task_merkle_root':merkle,'tasks_file_sha256':digest(output/'tasks.jsonl'),'index_sha256':digest(output/'index.json'),
        'selection_sha256':digest(output/'selection33954.json'),'changed_targets_tasks':changed_count,'held114_preserved':114,
        'prior_full_charge_seconds':previous,'original_full_budget_hours':720,
        'input_hashes':{k:digest(p) for k,p in paths.items()},'scope':cfg['scope'],
        'target_scope':'All original ordered reference occurrences and mandatory endpoint-source gates; candidate mappings explicit',
        'official_action_sources':pm.get('official_action_sources',[]),
        'launchers':{str(root/'oracleAdapter/run.py'):digest(root/'oracleAdapter/run.py'),str(root/'scripts/with_runtime.sh'):digest(root/'scripts/with_runtime.sh')},
        'limits':'Fresh full Landmark run, no oldPASS copying or per-task outcome selection. Changed mappings have no official-action prefix; unchanged inputs keep original fixed information policy. Report groups separately. Static3411 and other failures remain in denominator; no automatic model evaluation or publication.'}
    write_json(output/'manifest.json',manifest);freeze_sources(output,sources)
    write_json(output/'state.json',{'status':'PREPARED_NOT_RUN','expected':33954,'completed':0})
    return manifest


def run_with_review(case_root,manifest_path):
    root=Path(case_root).resolve();mp=Path(manifest_path);run=owned_output(root,mp.parent)
    if (run/'controller-process.json').exists():raise ValueError('Existing full run requires review before any resume')
    from oracle.research.full_run import run as execute
    from oracle.research.full_review import review
    from oracle.research.full_report import report
    if not execute(root,mp):raise RuntimeError('Full Landmark run stopped; inspect preserved evidence, no automatic retry')
    closure=json.loads((run/'source-freeze.json').read_text())
    if closure['status']!='CLOSED' or closure['live_phase_receipts']:raise RuntimeError('Owned phases remain live')
    review(root,run,run/'independent-full-review')
    report(root,run,run/'independent-full-review/validation.json',run/'grouped-report')
    write_json(run/'review-complete.json',{'status':'FULL33954_EXECUTION_AND_INDEPENDENT_REVIEW_COMPLETE','manifest_sha256':digest(mp),
        'report_sha256':digest(run/'grouped-report/validation.json'),'all_navigation_gates_passed':json.loads((run/'independent-full-review/validation.json').read_text())['all_navigation_gates_passed']})
    write_json(run/'state.json',{'status':'COMPLETE_FULL33954_REVIEW','completed':33954,'expected':33954,'time':timestamp()},immutable=False)
