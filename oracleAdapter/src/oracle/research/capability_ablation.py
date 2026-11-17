"""Reconcile real method outcomes without registering a post-hoc union oracle."""
import json
from pathlib import Path
from oracle.common.artifacts import content_digest,digest,write_json
from oracle.research.search_ablation import physical_identity


def compare_sets(source,search,combination):
    return {'combination_success_beyond_source':sorted(combination-source),
            'source_success_lost_by_combination':sorted(source-combination),
            'combination_success_beyond_search':sorted(combination-search),
            'search_success_not_recovered_by_combination':sorted(search-combination),
            'combination_only_beyond_both_single_methods':sorted(combination-(source|search)),
            'union_is_diagnostic_not_an_executed_method':True}


def audit(case_root,config,output):
    root=Path(case_root).resolve();output=Path(output).resolve()
    if not output.is_relative_to(root/'outputs/oracleAdapter') or output.exists():raise ValueError('Fresh owned output required')
    groups={};physical={};protocol=None;checks=[]
    for label in ('portfolio','search'):
        run=root/config[label+'_run'];report=root/config[label+'_report']
        receipt=json.loads((report/'validation.json').read_text());summary=json.loads((report/'summary.json').read_text())
        if digest(report/'summary.json')!=receipt['summary_sha256']:raise ValueError('Summary receipt changed')
        validation=json.loads((run/'validation.json').read_text());manifest=json.loads((run/'manifest.json').read_text())
        if (not validation['complete'] or digest(run/'validation.json')!=summary['source_validation_sha256']
            or digest(run/'manifest.json')!=summary['manifest_sha256']):raise ValueError('Unverified source study')
        if protocol is None:protocol=manifest['protocol']
        elif protocol!=manifest['protocol']:raise ValueError('Different physical acceptance cannot be attributed to information')
        tasks={x['task_key']:x for x in manifest['tasks']}
        if len(tasks)!=config['expected_physical_tasks']:raise ValueError('Physical task scope changed')
        for key,item in tasks.items():
            if digest(item['path'])!=item['sha256']:raise ValueError('Frozen task changed')
            task=json.loads(Path(item['path']).read_text());pid=physical_identity(task)
            if key in physical and physical[key]!=pid:raise ValueError('Initial state/targets/profile mismatch')
            physical[key]=pid
            if label=='search' and ('official_demonstration' in task or 'official_actions' in task['privileges']):
                raise ValueError('Official information leaked into pure search input')
        for row in validation['results']:
            if digest(row['result_path'])!=row['result_sha256'] or digest(row['audit_path'])!=row['audit_sha256']:raise ValueError('Result/audit changed')
            record=json.loads(Path(row['result_path']).read_text());independent=json.loads(Path(row['audit_path']).read_text())
            key=row['task_key'];task=json.loads(Path(tasks[key]['path']).read_text())
            if record['task_sha256']!=content_digest(task) or independent['source_result_sha256']!=row['result_sha256']:raise ValueError('Task/result audit binding mismatch')
            if row['status']!=independent['status'] or (independent['full_route_accepted'] and (independent['issues'] or independent['physical_alerts'])):raise ValueError('False acceptance')
            method=row['method'];group=groups.setdefault(method,{})
            if key in group:raise ValueError('Duplicate method/task')
            group[key]={'status':row['status'],'failure':record['failure'],'cpu_seconds':record['cost']['cpu_seconds'],
                        'actual_actions':len(record['actions']),'result_sha256':row['result_sha256'],'audit_sha256':row['audit_sha256']}
        checks.append({'run':str(run),'validation_sha256':digest(run/'validation.json'),'manifest_sha256':digest(run/'manifest.json')})
    if any(set(rows)!=set(physical) for rows in groups.values()):raise ValueError('Unmatched method task sets')
    accepted={m:{key for key,r in rows.items() if r['status']=='PASS_ORDERED_NATIVE_AND_RATIONAL_REPLAY'} for m,rows in groups.items()}
    source=accepted['guarded_official_only'];search=accepted['lossless_search_without_official_actions'];combo=accepted['guarded_official_then_search']
    comparison=compare_sets(source,search,combo)
    records=[{'task_key':key,'physical_identity':physical[key],'methods':{method:rows[key] for method,rows in groups.items()}} for key in sorted(physical)]
    output.mkdir(parents=True,exist_ok=False);write_json(output/'matched133-method-ledger.json',records)
    summary={'status':'MATCHED_PHYSICAL_TASK_ABLATION_INFORMATION_DIFFERENCE_EXPLICIT','physical_tasks':len(physical),
        'methods':{m:{'accepted':len(accepted[m]),'executed':len(rows),'cpu_seconds':sum(r['cpu_seconds'] for r in rows.values()),
                      'actual_actions':sum(r['actual_actions'] for r in rows.values()),
                      'official_actions_used':m!='lossless_search_without_official_actions'} for m,rows in groups.items()},
        'set_relations':comparison,'source_checks':checks,'ledger_sha256':digest(output/'matched133-method-ledger.json'),
        'initial_state_scope':'Historical official Guide/CE demonstration initial states; not a Landmark raw-heading full-cohort evaluation',
        'limits':['Source-only versus combination has matched information; pure-search comparison changes actual official-action information.',
                  'A union of successful records is not an executed or registered method; do not claim its score.',
                  'Development data previously inspected; no full3062/33954 or model-score/generalization claim.']}
    write_json(output/'validation.json',summary);return summary
