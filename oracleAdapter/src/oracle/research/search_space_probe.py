"""Bounded terminal-search observations, never a navigation result or key change."""
from collections import Counter
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import signal
import time

from oracle.common.artifacts import (content_digest, digest, freeze_sources,
    owned_output, package_sources, require_sources, runtime_identity, timestamp, write_json)


def summarize(snapshot, goal_h):
    nodes=snapshot['nodes']; expanded=[nodes[i][0] for i in snapshot['expanded_indices']]
    def bucket(s,scale,angle):
        yaw=math.degrees(2*math.atan2(s.quaternion_xyzw[1],s.quaternion_xyzw[3]))%360
        return tuple(round(v*scale) for v in s.position)+(round(yaw/angle)%round(360/angle),)
    groups=Counter(bucket(s,1000,.001) for s in expanded)
    return dict(generated=len(nodes),expanded=len(expanded),
        expanded_exact_poses=len({s.key_values() for s in expanded}),
        expanded_exact_positions=len({s.position for s in expanded}),
        expanded_report_only_mm_yaw001_buckets=len(groups),
        expanded_report_only_cm_yaw01_buckets=len({bucket(s,100,.1) for s in expanded}),
        largest_report_only_mm_bucket=max(groups.values(),default=0),
        generated_inside_original_goal_region=sum(h<=goal_h for h in snapshot['heuristics']),
        minimum_generated_h=min(snapshot['heuristics']), initial_h=snapshot['heuristics'][0],
        maximum_depth=max(n[3] for n in nodes),
        generated_last_actions=dict(Counter(n[2] for n in nodes[1:])),
        approximate_equivalence_proven=False,
        interpretation='Rounded buckets describe concentration only; no states are merged or removed.')


def one_case(job):
    import resource
    from oracle.adapters.habitat.native import NativeAdapter,NativeState
    from oracle.adapters.habitat.assets import resolve
    from oracle.contracts import Budget,MotionContract
    from oracle.common.identity import Context,exact_state_key
    from oracle.planners.action_space import search
    from oracle.planners.collision_queries import CachedSourceQueries
    from oracle.verification.source_scene import SourceScene
    from oracle.verification.motion import native_violation
    from oracle.research.full_worker import process_identity
    require_sources(job['sources'])
    os.sched_setaffinity(0,{job['cpu']});os.nice(15)
    resource.setrlimit(resource.RLIMIT_CPU,(99,100))
    def expired(*_):raise TimeoutError('Frozen diagnostic110second wall cap')
    signal.signal(signal.SIGALRM,expired);signal.alarm(110)
    out=Path(job['output']);out.mkdir();write_json(out/'process.json',process_identity())
    started=time.process_time();adapter=None
    try:
        task=job['task'];old=job['old'];method=old['method'];protocol=old['protocol']
        ref=old['search_attempts'][-1]['reference_index'];target=task['targets'][ref]
        motion=MotionContract(**{k:protocol[k] for k in MotionContract.__dataclass_fields__})
        asset,geometry=resolve(job['root'],task)
        source=SourceScene(geometry['receipt_path'],geometry['receipt_sha256'],protocol,catalog=geometry)
        adapter=NativeAdapter(asset['navmesh_path'],asset['navmesh_sha256'],motion)
        env=runtime_identity()
        previous=old['environment']
        if any(env[k]!=previous[k] for k in ('python','python_version','habitat_sim','numpy')):
            raise ValueError('Original native environment differs')
        for filename,expected in previous['native_and_wrapper_files'].items():
            if digest(filename)!=expected:raise ValueError('Previously loaded native/wrapper file changed')
        initial=NativeState(tuple(old['positions'][-1]),tuple(old['rotations'][-1]))
        adapter.restore(initial);roundtrip=adapter.snapshot()
        if roundtrip!=initial:raise ValueError('Last saved state is not exactly restore-idempotent')
        context=Context(geometry['scene_sha256'],task['profile_sha256'],content_digest(asdict(motion)),
            content_digest(task),content_digest(protocol),content_digest(job['sources']),content_digest(env),'native_xyz_quaternion_xyzw')
        cache=CachedSourceQueries(source,context_digest=context.digest(),**method['planning_query_cache'])
        rejected=Counter()
        def distance(state):return adapter.geodesic_distance(state.position,target)
        def transition(state,action):
            adapter.restore(state);following=adapter.step(action)
            reason=native_violation(adapter,state,following,action,protocol)
            if not reason and not math.isfinite(distance(following)):reason='target_disconnected'
            if not reason and cache.contact(state.position,following.position):reason='source_contact'
            if reason:rejected[reason]+=1;return None
            return following
        last_boundary=max((b['action_index'] for b in old['boundaries'] if b['reference_index']<ref),default=0)
        remaining=min(method['max_actions_per_reference']-(len(old['actions'])-last_boundary),method['max_task_actions']-len(old['actions']))
        snapshots=[]
        result=search(initial,actions=(1,2,3),transition=transition,
            key=lambda s:exact_state_key(s.key_values(),ref,context),
            reached=lambda s:distance(s)<=motion.goal_radius_m,
            heuristic=lambda s:distance(s)/motion.forward_m,
            action_costs={int(k):v for k,v in method['action_costs'].items()},
            budget=Budget(method['max_expansions_per_search'],method['max_transition_calls_per_search'],remaining,method['max_search_wall_seconds']),
            priority_weight=method.get('search_priority_weight',1.),audit_sink=snapshots.append)
        snap=snapshots[0];report=summarize(snap,motion.goal_radius_m/motion.forward_m)
        serialized={**snap,'nodes':[(asdict(s),p,a,d) for s,p,a,d in snap['nodes']]}
        write_json(out/'terminal-search.json',serialized)
        expected=old['search_attempts'][-1]
        report.update(task_key=task['task_key'],failure=result.failure.value,stop_reason=result.stop_reason,
            expansions=result.expansions,native_preview_calls=adapter.native_calls,
            source_result_sha256=job['old_sha256'],reference_index=ref,
            original_outcome_reproduced=(result.failure.value==expected['failure'] and result.expansions==expected['expansions'] and result.transition_calls==expected['transition_calls']),
            original_attempt=expected,diagnostics=result.diagnostics,rejected_transitions=dict(rejected),
            terminal_snapshot_sha256=digest(out/'terminal-search.json'),
            actual_entry=__file__,actual_entry_sha256=digest(__file__),search_source_sha256=digest(Path(__file__).parents[1]/'planners/action_space.py'),
            cpu_seconds=time.process_time()-started,whole_navigation_tasks_executed=0,navigation_recoveries=0)
        write_json(out/'validation.json',report)
        return report
    except BaseException as error:
        write_json(out/'failure.json',dict(type=type(error).__name__,detail=str(error),cpu_seconds=time.process_time()-started))
        raise
    finally:
        if adapter:adapter.close()
        signal.alarm(0)


def run(case_root,output):
    import multiprocessing
    import psutil
    import resource
    from concurrent.futures import ProcessPoolExecutor
    from oracle.research.full_worker import process_identity
    if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
    root=Path(case_root).resolve();out=owned_output(root,output);package,sources=package_sources()
    cfg=json.loads((package/'configs/experiments/search_space_probe_v1.json').read_text())
    budget=root/cfg['budget_receipt'];b=json.loads(budget.read_text())
    if digest(budget)!=cfg['budget_sha256']:raise ValueError('Budget receipt changed')
    if b['legacy_development_charge_seconds']+b['next_stage_reservation_seconds']+cfg['subsequent_reserved_seconds']+cfg['cpu_reservation_seconds']>b['development_limit_seconds']:raise ValueError('Original development budget exhausted')
    parent=root/cfg['parent_run'];m=json.loads((parent/'manifest.json').read_text())
    if json.loads((parent/'source-freeze.json').read_text())['status']!='CLOSED':raise ValueError('Parent run still frozen open')
    for run in cfg['closed_runs']:
        if json.loads((root/run/'source-freeze.json').read_text())['status']!='CLOSED':raise ValueError('Other owned run not closed')
    selection=root/cfg['selection'];assert digest(selection)==cfg['selection_sha256']
    keys=[x['task_key'] for x in json.loads(selection.read_text()) if x['stratum']=='failure'];assert len(keys)==8
    assert digest(parent/'tasks.jsonl')==m['tasks_file_sha256']
    assert digest(parent/'results-index.json')==json.loads((parent/'validation.json').read_text())['results_index_sha256']
    tasks={t['task_key']:t for t in map(json.loads,(parent/'tasks.jsonl').read_text().splitlines())}
    rows={x['task_key']:x for x in json.loads((parent/'results-index.json').read_text())}
    usage=psutil.cpu_percent(interval=1,percpu=True);allowed=sorted(os.sched_getaffinity(0))[:64]
    cpus=sorted((c for c in allowed if usage[c]<15),key=lambda c:usage[c])[:8]
    if len(cpus)<8 or psutil.virtual_memory().available<8*2*2**30:raise RuntimeError('Need8idleCPUs and16GiB; no launch')
    jobs=[]
    for key,cpu in zip(keys,cpus):
        row=rows[key];receipt=Path(row['receipt']);assert digest(receipt)==row['receipt_sha256']
        path=receipt.parent.parent/'execute/motion/result.json';old=json.loads(path.read_text());task=tasks[key]
        if (old['failure']!='search_budget_exhausted' or not key.startswith('train:') or old['official_policy']!='none'
                or content_digest(task)!=old['task_sha256'] or old['search_attempts'][-1]['stop_reason']!='expansion_limit'):raise ValueError('Frozen failure selection does not match diagnostic')
        jobs.append(dict(root=str(root),output=str(out/key.replace(':','-')),cpu=cpu,task=task,old=old,old_sha256=digest(path),sources=sources))
    out.mkdir();freeze_sources(out,sources);write_json(out/'controller-process.json',process_identity())
    write_json(out/'manifest.json',dict(config=cfg,sources=sources,parent_manifest_sha256=digest(parent/'manifest.json'),jobs=jobs,cpus=cpus,created_at=timestamp()))
    write_json(out/'source-freeze.json',dict(status='OPEN'))
    os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['CUDA_VISIBLE_DEVICES']=''
    resource.setrlimit(resource.RLIMIT_CPU,(99,100))
    try:
        with ProcessPoolExecutor(max_workers=8,mp_context=multiprocessing.get_context('spawn')) as pool:
            reports=list(pool.map(one_case,jobs))
        write_json(out/'validation.json',dict(status='COMPLETE_SEARCH_SPACE_DIAGNOSTIC_NOT_NEW_ORACLE',reports=reports,
            all_original_outcomes_reproduced=all(r['original_outcome_reproduced'] for r in reports),cpu_reservation_seconds=cfg['cpu_reservation_seconds'],
            whole_navigation_tasks_executed=0,navigation_recoveries=0,manifest_sha256=digest(out/'manifest.json')))
        return dict(tasks=len(reports),reproduced=sum(r['original_outcome_reproduced'] for r in reports))
    except BaseException as error:
        write_json(out/'failure.json',dict(type=type(error).__name__,detail=str(error)))
        raise
    finally:
        write_json(out/'source-freeze.json',dict(status='CLOSED'),immutable=False)
