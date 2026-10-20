"""One fixed priority comparison, with identical physical tasks and budgets."""
import copy
import hashlib
import json
import os
from pathlib import Path

from oracle.common.artifacts import content_digest, digest, owned_output, write_json, package_sources, freeze_sources, require_sources, timestamp
from oracle.common.task_index import merkle_index
from oracle.research.full_worker import process_identity,validate_launchers

PASS='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES'
IDS=('reference_priority1_control','reference_priority2_candidate')


def make_task(original,source_digest):
    if original.get('dataset')!='landmark_rxr' or original.get('split')!='train':
        raise ValueError('Only selected Landmark train development tasks; sealed datasets excluded')
    if ('official_demonstration' in original or 'official_actions' in original['privileges']
            or original['method_selection']['official_policy']!='none'):
        raise ValueError('Priority comparison requires the fixed pure-search information condition')
    task=copy.deepcopy(original)
    task.update(module_source_sha256=source_digest,cohort='fixed_landmark_priority_development')
    return task


def method_pair(base):
    return [{**copy.deepcopy(base),'id':name,'search_priority_weight':weight}
            for name,weight in zip(IDS,(1.,2.))]


def compare_outcomes(control,candidate,success_controls):
    if not control or set(control)!=set(candidate) or not set(success_controls)<=set(control):
        raise ValueError('Complete matched task scope required')
    a={k for k,v in control.items() if v};b={k for k,v in candidate.items() if v}
    lost_controls=sorted(k for k in success_controls if k not in a or k not in b)
    return dict(recovered=sorted(b-a),regressed=sorted(a-b),retained_pass=sorted(a&b),
                both_failed=sorted(set(control)-a-b),success_control_failures=lost_controls,
                development_promotion_gate=bool(b-a) and not (a-b) and not lost_controls,
                global_acceptance=False)


def combined_controller_charge(charges,identities,owner):
    expected=(owner['pid'],str(owner['start_ticks']))
    if not charges or len(charges)!=len(identities) or any(x<3605 for x in charges):
        raise ValueError('Every arm must retain its full controller reservation')
    if any((r['pid'],str(r['start_ticks']))!=expected for r in identities):
        raise ValueError('Different controller processes cannot share one CPU reservation')
    return sum(charges)-3605*(len(charges)-1)


def comparable_methods(methods,kind='fixed_priority'):
    excluded={'fixed_priority':{'id','search_priority_weight'},
              'soft_priority':{'id','soft_duplicate_priority'}}
    if kind not in excluded:raise ValueError('Unknown paired comparison kind')
    return len(methods)==2 and ({k:v for k,v in methods[0].items() if k not in excluded[kind]}
        =={k:v for k,v in methods[1].items() if k not in excluded[kind]})


def prepare(case_root,output):
    root=Path(case_root).resolve();output=owned_output(root,output);package,sources=package_sources()
    cfg=json.loads((package/'configs/experiments/reference_priority_development_v1.json').read_text())
    if (cfg['arms']!=[{'id':name,'search_priority_weight':weight} for name,weight in zip(IDS,(1.,2.))]
            or cfg['expected_executions']!=32 or not cfg['sequential_arms'] or not 1<=cfg['max_workers']<=32):
        raise ValueError('Only the predeclared two fixed priorities and bounded resources are authorized')
    budget_path=root/cfg['budget_receipt'];admission=json.loads(budget_path.read_text())
    if (digest(budget_path)!=cfg['budget_receipt_sha256'] or admission['next_stage_reservation_seconds']!=43200
            or admission['status']!='ADMITTED_WITH_CONSERVATIVE_LEGACY_RESERVATIONS_NOT_EXACT_HISTORICAL_CPU'
            or admission['overall_including_next_stage_reservation_seconds']>cfg['overall_cpu_hours_cap']*3600):
        raise ValueError('Frozen stage reservation differs')
    if admission['legacy_development_charge_seconds']+43200>cfg['original_development_cpu_hours_cap']*3600:
        raise ValueError('Original development envelope exhausted')
    full=root/'outputs/oracleAdapter/landmark-global-source-priority-v1'
    closure=json.loads((full/'source-freeze.json').read_text())
    if closure['status']!='CLOSED' or closure['live_phase_receipts'] or not (full/'review-complete.json').is_file():
        raise ValueError('Prior full run and independent audit must be closed')
    if digest(root/cfg['current_full_closeout'])!=admission['full_closeout_sha256']:
        raise ValueError('Full closeout differs from budget admission')
    selected_path=root/cfg['selection_file'];selected=json.loads(selected_path.read_text())
    if digest(selected_path)!=cfg['selection_sha256'] or len(selected)!=cfg['expected_tasks']:
        raise ValueError('Preselected16 scope changed')
    mp=root/cfg['source_manifest'];parent=mp.parent;pm=json.loads(mp.read_text())
    if digest(mp)!=cfg['source_manifest_sha256'] or digest(parent/'tasks.jsonl')!=pm['tasks_file_sha256']:
        raise ValueError('Historical source stream changed')
    originals={t['task_key']:t for t in map(json.loads,(parent/'tasks.jsonl').read_text().splitlines())}
    tasks=[]
    for row in selected:
        original=originals[row['task_key']]
        if content_digest(original)!=row['task_sha256']:raise ValueError('Selected task bytes differ')
        tasks.append(make_task(original,content_digest(sources)))
    if len({t['task_key'] for t in tasks})!=16:raise ValueError('Duplicate development task')
    failed=root/cfg['retained_failed_run'];fm=json.loads((failed/'manifest.json').read_text())
    if (not (failed/'failure.json').exists() or json.loads((failed/'source-freeze.json').read_text())['status']!='CLOSED'
            or list(failed.glob('runs/*/jobs/*/*/*/start.json')) or list(failed.glob('runs/*/jobs/*/*/execute/motion/result.json'))):
        raise ValueError('Previous failure is not the sealed pre-native launcher failure')
    from oracle.research.full_run import live
    if live(json.loads((failed/'controller-process.json').read_text())):raise ValueError('Prior controller remains live')
    failed_charge=sum(json.loads((Path(a['manifest']).parent/'state.json').read_text())['charged_cpu_upper_bound_seconds']
                      for a in fm['arms'] if (Path(a['manifest']).parent/'state.json').exists())
    maximum=2*cfg['per_arm_cpu_hours']*3600-3605
    if maximum+failed_charge+3600>cfg['stage_cpu_hours_cap']*3600:
        raise ValueError('Prior failed attempt plus new study exceed the same stage allocation')
    output.mkdir();freeze_sources(output,sources);arms=[]
    for method in method_pair(pm['base_method']):
        run=output/'runs'/method['id'];run.mkdir(parents=True);entries=[]
        with (run/'tasks.jsonl').open('xb') as stream:
            for task in tasks:
                raw=(json.dumps(task,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
                offset=stream.tell();stream.write(raw)
                entries.append(dict(task_key=task['task_key'],dataset='landmark_rxr',offset=offset,bytes=len(raw),
                                    sha256=hashlib.sha256(raw).hexdigest(),cohort=task['cohort']))
        merkle,index=merkle_index(entries);write_json(run/'index.json',index)
        config={**pm['config'],'max_workers':cfg['max_workers'],'total_cpu_budget_hours':cfg['per_arm_cpu_hours'],
                'maximum_infrastructure_attempts':1,'expected':{'landmark_rxr':16},'scope':cfg['scope'],
                'method_config':'explicit frozen priority arm with unchanged remaining parameters'}
        manifest={'status':'FROZEN_FIXED16_PRIORITY_DEVELOPMENT_ARM','created_at':timestamp(),'config':config,
            'protocol':pm['protocol'],'base_method':method,'sources':sources,'task_count':16,
            'datasets':{'landmark_rxr':16},'task_merkle_root':merkle,'tasks_file_sha256':digest(run/'tasks.jsonl'),
            'index_sha256':digest(run/'index.json'),'scope':cfg['scope'],
            'target_scope':pm['target_scope'],'official_action_sources':[],
            'limits':'Fixed16 known Landmark train tasks, two priorities, all outcomes retained; not global acceptance.',
            'launchers':{str(p):digest(p) for p in [root/'oracleAdapter/run.py',root/'scripts/with_runtime.sh']}}
        validate_launchers(root,manifest)
        write_json(run/'manifest.json',manifest);freeze_sources(run,sources)
        arms.append(dict(id=method['id'],manifest=str(run/'manifest.json'),manifest_sha256=digest(run/'manifest.json')))
    outer=dict(status='FROZEN_FIXED16_TWO_PRIORITY_ARMS',created_at=timestamp(),sources=sources,config=cfg,
               selected=selected,arms=arms,maximum_cpu_seconds=maximum,retained_failed_charge_seconds=failed_charge,
               retained_failure_manifest_sha256=digest(failed/'manifest.json'),budget_receipt_sha256=digest(budget_path),
               expected_tasks=16,expected_executions=32,global_landmark_denominator=33954)
    write_json(output/'manifest.json',outer)
    return outer


def report(root,run):
    m=json.loads((run/'manifest.json').read_text());tables={};costs={};streams=[];methods=[];environments={};rows=[]
    for arm in m['arms']:
        ap=Path(arm['manifest']);am=json.loads(ap.read_text());folder=ap.parent
        if digest(ap)!=arm['manifest_sha256']:raise ValueError('Arm manifest drift')
        iv=json.loads((folder/'independent-full-review/validation.json').read_text())
        rv=json.loads((folder/'grouped-report/validation.json').read_text())
        if iv['records']!=16 or rv['records']!=16 or rv['independent_review_sha256']!=digest(folder/'independent-full-review/validation.json'):
            raise ValueError('Complete independent arm review required')
        task_path=folder/'grouped-report/task-costs.json'
        if digest(task_path)!=rv['outputs_sha256']['task-costs.json']:raise ValueError('Task evidence drift')
        records=json.loads(task_path.read_text());table={x['task_key']:x for x in records}
        if len(table)!=len(records) or len(table)!=16:raise ValueError('Arm scope duplicates or omissions')
        tables[arm['id']]={k:x['status']==PASS for k,x in table.items()}
        streams.append((folder/'tasks.jsonl').read_bytes());methods.append(am['base_method'])
        costs[arm['id']]=dict(accepted=sum(tables[arm['id']].values()),
            process_cpu_seconds=sum(x['costs']['process_cpu_seconds']['sum'] for x in rv['phase_costs_including_failed_attempts'].values()),
            actual_actions=iv['actual_actions'],replayed_actions=iv['independently_replayed_actions'],
            group_report=str(folder/'grouped-report/validation.json'),report_sha256=digest(folder/'grouped-report/validation.json'))
        for key,row in table.items():
            path=folder/row['evidence']['receipt'];motion=path.parent.parent/'execute/motion/result.json'
            if not motion.exists():raise ValueError('Selected previously static-valid task lacks motion execution')
            result=json.loads(motion.read_text())
            if digest(motion)!=row['evidence']['result_sha256']:raise ValueError('Motion evidence changed')
            env=content_digest(result['environment'])
            if key in environments and environments[key]!=env:raise ValueError('Native environment differs between arms')
            environments[key]=env
            rows.append(dict(method=arm['id'],task_key=key,status=row['status'],failure=row['failure'],
                             search_attempts=result['search_attempts'],cost=result['cost'],result_sha256=digest(motion)))
    kind=m.get('comparison_kind','fixed_priority')
    if streams[0]!=streams[1] or not comparable_methods(methods,kind):
        raise ValueError('Priority comparison changed task or another method parameter')
    controls={x['task_key'] for x in m['selected'] if x['stratum']=='success_control'}
    ids=[x['id'] for x in m['arms']]
    result=compare_outcomes(tables[ids[0]],tables[ids[1]],controls)
    result.update(status='COMPLETE_FIXED16_PRIORITY_COMPARISON_NOT_GLOBAL_RESULT',comparison_kind=kind,tasks=16,executions=32,costs=costs,
                  manifest_sha256=digest(run/'manifest.json'),global_denominator=33954,
                  limits='Known train development, not blind generalization, optimality proof, model score or full-cohort promotion.')
    out=run/'paired-report';out.mkdir();write_json(out/'tasks32.json',rows);result['tasks_sha256']=digest(out/'tasks32.json')
    write_json(out/'validation.json',result);return result


def run_study(case_root,manifest_path):
    root=Path(case_root).resolve();mp=owned_output(root,manifest_path);run=mp.parent;m=json.loads(mp.read_text())
    require_sources(m['sources'])
    if (run/'controller-process.json').exists():raise ValueError('Existing study must not be restarted')
    import resource
    resource.setrlimit(resource.RLIMIT_CPU,(3600,3605))
    owner=process_identity();write_json(run/'controller-process.json',owner);completed=[]
    try:
        for arm in m['arms']:
            require_sources(m['sources']);ap=Path(arm['manifest'])
            if digest(ap)!=arm['manifest_sha256']:raise ValueError('Frozen arm identity changed')
            write_json(run/'state.json',dict(status='RUNNING',arm=arm['id'],completed_arms=completed,time=timestamp()),immutable=False)
            from oracle.research.full_run import run as execute
            if not execute(root,ap):raise RuntimeError('Arm stopped; preserve all existing outcomes')
            from oracle.research.full_review import review
            from oracle.research.full_report import report as grouped_report
            review(root,ap.parent,ap.parent/'independent-full-review')
            grouped_report(root,ap.parent,ap.parent/'independent-full-review/validation.json',ap.parent/'grouped-report')
            completed.append(arm['id'])
        result=report(root,run)
        charged=combined_controller_charge(
            [json.loads((Path(a['manifest']).parent/'validation.json').read_text())['charged_cpu_upper_bound_seconds'] for a in m['arms']],
            [json.loads((Path(a['manifest']).parent/'controller-process.json').read_text()) for a in m['arms']],owner)
        if charged>m['maximum_cpu_seconds']:raise RuntimeError('Study charge exceeded frozen reservation')
        write_json(run/'validation.json',dict(status=result['status'],executions=32,charged_cpu_upper_bound_seconds=charged,
                   manifest_sha256=digest(mp),paired_report_sha256=digest(run/'paired-report/validation.json'),global_acceptance=False))
        write_json(run/'state.json',dict(status='COMPLETE_PAIRED_REVIEW',completed_arms=completed,time=timestamp()),immutable=False)
    except BaseException as error:
        write_json(run/'failure.json',dict(error=repr(error),completed_arms=completed,time=timestamp()))
        write_json(run/'state.json',dict(status='STOPPED_FOR_EVIDENCE_REVIEW',error=repr(error),completed_arms=completed,time=timestamp()),immutable=False)
        raise
    finally:
        from oracle.research.full_run import live
        phases=[str(p) for a in m['arms'] for p in Path(a['manifest']).parent.glob('jobs/*/*/*/start.json') if live(json.loads(p.read_text()))]
        write_json(run/'source-freeze.json',dict(status='OPEN' if phases else 'CLOSED',live_phase_receipts=phases,manifest_sha256=digest(mp)),immutable=False)
