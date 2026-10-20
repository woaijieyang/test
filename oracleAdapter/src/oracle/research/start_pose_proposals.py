"""Fixed-family initial-point proposals with unchanged native/source admission."""
import json,math,os,time,signal
from pathlib import Path
from oracle.common.artifacts import digest,content_digest,owned_output,write_json,package_sources,freeze_sources,runtime_identity,timestamp
from oracle.research.full_worker import process_identity
from oracle.adapters.habitat.assets import resolve
from oracle.adapters.landmark_rxr.source_bounded_candidates import collect_candidates
from oracle.verification.source_scene import SourceScene
from oracle.planners.collision_queries import CachedSourceQueries


def fixed_ring_offsets(rings):
    if any(type(n) is not int or n<1 or not math.isfinite(radius) or radius<=0 for radius,n in rings):
        raise ValueError('Explicit finite old ring family required')
    return [(radius*math.cos(i*2*math.pi/n),radius*math.sin(i*2*math.pi/n)) for radius,n in rings for i in range(n)]


def frozen_anchor(task,proposal):
    if (proposal['proposed_targets']!=task['targets'] or proposal['original_heading']!=task['raw_heading']
            or proposal['legacy_source_record_sha256']!=task['legacy_source_record_sha256']):
        raise ValueError('Current task is not the frozen derived proposal')
    choice=proposal['choices'][0]
    if choice['anchor_kind']!='bounded_camera_projection' or choice['anchor']!=proposal['old_targets'][0]:
        raise ValueError('Initial anchor must remain the original pre-repair fallback, not the repaired coordinate')
    return choice['anchor']


def run(case_root,output,cpu):
    import resource
    if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
    root=Path(case_root).resolve();out=owned_output(root,output);package,sources=package_sources()
    cfg=json.loads((package/'configs/experiments/start_pose_proposals_v1.json').read_text())
    budget=json.loads((root/cfg['budget_admission']).read_text())
    if digest(root/cfg['budget_admission'])!=cfg['budget_admission_sha256']:raise ValueError('Budget admission drift')
    extra=cfg['prior_extra_reservation_seconds']+cfg['cpu_reservation_seconds']
    if budget['legacy_development_charge_seconds']+budget['next_stage_reservation_seconds']+extra>budget['development_limit_seconds']:raise ValueError('Development budget exhausted')
    if budget['overall_including_next_stage_reservation_seconds']+extra>budget['overall_limit_seconds']:raise ValueError('Overall budget exhausted')
    cp=root/cfg['cases'];assert digest(cp)==cfg['cases_sha256'];cases=json.loads(cp.read_text())
    diagnostic_path=root/cfg['diagnostic'];assert digest(diagnostic_path)==cfg['diagnostic_sha256'];diag=json.loads(diagnostic_path.read_text())
    if len(cases)!=27 or diag['all_direct_actions_rejected_tasks']!=27 or diag['pose_model_admission_disagreement_tasks']:
        raise ValueError('Data repair cannot hide a demonstrated planner/actual-state discrepancy')
    if cpu not in sorted(os.sched_getaffinity(0))[:64]:raise ValueError('CPU outside authorized64')
    os.sched_setaffinity(0,{cpu});os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15);resource.setrlimit(resource.RLIMIT_CPU,(895,900))
    def expired(*_):raise TimeoutError('Fixed starting-pose proposal budget')
    signal.signal(signal.SIGALRM,expired);signal.alarm(895)
    parent=root/'outputs/oracleAdapter/landmark-global-source-priority-v1';m=json.loads((parent/'manifest.json').read_text());protocol=m['protocol']
    if not protocol['allow_sliding']:raise ValueError('Different native filter protocol')
    policy=json.loads((package/'configs/experiments/global_bounded_mapping_v1.json').read_text())
    offsets=fixed_ring_offsets(policy['rings'])
    auditpath=root/'outputs/oracleAdapter/global-bounded-static-audit-v2/validation.json'
    if digest(auditpath)!=m['input_hashes']['global_audit']:raise ValueError('Original derived audit changed')
    av=json.loads(auditpath.read_text());ap=auditpath.parent/'all33954-records.json';assert digest(ap)==av['records_sha256']
    audited={x['task_key']:x for x in json.loads(ap.read_text())}
    pubpath=root/policy['inputs']['published']['path'];assert digest(pubpath)==policy['inputs']['published']['sha256']
    published={(x['scene'],x['node']):x for x in json.loads(pubpath.read_text())['nodes']}
    asset,geometry=resolve(root,cases[0]['task']);source=SourceScene(geometry['receipt_path'],geometry['receipt_sha256'],protocol,catalog=geometry)
    body=CachedSourceQueries(source,context_digest=content_digest([sources,cfg,protocol,geometry]),**policy['query_cache'])
    import habitat_sim
    pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path'])
    out.mkdir();freeze_sources(out,sources);write_json(out/'controller-process.json',process_identity());write_json(out/'source-freeze.json',dict(status='OPEN'))
    checks={};records=[];queries={'snap':0,'path':0,'zero_step':0};started=time.perf_counter()
    def connected(a,b):
        queries['path']+=1;p=habitat_sim.ShortestPath();p.requested_start=a;p.requested_end=b
        return bool(pf.find_path(p) and math.isfinite(p.geodesic_distance))
    def snap(q):queries['snap']+=1;return pf.snap_point(q)
    def contact(a,b):
        f=body.contact(a,b,certificate=True);r=body.contact(a,b,certificate=True,arithmetic='rational_hull')
        if bool(f)!=bool(r):raise ValueError('Source predicate disagreement')
        return r
    def admission(q):
        key=content_digest(q)
        if key not in checks:
            queries['zero_step']+=1;z=[float(x) for x in pf.try_step(q,q)];reason=None;hit=None
            if not all(math.isfinite(v) for v in z) or not pf.is_navigable(z):reason='zero_filter_offmesh'
            elif math.hypot(z[0]-q[0],z[2]-q[2])>protocol['horizontal_tolerance_m']:reason='zero_filter_horizontal_limit'
            elif abs(z[1]-q[1])>protocol['maximum_vertical_transition_m']:reason='zero_filter_vertical_limit'
            elif not connected(q,z) or not connected(z,q):reason='zero_filter_component_change'
            else:
                hit=contact(q,z)
                if hit:reason='zero_filter_source_contact'
            checks[key]={'before':q,'after':z,'reason':reason,'source_contact':hit}
        return checks[key]['reason']
    try:
        for case in cases:
            t=case['task'];key=t['task_key'];oldpath=root/'outputs/oracleAdapter/global-bounded-mapping-v1/tasks'/f"{key.replace(':','-')}.json"
            if digest(oldpath)!=audited[key]['proposal_sha256']:raise ValueError('Original proposal chain changed')
            old=json.loads(oldpath.read_text());anchor=frozen_anchor(t,old);ident=published[(t['scene'],t['original_viewpoint_path'][0])]
            if t['scene']!='oLBMNvg9in8' or t['profile_sha256']!=cases[0]['task']['profile_sha256']:raise ValueError('Selected context drift')
            goal=t['targets'][1]
            component=lambda q:0 if connected(q,goal) and connected(goal,q) else 1
            args=dict(anchor=anchor,anchor_kind='bounded_camera_projection',camera=ident['camera_position'],current=t['targets'][0],
                      offsets=offsets,snap=snap,navigable=pf.is_navigable,contact=lambda q:contact(q,q),component=component,
                      sphere_m=.5,extra_horizontal_m=.350001,retain_seed_metadata=True)
            baseline=collect_candidates(**args);filtered=collect_candidates(**args,candidate_admission=admission)
            choice=filtered['options'].get(0);points=None
            if choice:
                points=[choice['position']]+t['targets'][1:]
                if any(contact(q,q) for q in points) or not all(connected(a,b) and connected(b,a) for a,b in zip(points,points[1:])):
                    raise ValueError('Full unchanged-reference/static source gate failed')
            rec=dict(task_key=key,status='INITIAL_FILTER_SAFE_PROPOSAL_PENDING_INDEPENDENT_AUDIT' if choice else 'NO_ADMISSIBLE_START_IN_FIXED_FAMILY',
                     original_anchor=anchor,raw_camera=ident['camera_position'],old_targets=t['targets'],proposed_targets=points,
                     original_heading=t['raw_heading'],start_rotation=t['start_rotation'],choice=choice,
                     original_proposal_sha256=digest(oldpath),baseline=baseline,filtered=filtered,adopted=False,native_actions=0)
            records.append(rec);write_json(out/'tasks'/f"{key.replace(':','-')}.json",rec)
        write_json(out/'zero-filter-checks.json',checks);write_json(out/'records27.json',records)
        summary=dict(status='COMPLETE_FIXED27_INITIAL_PROPOSALS_NOT_MOTION_ACCEPTANCE',time=timestamp(),tasks=27,
                     proposed=sum(r['proposed_targets'] is not None for r in records),unresolved=sum(r['proposed_targets'] is None for r in records),
                     unique_proposed_starts=[list(q) for q in sorted({tuple(r['proposed_targets'][0]) for r in records if r['proposed_targets']})],
                     native_actions=0,adopted_mappings=0,query_counts=queries,zero_filter_failures=sum(x['reason'] is not None for x in checks.values()),
                     wall_seconds=time.perf_counter()-started,process_cpu_seconds=time.process_time(),native_environment=runtime_identity(),
                     records_sha256=digest(out/'records27.json'),checks_sha256=digest(out/'zero-filter-checks.json'),
                     limits='Original source anchor and old ring family retained; only initial coordinate proposed. Native filter/gates unchanged. Static/zero-filter checks do not replace independent actual full-route execution and replay.')
        write_json(out/'validation.json',summary);return summary
    except BaseException as error:
        write_json(out/'failure.json',dict(error=repr(error),completed_records=len(records),time=timestamp()));raise
    finally:signal.alarm(0);write_json(out/'source-freeze.json',dict(status='CLOSED',live_phase_receipts=[]),immutable=False)
