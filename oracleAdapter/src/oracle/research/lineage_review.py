"""Reconcile a sealed prefix and its complete continuation without hiding revisions."""
from collections import Counter,defaultdict
import json
from pathlib import Path
import zipfile

from oracle.common.artifacts import digest,content_digest,owned_output,write_json,package_sources,freeze_sources
from oracle.common.offline_audit import identity
from oracle.research.full_worker import load_task,effective_method
from oracle.research.full_report import group_contract,failure_explanation,summarize,phase_cost,cost_statistics,PASS


def verify_partition(expected,parent,child):
    if (len(set(parent))!=len(parent) or len(set(child))!=len(child)
        or set(parent)&set(child) or set(parent)|set(child)!=set(expected)):
        raise ValueError('Revisions do not exactly partition the original task scope')


def verify_task_meaning(old,new,old_source,new_source):
    if old.get('module_source_sha256')!=old_source or new.get('module_source_sha256')!=new_source:
        raise ValueError('Task source revision binding differs')
    a={k:v for k,v in old.items() if k!='module_source_sha256'}
    b={k:v for k,v in new.items() if k!='module_source_sha256'}
    if a!=b:raise ValueError('Task changed beyond the explicit execution source revision')
    return content_digest(a)


def archive_check(run,m):
    for name,key in [('index.json','index_sha256'),('tasks.jsonl','tasks_file_sha256')]:
        if digest(run/name)!=m[key]:raise ValueError('Frozen revision input changed')
    with zipfile.ZipFile(run/'source.zip') as z:
        if set(z.namelist())!=set(m['sources']):raise ValueError('Frozen source set differs')
        import hashlib
        for name,sha in m['sources'].items():
            if hashlib.sha256(z.read(name)).hexdigest()!=sha:raise ValueError('Frozen source bytes changed')


def review(case_root,child_path,child_review_path,output):
    startup=identity();root=Path(case_root).resolve();child=owned_output(root,child_path)
    child_review_path=owned_output(root,child_review_path);output=owned_output(root,output)
    if output.exists():raise FileExistsError(output)
    if not (child/'validation.json').is_file() or not child_review_path.is_file():
        raise ValueError('Continuation has not completed independent full review; partial output cannot be merged')
    cm=json.loads((child/'manifest.json').read_text());lineage=cm['continuation'];csha=digest(child/'manifest.json')
    parent=owned_output(root,lineage['parent_run']);pm=json.loads((parent/'manifest.json').read_text());psha=digest(parent/'manifest.json')
    policy_path=Path(__file__).resolve().parents[1]/'configs/experiments/lineage_review.json'
    policy=json.loads(policy_path.read_text())
    if (psha!=policy['parent_manifest_sha256'] or csha!=policy['continuation_manifest_sha256']
        or pm['task_count']!=policy['original_task_count'] or pm['datasets']!=policy['original_datasets']
        or cm['task_count']!=policy['continuation_records'] or lineage['retained_completed']!=policy['retained_parent_records']):
        raise ValueError('Requested full experiment scope/revisions differ from explicit policy')
    if psha!=lineage['parent_manifest_sha256'] or pm['task_count']!=lineage['parent_task_count']:
        raise ValueError('Original experiment identity changed')
    if cm['protocol']!=pm['protocol'] or cm['base_method']!=pm['base_method']:raise ValueError('Protocol or method changed across revisions')
    archive_check(parent,pm);archive_check(child,cm)
    cr=json.loads(child_review_path.read_text());closure=json.loads((child/'validation.json').read_text())
    if (cr['status']!='FULL_ACCOUNTING_AND_EVIDENCE_VALID_NOT_ALL_NAVIGATION_PASSED'
        or cr['manifest_sha256']!=csha or cr['records']!=cm['task_count']
        or closure['manifest_sha256']!=csha or closure['results_index_sha256']!=digest(child/'results-index.json')):
        raise ValueError('Complete independent continuation review required')
    pr_path=owned_output(root,lineage['parent_prefix_review']);pr=json.loads(pr_path.read_text())
    if (digest(pr_path)!=lineage['parent_prefix_review_sha256'] or pr['status']!='SEALED_PREFIX_RECEIPTS_VERIFIED_PARENT_RUN_INCOMPLETE'
        or pr['parent_manifest_sha256']!=psha or pr['records']!=lineage['retained_completed']):
        raise ValueError('Sealed parent review changed')
    pe_path=pr_path.parent/'task-evidence.json';ce_path=child_review_path.parent/'task-evidence.json'
    if digest(pe_path)!=pr['output_hashes']['task-evidence.json'] or digest(ce_path)!=cr['task_evidence_sha256']:
        raise ValueError('Independent per-task evidence index changed')
    pe={r['task_key']:r for r in json.loads(pe_path.read_text())};ce={r['task_key']:r for r in json.loads(ce_path.read_text())}
    parent_rows=json.loads((pr_path.parent.parent/'parent-snapshot/selected-results.json').read_text())
    child_rows=json.loads((child/'results-index.json').read_text())
    parent_index={e['record']['task_key']:e for e in json.loads((parent/'index.json').read_text())}
    child_index={e['record']['task_key']:e for e in json.loads((child/'index.json').read_text())}
    verify_partition(parent_index,[r['task_key'] for r in parent_rows],[r['task_key'] for r in child_rows])
    if set(pe)!={r['task_key'] for r in parent_rows} or set(ce)!=set(child_index):raise ValueError('Review coverage differs')
    budget=lineage['parent_charged_cpu_upper_bound_seconds']+closure['charged_cpu_upper_bound_seconds']
    if budget>lineage['original_total_cpu_budget_hours']*3600:raise ValueError('Cumulative experiment CPU bound exceeded')
    rows=[];logical=defaultdict(Counter);datasets=Counter();actual=replayed=0;phases=[]
    for run,m,msha,records,verified,index in ((parent,pm,psha,parent_rows,pe,parent_index),(child,cm,csha,child_rows,ce,child_index)):
        for record in records:
            key=record['task_key'];task,_=load_task(root,m,index[key],run/'tasks.jsonl')
            original,_=load_task(root,pm,parent_index[key],parent/'tasks.jsonl')
            meaning=verify_task_meaning(original,task,content_digest(pm['sources']),content_digest(m['sources']))
            rp=Path(record['receipt']).resolve()
            if not rp.is_relative_to(run) or digest(rp)!=record['receipt_sha256'] or digest(rp)!=verified[key]['receipt_sha256']:
                raise ValueError('Revision receipt differs from independently reviewed bytes')
            receipt=json.loads(rp.read_text());method=effective_method(task,m)
            if (receipt['task_sha256']!=content_digest(task) or verified[key]['task_sha256']!=content_digest(task)
                or receipt['manifest_sha256']!=msha or receipt['method']!=method):raise ValueError('Actual execution revision differs')
            for field in ('task_key','dataset','cohort','status','failure','actual_actions','replayed_actions'):
                if receipt[field]!=record[field]:raise ValueError('Cached result row differs')
            pre_path=rp.with_name('preflight.json')
            if digest(pre_path)!=receipt['preflight_sha256']:raise ValueError('Preflight changed')
            pre=json.loads(pre_path.read_text());result=audit=None
            contract=group_contract(task,receipt);contract['execution_revision']=run.name
            row=dict(task_key=key,execution_revision=run.name,producer_manifest_sha256=msha,contract=contract,
                original_task_sha256=content_digest(original),executed_task_sha256=content_digest(task),unchanged_meaning_sha256=meaning,
                status=receipt['status'],failure=receipt['failure'],motion_attempted=receipt['motion_attempted'],teacher_cost={},
                replay_wall_seconds=None,search_calls=None,search_failures=[],switch_reasons=[],actions_by_origin={},
                official_primitives_consumed=receipt['official_primitives_consumed'],
                receipt=str(rp),receipt_sha256=digest(rp))
            if receipt['result_sha256'] is not None:
                result_path=rp.parent.parent/'execute/motion/result.json';audit_path=rp.with_name('motion-audit.json')
                if digest(result_path)!=receipt['result_sha256'] or digest(audit_path)!=receipt['motion_audit_sha256']:
                    raise ValueError('Motion evidence changed after component review')
                result=json.loads(result_path.read_text());audit=json.loads(audit_path.read_text())
                if (len(result['actions'])!=receipt['actual_actions'] or audit['executed_actions_replayed']!=receipt['replayed_actions']
                    or receipt['actual_actions']!=receipt['replayed_actions'] or audit['issues']):raise ValueError('Per-task action/replay accounting differs')
                row.update(teacher_cost=result['cost'],replay_wall_seconds=audit['wall_seconds'],search_calls=len(result['search_attempts']),
                    search_failures=[a['failure'] for a in result['search_attempts']],actions_by_origin=dict(Counter(result['action_origins'])),
                    switch_reasons=[e.get('reason') for e in result['events'] if e.get('kind')=='official_prefix_stopped' and e.get('next_stage')=='native_greedy_and_bounded_search'])
            elif receipt['actual_actions'] or receipt['replayed_actions'] or receipt['motion_attempted']:
                raise ValueError('Unexecuted task claims motion')
            row['failure_explanation']=failure_explanation(task,receipt,pre,result,audit)
            rows.append(row);datasets[task['dataset']]+=1;logical[task['cohort']][receipt['status']]+=1
            actual+=receipt['actual_actions'];replayed+=receipt['replayed_actions']
        for directory in sorted((run/'jobs').glob('*/attempt-*/*')):
            if directory.is_dir() and (directory.name=='execute' or directory.name.startswith('audit-')):
                phases.append(dict(execution_revision=run.name,directory=str(directory),**phase_cost(directory,msha)))
    if dict(datasets)!=pm['datasets'] or len(rows)!=pm['task_count']:raise ValueError('Original full denominators not restored')
    phase_groups={}
    for revision,role in sorted({(p['execution_revision'],p['role']) for p in phases}):
        items=[p for p in phases if p['execution_revision']==revision and p['role']==role]
        phase_groups[revision+'::'+role]=dict(phases=len(items),statuses=dict(Counter(p['status'] for p in items)),
            costs={k:cost_statistics(k,[p[k] for p in items]) for k in ('process_cpu_seconds','phase_wall_including_permit_wait_seconds','peak_rss_kib','charged_cpu_upper_bound_seconds')})
    output.mkdir();_,sources=package_sources();freeze_sources(output,sources)
    write_json(output/'all-task-lineage.json',rows);write_json(output/'all-phase-costs.json',phases)
    write_json(output/'failures.json',[r for r in rows if r['status']!=PASS])
    summary=dict(status='ORIGINAL_FULL_SCOPE_RECONCILED_ACROSS_EXPLICIT_COMPATIBILITY_REVISIONS',startup=startup,
        datasets=dict(datasets),records=len(rows),revisions={parent.name:len(parent_rows),child.name:len(child_rows)},
        producer_manifest_sha256={parent.name:psha,child.name:csha},logical_information_groups={k:dict(v) for k,v in logical.items()},
        revision_specific_effects_and_costs=summarize(rows),phase_costs_including_infrastructure_failures=phase_groups,
        actual_actions=actual,independently_replayed_actions=replayed,all_navigation_gates_passed=all(r['status']==PASS for r in rows),
        cumulative_charged_cpu_upper_bound_seconds=budget,original_total_cpu_budget_hours=lineage['original_total_cpu_budget_hours'],
        component_reviews={str(pr_path):digest(pr_path),str(child_review_path):digest(child_review_path)},
        outputs_sha256={p.name:digest(p) for p in output.glob('*.json')},configuration_sha256=digest(policy_path),
        limits=['Explicit two-revision execution, not one source SHA and not a new method union.',
                'Each task has exactly one final execution result; original ordinary failures are not rerun or replaced.',
                'Per-revision costs are not a randomized performance comparison; unknown cost remains unknown.',
                'Recorded original reference order is checked, not full natural-language action semantics or paper-A reset evaluation.',
                'This reconciles recorded independent native audits; no new motion, physical-independence theorem, model SR or publication approval.'])
    write_json(output/'validation.json',summary);return summary
