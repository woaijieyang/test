"""Evidence-bound full validation costs; no navigation or outcome selection."""
from collections import Counter,defaultdict
import hashlib
import json
import math
from pathlib import Path,PurePosixPath
import zipfile

from oracle.common.artifacts import content_digest,digest,owned_output,write_json,package_sources,freeze_sources
from oracle.common.offline_audit import identity
from oracle.common.task_index import verify_entry
from oracle.research.report import statistics

PASS='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES'
TEACHER_COSTS=('total_wall_seconds','cpu_seconds','actual_native_calls','native_preview_calls',
               'source_queries','triangle_checks','search_expansions','peak_rss_kib')


def measurements(values):
    present=[x for x in values if x is not None]
    result=statistics(present) if present else dict(count=0,sum=None,p50=None,p95=None,max=None)
    return {**result,'missing':len(values)-len(present)}


def cost_statistics(field,values):
    result=measurements(values)
    if field=='peak_rss_kib':result.pop('sum')
    return result


def group_contract(task,receipt):
    return {**{k:task.get(k) for k in ('dataset','split','language','purpose','objective','target_scope','profile_sha256')},
            'privileges':sorted(task['privileges']),'method':receipt['method']['id'],
            'official_policy':receipt['method']['official_policy']}


def failure_explanation(task,receipt,pre,result=None,audit=None):
    """Classify recorded failure evidence without making reachability claims."""
    kind=receipt['failure']
    stage=('none' if receipt['status']==PASS else
           'input_or_asset_mapping' if kind=='identity_or_adaptation_missing' else
           'static_native_reference' if receipt['status']=='STATIC_FAILURE_PRESERVED' else
           'reference_endpoint_source_gate' if receipt['status']=='ROUTE_WITNESS_ONLY_ENDPOINT_SOURCE_GATE_FAIL' else
           'bounded_search' if kind in ('search_budget_exhausted','search_frontier_exhausted') else
           'actual_native_motion' if kind=='native_action_illegal' else
           'source_geometry' if kind=='source_geometry_contact' else 'unknown')
    point_contacts=[p['index'] for p in pre['points'] if p['source_contact'] is not None]
    endpoints=set(pre.get('endpoint_indices',[]))
    next_index=len(result['boundaries'])+1 if result is not None else None
    if next_index is not None and next_index>=len(task['targets']):next_index=None
    return dict(stage=stage,recorded_failure=kind,detail=result.get('detail') if result else None,
        missing_target_indices=pre['missing_target_indices'],geometry_catalog_present=pre['geometry_catalog_present'],
        offmesh_reference_indices=[p['index'] for p in pre['points'] if not p['navigable']],
        disconnected_reference_edge_indices=[e['index'] for e in pre['links'] if not e['finite']],
        source_contact_reference_indices=point_contacts,
        source_contact_endpoint_indices=[i for i in point_contacts if i in endpoints],
        endpoint_source_gate=pre['endpoint_source_gate'],
        next_required_reference_index=next_index,
        last_executed_position=result['positions'][-1] if result else None,
        last_search_attempt=result['search_attempts'][-1] if result and result['search_attempts'] else None,
        rejected_planner_transitions=result.get('rejected_planner_transitions') if result else None,
        independent_replay_physical_alerts=audit.get('physical_alerts') if audit else None,
        full_route_accepted=audit.get('full_route_accepted') if audit else False,
        physical_unreachability_proven=False,
        interpretation=('No route proof under the declared finite planner; global physical reachability remains unknown'
                        if stage=='bounded_search' else
                        'Static failure describes current mapping/profile queries, not a physical impossibility theorem'
                        if stage in ('input_or_asset_mapping','static_native_reference') else
                        'A route witness does not clear the separate source endpoint gate'
                        if stage=='reference_endpoint_source_gate' else
                        'Recorded evidence under the named protocol; no global impossibility claim'))


def summarize(rows):
    groups=defaultdict(list);seen=set()
    for row in rows:
        if row['task_key'] in seen:raise ValueError('Duplicate task in cost report')
        seen.add(row['task_key']);groups[content_digest(row['contract'])].append(row)
    result=[]
    for key,items in sorted(groups.items()):
        motion=[r for r in items if r['motion_attempted']]
        result.append(dict(group_id=key,contract=items[0]['contract'],tasks=len(items),
            statuses=dict(Counter(r['status'] for r in items)),
            failures=dict(Counter(r['failure'] for r in items if r['failure'])),
            accepted=sum(r['status']==PASS for r in items),
            accepted_fraction=sum(r['status']==PASS for r in items)/len(items),
            motion_attempted=len(motion),static_or_input_failures=len(items)-len(motion),
            teacher_cost={field:cost_statistics(field,[r['teacher_cost'].get(field) for r in motion]) for field in TEACHER_COSTS},
            final_motion_replay_wall_seconds=measurements([r['replay_wall_seconds'] for r in motion]),
            search_calls=measurements([r['search_calls'] for r in motion]),
            official_primitives_consumed=measurements([r['official_primitives_consumed'] for r in items]),
            search_call_failures=dict(Counter(x for r in motion for x in r['search_failures'])),
            method_switch_reasons=dict(Counter(x for r in motion for x in r['switch_reasons'])),
            actions_by_origin=dict(sum((Counter(r['actions_by_origin']) for r in motion),Counter()))))
    return result


def resolve_evidence(path,run,source_run):
    """Explicit relocation for a byte-preserving read-only export, never guess."""
    original=PurePosixPath(str(path))
    relative=original.relative_to(PurePosixPath(str(source_run)))
    if '..' in relative.parts:raise ValueError('Evidence traverses source root')
    target=(Path(run)/Path(*relative.parts)).resolve()
    if not target.is_relative_to(Path(run).resolve()):raise ValueError('Evidence escapes copied run')
    return target


def phase_cost(directory,expected_manifest):
    start_path=directory/'start.json';exit_path=directory/'exit.json';settled_path=directory/'settled-cost.json'
    start=json.loads(start_path.read_text()) if start_path.exists() else None
    end=json.loads(exit_path.read_text()) if exit_path.exists() else None
    settled=json.loads(settled_path.read_text()) if settled_path.exists() else None
    if start and start['manifest_sha256']!=expected_manifest:raise ValueError('Phase belongs to another manifest')
    if start and end and any(start[k]!=end[k] for k in ('pid','start_ticks')):raise ValueError('Phase process identity mismatch')
    if settled and settled.get('exit_sha256') is not None and (not end or digest(exit_path)!=settled['exit_sha256']):
        raise ValueError('Settled CPU receipt differs from exit')
    wall=end['ended_monotonic']-start['started_monotonic'] if start and end else None
    cpu=end['process_cpu_seconds'] if end else None
    peak=end.get('peak_rss_kib') if end else None
    charged=settled['charged_cpu_upper_bound_seconds'] if settled else None
    if any(v is not None and (not math.isfinite(v) or v<0) for v in (wall,cpu,peak,charged)):
        raise ValueError('Invalid phase cost')
    return dict(role=start['role'] if start else directory.name,process_cpu_seconds=cpu,
        phase_wall_including_permit_wait_seconds=wall,peak_rss_kib=peak,
        charged_cpu_upper_bound_seconds=charged,status=end['status'] if end else 'MISSING_EXIT_COST_UNKNOWN',
        evidence={p.name:digest(p) for p in (start_path,exit_path,settled_path) if p.exists()})


def report(case_root,run_path,review_path,output,source_case_root=None):
    startup=identity();root=Path(case_root).resolve();run=owned_output(root,run_path)
    output=owned_output(root,output);review_path=owned_output(root,review_path)
    if output.exists():raise FileExistsError(output)
    m=json.loads((run/'manifest.json').read_text());msha=digest(run/'manifest.json')
    closure=json.loads((run/'validation.json').read_text());review=json.loads(review_path.read_text())
    if (closure['manifest_sha256']!=msha or review['manifest_sha256']!=msha
        or review['status']!='FULL_ACCOUNTING_AND_EVIDENCE_VALID_NOT_ALL_NAVIGATION_PASSED'
        or review['records']!=m['task_count']):raise ValueError('Complete independent review required')
    evidence_path=review_path.parent/'task-evidence.json'
    if digest(evidence_path)!=review['task_evidence_sha256']:raise ValueError('Independent review evidence changed')
    reviewed={r['task_key']:r for r in json.loads(evidence_path.read_text())}
    if digest(run/'results-index.json')!=closure['results_index_sha256']:raise ValueError('Result index changed')
    if digest(run/'index.json')!=m['index_sha256'] or digest(run/'tasks.jsonl')!=m['tasks_file_sha256']:
        raise ValueError('Input inventory changed')
    with zipfile.ZipFile(run/'source.zip') as source:
        if set(source.namelist())!=set(m['sources']):raise ValueError('Frozen source set changed')
        for name,sha in m['sources'].items():
            if hashlib.sha256(source.read(name)).hexdigest()!=sha:raise ValueError('Frozen source bytes changed')
    indices=json.loads((run/'index.json').read_text());entries={e['record']['task_key']:e for e in indices}
    final=json.loads((run/'results-index.json').read_text())
    if (len(final)!=m['task_count'] or len({r['task_key'] for r in final})!=len(final)
        or {r['task_key'] for r in final}!=set(entries) or set(entries)!=set(reviewed)):
        raise ValueError('Full task coverage differs')
    source_run=(PurePosixPath(source_case_root)/'outputs/oracleAdapter'/run.name if source_case_root else PurePosixPath(run.as_posix()))
    rows=[]
    with (run/'tasks.jsonl').open('rb') as stream:
        for indexed in final:
            entry=verify_entry(entries[indexed['task_key']],m['task_merkle_root'],m['task_count'])
            stream.seek(entry['offset']);raw=stream.read(entry['bytes'])
            if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Task bytes changed')
            task=json.loads(raw)
            rp=resolve_evidence(indexed['receipt'],run,source_run)
            if digest(rp)!=indexed['receipt_sha256'] or digest(rp)!=reviewed[task['task_key']]['receipt_sha256']:
                raise ValueError('Final receipt differs from independent review')
            receipt=json.loads(rp.read_text())
            if receipt['task_sha256']!=content_digest(task) or receipt['task_sha256']!=reviewed[task['task_key']]['task_sha256']:
                raise ValueError('Task contract binding differs')
            pre_path=rp.with_name('preflight.json')
            if digest(pre_path)!=receipt['preflight_sha256']:raise ValueError('Preflight evidence changed')
            pre=json.loads(pre_path.read_text());result=audit=None
            legacy_fields=[k for k in ('motion_attempted','official_primitives_consumed') if k not in receipt]
            if legacy_fields and 'worker' in m['config']:raise ValueError('Required current phase fields absent')
            attempted=receipt.get('motion_attempted',receipt['result_sha256'] is not None)
            row=dict(legacy_receipt_fields_absent=legacy_fields,task_key=task['task_key'],contract=group_contract(task,receipt),status=receipt['status'],
                failure=receipt['failure'],motion_attempted=attempted,teacher_cost={},
                replay_wall_seconds=None,search_calls=None,search_failures=[],switch_reasons=[],actions_by_origin={},
                official_primitives_consumed=receipt.get('official_primitives_consumed'))
            row['evidence']={'receipt':rp.relative_to(run).as_posix(),'receipt_sha256':digest(rp),
                             'preflight_sha256':digest(pre_path),'result_sha256':receipt['result_sha256'],
                             'motion_audit_sha256':receipt['motion_audit_sha256']}
            if attempted:
                result_path=rp.parent.parent/'execute/motion/result.json';audit_path=rp.with_name('motion-audit.json')
                if digest(result_path)!=receipt['result_sha256'] or digest(audit_path)!=receipt['motion_audit_sha256']:
                    raise ValueError('Motion cost evidence changed')
                result=json.loads(result_path.read_text());audit=json.loads(audit_path.read_text())
                row.update(official_primitives_consumed=result.get('official_primitives_consumed'),teacher_cost=result['cost'],replay_wall_seconds=audit['wall_seconds'],
                    search_calls=len(result['search_attempts']),search_failures=[a['failure'] for a in result['search_attempts']],
                    switch_reasons=[e.get('reason',e.get('kind','unknown')) for e in result['events'] if e.get('kind')=='official_prefix_stopped' and e.get('next_stage')=='native_greedy_and_bounded_search'],
                    actions_by_origin=dict(Counter(result['action_origins'])))
            row['failure_explanation']=failure_explanation(task,receipt,pre,result,audit)
            rows.append(row)
    phases=[]
    for directory in sorted((run/'jobs').glob('*/attempt-*/*')):
        if not directory.is_dir():continue
        if directory.name!='execute' and not directory.name.startswith('audit-'):continue
        phases.append(dict(directory=directory.relative_to(run).as_posix(),**phase_cost(directory,msha)))
    phase_groups={}
    for role in sorted({p['role'] for p in phases}):
        items=[p for p in phases if p['role']==role]
        phase_groups[role]=dict(phases=len(items),statuses=dict(Counter(p['status'] for p in items)),
            costs={k:cost_statistics(k,[p[k] for p in items]) for k in ('process_cpu_seconds','phase_wall_including_permit_wait_seconds','peak_rss_kib','charged_cpu_upper_bound_seconds')})
    controllers=[json.loads(p.read_text()) for p in sorted((run/'controllers').glob('[0-9][0-9][0-9][0-9].json'))]
    groups=summarize(rows)
    summary=dict(status='FULL_GROUPED_RESULTS_AND_COST_ACCOUNTING',startup=startup,records=len(rows),groups=groups,
        phase_costs_including_failed_attempts=phase_groups,controller_sessions=len(controllers),
        controller_reserved_cpu_seconds=sum(c['reserved_cpu_seconds'] for c in controllers),
        controller_measured_cpu_seconds=None,closure_charged_cpu_upper_bound_seconds=closure['charged_cpu_upper_bound_seconds'],
        all_navigation_gates_passed=review['all_navigation_gates_passed'],manifest_sha256=msha,
        independent_review_sha256=digest(review_path),source_run_root=str(source_run),
        limits=['No pooled success rate across different objectives, information conditions or profiles.',
                'Teacher costs include navigation failures; static failures have no teacher cost, not zero-cost navigation.',
                'Phase costs include all execution/audit attempts and permit wait; missing exit cost remains unknown.',
                'Controller measured CPU was not recorded; its reservation is not actual CPU.',
                'Peak RSS statistics are per-process peaks; their sum is not concurrent memory.',
                'Greedy internal native probes were not instrumented; preview calls are not complete simulator work.',
                'Quantiles use linear interpolation at (n-1)*q. No new motion or model evaluation.'])
    output.mkdir(parents=True);_,sources=package_sources();freeze_sources(output,sources)
    write_json(output/'task-costs.json',rows);write_json(output/'phase-costs.json',phases)
    failures=[{k:r[k] for k in ('task_key','contract','status','failure','failure_explanation','evidence')}
              for r in rows if r['status']!=PASS]
    write_json(output/'failures.json',failures)
    summary['failure_stage_counts']=dict(Counter(r['failure_explanation']['stage'] for r in failures))
    summary['outputs_sha256']={p.name:digest(p) for p in output.glob('*.json')}
    write_json(output/'validation.json',summary)
    lines=['# 完整验证结果与成本报告','',
           f'任务覆盖：{len(rows)}；全部导航门槛通过：{review["all_navigation_gates_passed"]}。',
           '各行代表不同任务/实际信息条件，不合并成统一Oracle成功率。静态失败保留在任务分母，未执行的teacher成本不补零。','',
           '| 数据集 / split / 语言 | 方法 | 任务数 | 全门槛通过 | 静态或输入失败 | Teacher耗时P50/P95(s) |',
           '|---|---|---:|---:|---:|---|']
    for group in groups:
        c=group['contract'];cost=group['teacher_cost']['total_wall_seconds']
        timing='未执行' if cost['count']==0 else f'{cost["p50"]:.3f} / {cost["p95"]:.3f}'
        lines.append(f'| {c["dataset"]} / {c["split"]} / {c["language"]} | {c["method"]} | {group["tasks"]} | {group["accepted"]} | {group["static_or_input_failures"]} | {timing} |')
    lines+=['','完整分组契约、逐任务成本见validation.json与task-costs.json；逐任务失败解释及证据链接见failures.json；执行及审计的所有尝试见phase-costs.json。',
            '控制器CPU实际值未记录；其预算预留不当作实际CPU。内存仅报告各进程峰值分布，不相加当并发总峰值。',
            '原生贪心内部探测未完整计数；已记录preview调用数不能冒充全部模拟器调用。',
            '有限搜索失败不证明物理不可达；本报告不提供模型成绩、论文创新认定或发布授权。']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return summary
