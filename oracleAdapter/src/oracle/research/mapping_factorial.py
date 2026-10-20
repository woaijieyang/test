"""Affected-scope mapping x query-cache controls; all four arms re-executed."""
import copy,hashlib,json,os,subprocess,sys,time,zipfile
from collections import Counter
from pathlib import Path
from oracle.common.artifacts import content_digest,digest,owned_output,write_json,package_sources,freeze_sources,require_sources,timestamp
from oracle.common.task_index import merkle_index
from oracle.research.full_worker import load_task,process_identity


def summarize_factorial(rows_by_arm,keys):
    names=['original_map_uncached','original_map_cache','candidate_map_uncached','candidate_map_cache']
    if set(rows_by_arm)!=set(names) or len(set(keys))!=len(keys):raise ValueError('Explicit four-arm scope required')
    passed={};cells={};allowed={'PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES','ROUTE_WITNESS_ONLY_ENDPOINT_SOURCE_GATE_FAIL','FAILURE_PRESERVED','STATIC_FAILURE_PRESERVED'}
    for name in names:
        rows=rows_by_arm[name]
        if len(rows)!=len(keys) or {r['task_key'] for r in rows}!=set(keys) or any(r['status'] not in allowed for r in rows):
            raise ValueError('Missing, duplicate or unresolved factorial result')
        passed[name]={r['task_key'] for r in rows if r['status']=='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES'}
        cells[name]={'tasks':len(rows),'strict_pass':len(passed[name]),'statuses':dict(Counter(r['status'] for r in rows))}
    contrasts={}
    for label,old,new in [('mapping_at_uncached',names[0],names[2]),('mapping_at_cache',names[1],names[3]),
                           ('cache_at_original_mapping',names[0],names[1]),('cache_at_candidate_mapping',names[2],names[3])]:
        a,b=passed[old],passed[new]
        contrasts[label]={'control':old,'candidate':new,'recovered':sorted(b-a),'regressed':sorted(a-b),
            'retained_pass':sorted(a&b),'both_failed':sorted(set(keys)-a-b)}
    return dict(cells=cells,contrasts=contrasts)


def report_matrix(case_root,matrix_path,output):
    root=Path(case_root).resolve();matrix=owned_output(root,matrix_path);output=owned_output(root,output)
    if output.exists():raise FileExistsError(output)
    mp=matrix/'manifest.json';m=json.loads(mp.read_text());closure=json.loads((matrix/'validation.json').read_text())
    if closure['manifest_sha256']!=digest(mp) or closure['executions']!=372:raise ValueError('Matrix incomplete')
    tables={};task_streams={};costs={};bindings={}
    for arm in m['arms']:
        p=Path(arm['manifest']);run=p.parent;am=json.loads(p.read_text());v=json.loads((run/'validation.json').read_text())
        review=run/'independent-full-review/validation.json';report=run/'grouped-report/validation.json'
        rv=json.loads(review.read_text());cv=json.loads(report.read_text())
        if digest(p)!=arm['manifest_sha256'] or rv['manifest_sha256']!=digest(p) or cv['manifest_sha256']!=digest(p) or rv['records']!=93:
            raise ValueError('Independent arm identity/scope differs')
        if digest(run/'results-index.json')!=v['results_index_sha256'] or cv['independent_review_sha256']!=digest(review):raise ValueError('Result evidence changed')
        tables[arm['id']]=json.loads((run/'results-index.json').read_text())
        if digest(run/'tasks.jsonl')!=am['tasks_file_sha256']:raise ValueError('Arm inputs changed')
        task_streams[arm['id']]={t['task_key']:t for t in map(json.loads,(run/'tasks.jsonl').read_text().splitlines())}
        costs[arm['id']]=dict(grouped_report=str(report),grouped_report_sha256=digest(report),
            actual_actions=rv['actual_actions'],independently_replayed_actions=rv['independently_replayed_actions'],
            measured_phase_cpu_seconds=sum(r['costs']['process_cpu_seconds']['sum'] or 0 for r in cv['phase_costs_including_failed_attempts'].values()),
            charged_cpu_upper_bound_seconds=v['charged_cpu_upper_bound_seconds'])
        bindings[arm['id']]={'manifest_sha256':digest(p),'review_sha256':digest(review),'report_sha256':digest(report)}
    for mapping in ['original','candidate']:
        if task_streams[mapping+'_map_uncached']!=task_streams[mapping+'_map_cache']:raise ValueError('Oracle axis changed physical task/input')
    for key in m['original_task_keys']:
        old=task_streams['original_map_uncached'][key];new=task_streams['candidate_map_uncached'][key]
        exclude={'targets','cohort','mapping_study_provenance'}
        if {k:v for k,v in old.items() if k not in exclude}!={k:v for k,v in new.items() if k not in exclude}:raise ValueError('Mapping axis changed unapproved fields')
    summary=summarize_factorial(tables,m['original_task_keys'])
    summary.update(status='COMPLETE_MATCHED93_FOUR_ARM_EVIDENCE_NOT_GLOBAL_ACCEPTANCE',affected_tasks=93,executions=372,
        global_landmark_denominator=33954,all_global_gates_passed=False,costs=costs,bindings=bindings,
        manifest_sha256=digest(mp),limits=['No official-action payload in any arm; do not mix with the prior official-prefix development.',
            'Control is the current lossless bounded-search executor with query cache disabled, not historical quantized RobustOracle.',
            'Mapping changes target coordinates within the audited source bounds, not body/action/acceptance limits; mapping and cache contrasts stay separate.',
            'Only93affected candidates evaluated here; all other33861includingheld114remain in global scope, not newly accepted.',
            'Not blind generalization, a posthoc union, model score, complete physics proof, or permission to publish.'])
    output.mkdir();_,sources=package_sources();freeze_sources(output,sources);write_json(output/'summary.json',summary)
    lines=['# Matched Landmark93 mapping/cache factorial','',
           '| Mapping / Oracle | Strict pass / tasks | Actual actions / replay | Phase CPU seconds |',
           '|---|---:|---:|---:|']
    for name,c in summary['cells'].items():
        k=costs[name];lines.append(f"|{name}|{c['strict_pass']}/{c['tasks']}|{k['actual_actions']}/{k['independently_replayed_actions']}|{k['measured_phase_cpu_seconds']:.3f}|")
    for name,c in summary['contrasts'].items():lines.append(f"\n{name}: recovered={len(c['recovered'])}, regressed={len(c['regressed'])}, retained={len(c['retained_pass'])}, both_failed={len(c['both_failed'])}.")
    lines+=['','Limits:']+['- '+x for x in summary['limits']]
    (output/'report.md').write_text('\n'.join(lines)+'\n')
    write_json(output/'validation.json',{'status':summary['status'],'summary_sha256':digest(output/'summary.json'),'report_sha256':digest(output/'report.md'),'records':372})
    return summary


def variant_task(original,proposal,use_candidate,module_source_sha256,proposal_sha256):
    if original['dataset']!='landmark_rxr':raise ValueError('Sealed R2R/RxR cannot enter mapping study')
    targets=proposal['proposed_targets'] if use_candidate else original['targets']
    if not targets or len(targets)!=len(original['targets']):raise ValueError('Reference occurrence count changed')
    task=copy.deepcopy(original);task.pop('official_demonstration',None)
    task.pop('reference_action_pose_relation',None)
    task['privileges']=[p for p in task['privileges'] if p!='official_actions']
    task['targets']=copy.deepcopy(targets)
    task['module_source_sha256']=module_source_sha256
    task['method_selection']={'official_policy':'none','reason':'Action payload withheld in every factorial arm; matched input-information category'}
    variant='candidate_mapping' if use_candidate else 'original_mapping'
    task['cohort']='landmark_affected93_pure_search::'+variant
    task['mapping_study_provenance']={'variant':variant,'original_task_sha256':content_digest(original),
        'original_targets_sha256':content_digest(original['targets']),'proposal_sha256':proposal_sha256,
        'executed_targets_sha256':content_digest(targets),'original_record_unchanged':True}
    return task


def prepare(case_root,output):
    root=Path(case_root).resolve();output=owned_output(root,output);package,sources=package_sources()
    if output.exists():raise FileExistsError(output)
    cfg_path=package/'configs/experiments/mapping_factorial_v1.json';cfg=json.loads(cfg_path.read_text())
    audit_path=root/cfg['static_audit'];a=json.loads(audit_path.read_text())
    if digest(audit_path)!=cfg['static_audit_sha256'] or a['results']!={'PASS_INDEPENDENT_STATIC_NOT_MOTION':93}:
        raise ValueError('Independent static candidate set differs')
    checked_path=audit_path.parent/'records.json';sealed_path=audit_path.parent/'sealed-proposal-hashes.json'
    if digest(checked_path)!=a['records_sha256'] or digest(sealed_path)!=a['sealed_proposal_hashes_sha256']:raise ValueError('Audited proposal bytes changed')
    checked=json.loads(checked_path.read_text());sealed=json.loads(sealed_path.read_text())
    producer=root/cfg['producer'];pv=json.loads((producer/'validation.json').read_text())
    if digest(producer/'validation.json')!=a['producer_validation_sha256'] or pv['records']!=33954:raise ValueError('Original full candidate scope changed')
    parent=root/'outputs/oracleAdapter/full-continuous-reference-v1';pm=json.loads((parent/'manifest.json').read_text())
    if digest(parent/'manifest.json')!=cfg['parent_manifest_sha256']:raise ValueError('Original task source changed')
    indexes={e['record']['task_key']:e for e in json.loads((parent/'index.json').read_text())}
    previous_path=root/'outputs/oracleAdapter/logical-full-review-v1/validation.json';previous=json.loads(previous_path.read_text())
    max_new=3600+4*cfg['per_arm_cpu_hours']*3600
    if previous['cumulative_charged_cpu_upper_bound_seconds']+max_new>720*3600:raise ValueError('Cumulative full validation allocation exceeds720CPUh')
    cache_cfg=json.loads((package/'configs/methods/reference_progress_cache_v1.json').read_text())['planning_query_cache']
    cache_gate=root/'outputs/oracleAdapter/cache-equivalence71-v2'
    with zipfile.ZipFile(cache_gate/'source.zip') as z:
        for n in ['planners/collision_queries.py','verification/source_scene.py']:
            if hashlib.sha256(z.read(n)).hexdigest()!=sources[n]:raise ValueError('Cache equivalence gate no longer binds actual query code')
    tasks=[]
    for row in sorted(checked,key=lambda r:r['task_key']):
        p=producer/'tasks'/f"{row['task_key'].replace(':','-')}.json"
        if digest(p)!=row['proposal_sha256'] or digest(p)!=sealed[str(p.resolve())]:raise ValueError('Proposal changed after independent audit')
        proposal=json.loads(p.read_text());original,_=load_task(root,pm,indexes[row['task_key']],parent/'tasks.jsonl')
        if proposal['old_targets']!=original['targets']:raise ValueError('Candidate does not belong to original mapping')
        tasks.append((original,proposal,digest(p)))
    if len(tasks)!=93 or len({t[0]['task_key'] for t in tasks})!=93:raise ValueError('Affected93 denominator changed')
    output.mkdir();freeze_sources(output,sources);arms=[]
    for mapping,cached in [('original',False),('original',True),('candidate',False),('candidate',True)]:
        arm_id=mapping+'_map_'+('cache' if cached else 'uncached');run=output/'runs'/arm_id;run.mkdir(parents=True)
        method={**pm['base_method'],'id':'bounded_reference_search_exact_cache_v1' if cached else 'bounded_reference_search_uncached_v1'}
        if cached:method['planning_query_cache']=cache_cfg
        entries=[]
        with (run/'tasks.jsonl').open('xb') as stream:
            for original,proposal,sha in tasks:
                task=variant_task(original,proposal,mapping=='candidate',content_digest(sources),sha)
                raw=(json.dumps(task,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
                offset=stream.tell();stream.write(raw)
                entries.append({'task_key':task['task_key'],'dataset':'landmark_rxr','offset':offset,'bytes':len(raw),
                    'sha256':hashlib.sha256(raw).hexdigest(),'cohort':task['cohort']})
        merkle,index=merkle_index(entries);write_json(run/'index.json',index)
        config={**pm['config'],'max_workers':cfg['max_workers'],'per_process_wall_seconds':900,
            'total_cpu_budget_hours':cfg['per_arm_cpu_hours'],'maximum_infrastructure_attempts':1,
            'expected':{'landmark_rxr':93},'scope':cfg['scope'],'method_config':'explicit_frozen_base_method_in_manifest'}
        manifest={'status':'FROZEN_AFFECTED93_FACTORIAL_ARM','created_at':timestamp(),'config':config,'protocol':pm['protocol'],
            'base_method':method,'sources':sources,'task_count':93,'datasets':{'landmark_rxr':93},
            'task_merkle_root':merkle,'tasks_file_sha256':digest(run/'tasks.jsonl'),'index_sha256':digest(run/'index.json'),
            'launchers':{str(root/'oracleAdapter/run.py'):digest(root/'oracleAdapter/run.py'),str(root/'scripts/with_runtime.sh'):digest(root/'scripts/with_runtime.sh')},
            'scope':cfg['scope'],'target_scope':'all_original_Landmark_reference_occurrences_including_mandatory_endpoint_source_gate',
            'official_action_sources':[],'factorial_arm':{'id':arm_id,'mapping':mapping,'cache':cached},
            'global_landmark_denominator':33954,'candidate_audit_sha256':digest(audit_path),'parent_manifest_sha256':digest(parent/'manifest.json')}
        write_json(run/'manifest.json',manifest);freeze_sources(run,sources)
        write_json(run/'state.json',{'status':'PREPARED_NOT_RUN','expected':93,'completed':0})
        arms.append({'id':arm_id,'manifest':str(run/'manifest.json'),'manifest_sha256':digest(run/'manifest.json'),'mapping':mapping,'cache':cached})
    m={'status':'FROZEN_FOUR_ARM_MAPPING_CONTROL','created_at':timestamp(),'sources':sources,'config':cfg,'arms':arms,
       'original_task_keys':[t[0]['task_key'] for t in tasks],'affected_tasks':93,'expected_executions':372,
       'global_landmark_denominator':33954,'old_full_charge_seconds':previous['cumulative_charged_cpu_upper_bound_seconds'],
       'old_full_review_sha256':digest(previous_path),'new_matrix_cpu_upper_seconds':max_new,'all_movement_gates_passed':False}
    write_json(output/'manifest.json',m);return m


def run_matrix(case_root,manifest_path):
    root=Path(case_root).resolve();mp=Path(manifest_path);out=owned_output(root,mp.parent);m=json.loads(mp.read_text());require_sources(m['sources'])
    if (out/'controller-process.json').exists():raise ValueError('Existing matrix attempt requires explicit evidence review, not restart')
    import resource
    resource.setrlimit(resource.RLIMIT_CPU,(3600,3605));os.nice(10)
    write_json(out/'controller-process.json',{**process_identity(),'manifest_sha256':digest(mp),'started_at':timestamp()})
    write_json(out/'source-freeze.json',{'status':'OPEN','manifest_sha256':digest(mp)})
    completed=[];code=0
    try:
        for arm in m['arms']:
            require_sources(m['sources']);ap=Path(arm['manifest'])
            if digest(ap)!=arm['manifest_sha256']:raise ValueError('Frozen factorial arm changed')
            write_json(out/'state.json',{'status':'RUNNING_ARM','arm':arm['id'],'completed_arms':completed,'time':timestamp()},immutable=False)
            cmd=[sys.executable,'-B',str(root/'oracleAdapter/run.py'),'run-full-validation','--case-root',str(root),'--manifest',str(ap)]
            with (out/(arm['id']+'.log')).open('xb') as log:
                child=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
                ticks=Path(f'/proc/{child.pid}/stat').read_text().rsplit(')',1)[1].split()[19]
                write_json(out/(arm['id']+'.process.json'),dict(pid=child.pid,start_ticks=ticks,command=cmd))
                code=child.wait()
            if code or not (ap.parent/'validation.json').exists():raise RuntimeError('Arm stopped before complete independent accounting: '+arm['id'])
            closure=json.loads((ap.parent/'source-freeze.json').read_text())
            if closure['status']!='CLOSED' or closure['live_phase_receipts']:raise RuntimeError('Owned phase still live after arm')
            from oracle.research.full_review import review
            review(root,ap.parent,ap.parent/'independent-full-review')
            from oracle.research.full_report import report
            report(root,ap.parent,ap.parent/'independent-full-review/validation.json',ap.parent/'grouped-report')
            completed.append(arm['id'])
        charged=3605+sum(json.loads((Path(a['manifest']).parent/'validation.json').read_text())['charged_cpu_upper_bound_seconds'] for a in m['arms'])
        if charged>m['new_matrix_cpu_upper_seconds']+5:raise RuntimeError('Matrix CPU charge exceeded declaration')
        write_json(out/'validation.json',{'status':'COMPLETE372_FACTORIAL_EXECUTIONS_PENDING_PAIRED_REPORT','executions':372,
            'completed_arms':completed,'manifest_sha256':digest(mp),'charged_cpu_upper_bound_seconds':charged,
            'global_landmark_denominator':33954,'all_global_gates_passed':False})
        write_json(out/'state.json',{'status':'COMPLETE_PENDING_FACTORIAL_REPORT','completed_arms':completed,'time':timestamp()},immutable=False)
        report_matrix(root,out,out/'factorial-report')
        write_json(out/'state.json',{'status':'COMPLETE_FACTORIAL_REVIEW_NOT_GLOBAL_ACCEPTANCE','completed_arms':completed,'time':timestamp()},immutable=False)
    except BaseException as error:
        write_json(out/'failure.json',{'error':repr(error),'completed_arms':completed,'time':timestamp()})
        write_json(out/'state.json',{'status':'STOPPED_FOR_EVIDENCE_REVIEW','error':repr(error),'completed_arms':completed},immutable=False)
        raise
    finally:
        live=[]
        from oracle.research.full_run import live as is_live
        for arm in m['arms']:
            for p in Path(arm['manifest']).parent.glob('jobs/*/*/*/start.json'):
                if is_live(json.loads(p.read_text())):live.append(str(p))
        write_json(out/'source-freeze.json',{'status':'OPEN' if live else 'CLOSED','live_phase_receipts':live,'manifest_sha256':digest(mp)},immutable=False)
