"""Fixed initial primitive probes; no navigation score, resets are explicit."""
import json,math,os,signal,time
from pathlib import Path
from dataclasses import asdict
from collections import Counter
from oracle.common.artifacts import digest,content_digest,owned_output,write_json,package_sources,freeze_sources,runtime_identity,timestamp
from oracle.adapters.habitat.assets import resolve
from oracle.adapters.habitat.native import NativeAdapter,NativeState
from oracle.contracts import MotionContract
from oracle.verification.motion import native_violation,orientation_error
from oracle.verification.source_scene import SourceScene
from oracle.research.full_worker import process_identity


def classify_actions(rows):
    if len(rows)!=3 or {x['action'] for x in rows}!={1,2,3} or any(type(x['action']) is not int for x in rows):
        raise ValueError('All three distinct native primitives are required')
    if any(type(x[k]['admissible']) is not bool for x in rows for k in ['direct','pose_roundtrip']):
        raise ValueError('Unresolved admission cannot become a failed primitive')
    a=[x['action'] for x in rows if x['direct']['admissible']]
    b=[x['action'] for x in rows if x['pose_roundtrip']['admissible']]
    return dict(direct_legal_actions=a,pose_roundtrip_legal_actions=b,
                admission_disagreement=a!=b,all_direct_actions_rejected=not a,
                physical_unreachability_proven=False,navigation_tasks_recovered=0)


def run(case_root,output,cpu):
    import resource
    import numpy as np
    if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
    root=Path(case_root).resolve();out=owned_output(root,output);package,sources=package_sources()
    cfg=json.loads((package/'configs/experiments/initial_state_probe_v1.json').read_text())
    selection=root/cfg['cases'];assert digest(selection)==cfg['cases_sha256'];cases=json.loads(selection.read_text())
    if len(cases)!=27 or len({c['task']['task_key'] for c in cases})!=27:raise ValueError('Fixed27 scope differs')
    budget=json.loads((root/cfg['budget_admission']).read_text())
    if digest(root/cfg['budget_admission'])!=cfg['budget_admission_sha256']:raise ValueError('Budget admission changed')
    extra=cfg['prior_extra_reservation_seconds']+cfg['cpu_reservation_seconds']
    if (budget['legacy_development_charge_seconds']+budget['next_stage_reservation_seconds']+extra>budget['development_limit_seconds']
            or budget['overall_including_next_stage_reservation_seconds']+extra>budget['overall_limit_seconds']):raise ValueError('Original budget exhausted')
    if cpu not in sorted(os.sched_getaffinity(0))[:64]:raise ValueError('CPU outside authorized64')
    os.sched_setaffinity(0,{cpu});os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
    resource.setrlimit(resource.RLIMIT_CPU,(895,900))
    def expired(*_):raise TimeoutError('Fixed initial-state diagnostic wall cap')
    signal.signal(signal.SIGALRM,expired);signal.alarm(895)
    parent=root/cfg['parent_run'];manifest=json.loads((parent/'manifest.json').read_text())
    if digest(parent/'manifest.json')!=cfg['parent_manifest_sha256'] or json.loads((parent/'source-freeze.json').read_text())['status']!='CLOSED':raise ValueError('Parent identity/closure differs')
    protocol=manifest['protocol'];motion=MotionContract(**{k:protocol[k] for k in MotionContract.__dataclass_fields__})
    shared={tuple(c['task']['targets'][0]) for c in cases}
    if len(shared)!=1 or {c['task']['scene'] for c in cases}!={'oLBMNvg9in8'}:raise ValueError('Shared initial context changed')
    for c in cases:
        if digest(c['old_result'])!=c['old_result_sha256']:raise ValueError('Original failure evidence changed')
        old=json.loads(Path(c['old_result']).read_text())
        if old['actions'] or old['search_attempts'][-1]['expansions']!=1 or old['failure']!='search_frontier_exhausted':raise ValueError('Original initial-frontier category differs')
    asset,geometry=resolve(root,cases[0]['task'])
    if any(c['task']['profile_sha256']!=cases[0]['task']['profile_sha256'] or c['task']['geometry_catalog_sha256']!=cases[0]['task']['geometry_catalog_sha256'] for c in cases):raise ValueError('Mixed native contexts')
    source=SourceScene(geometry['receipt_path'],geometry['receipt_sha256'],protocol,catalog=geometry)
    out.mkdir();freeze_sources(out,sources);write_json(out/'controller-process.json',process_identity());write_json(out/'source-freeze.json',dict(status='OPEN'))
    started=time.perf_counter();records=[];actions_count=0
    def contact(a,b):
        f=source.contact(a,b,certificate=False);r=source.contact(a,b,certificate=True,arithmetic='rational_hull')
        hit=r or f;normal_y=None
        if hit:
            triangle=source.triangles[hit['triangle']];normal=np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0]);length=float(np.linalg.norm(normal))
            normal_y=float(normal[1]/length) if length else None
        return dict(float_contact=bool(f),rational_contact=bool(r),agree=bool(f)==bool(r),
                    contact=hit,triangle_normal_y=normal_y)
    def pose(s):return dict(position=list(s.position),rotation=list(s.quaternion_xyzw))
    def matrix(adapter):return np.asarray(adapter.sim.get_agent(0).body.object.transformation,dtype=float).copy()
    def step_record(adapter,before,action,target):
        after=adapter.step(action);reason=native_violation(adapter,before,after,action,protocol)
        distance=adapter.geodesic_distance(after.position,target);sweep=contact(before.position,after.position)
        point=contact(after.position,after.position)
        legal=reason is None and math.isfinite(distance) and not sweep['float_contact'] and not sweep['rational_contact']
        return dict(before=pose(before),after=pose(after),native_reason=reason,goal_distance_m=distance if math.isfinite(distance) else None,
                    source_sweep=sweep,source_after=point,admissible=bool(legal),matrix_after=matrix(adapter).tolist())
    try:
        import habitat_sim
        pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path'])
        p=np.asarray(next(iter(shared)),dtype=np.float32)
        snap=[float(x) for x in pf.snap_point(p)];zero=[float(x) for x in pf.try_step(p,p)]
        projection=dict(position=p.tolist(),snap=snap,zero_displacement_try_step=zero,
                        snap_displacement_m=math.dist(p,snap),zero_step_displacement_m=math.dist(p,zero),
                        zero_step_source=contact(p.tolist(),zero))
        write_json(out/'shared-projection.json',projection)
        for case in cases:
            t=case['task'];original=json.loads(Path(case['old_result']).read_text());initial=NativeState(tuple(t['targets'][0]),tuple(t['start_rotation']));rows=[]
            for action in (1,2,3):
                a=NativeAdapter(asset['navmesh_path'],asset['navmesh_sha256'],motion)
                b=NativeAdapter(asset['navmesh_path'],asset['navmesh_sha256'],motion)
                try:
                    a.restore(initial);b.restore(initial);pa=a.snapshot();before_b=b.snapshot()
                    if pa!=before_b:raise ValueError('Direct/roundtrip initializations differ before intervention')
                    initial_error=math.dist(pa.position,original['positions'][0])
                    if initial_error>protocol['maximum_prediction_error_m'] or orientation_error(pa.quaternion_xyzw,original['rotations'][0])>protocol['maximum_orientation_error_rad']:
                        raise ValueError('Original initialization not reproduced')
                    d=a.geodesic_distance(pa.position,t['targets'][1])
                    db=b.geodesic_distance(before_b.position,t['targets'][1])
                    if d!=db:raise ValueError('Initial query controls differ')
                    if not math.isfinite(d) or d<=motion.goal_radius_m:raise ValueError('Original unmet first reference changed')
                    before_contact=contact(pa.position,pa.position)
                    if before_contact['float_contact'] or before_contact['rational_contact']:raise ValueError('Original clear initial point not reproduced')
                    ma=matrix(a)
                    if not np.array_equal(ma,matrix(b)):raise ValueError('Initial native matrices differ before intervention')
                    b.restore(before_b);pb=b.snapshot();mb=matrix(b)
                    direct=step_record(a,pa,action,t['targets'][1]);roundtrip=step_record(b,pb,action,t['targets'][1]);actions_count+=2
                    rows.append(dict(action=action,direct=direct,pose_roundtrip=roundtrip,
                                     original_initial_position_exact=list(pa.position)==original['positions'][0],
                                     original_initial_rotation_exact=list(pa.quaternion_xyzw)==original['rotations'][0],
                                     pose_roundtrip_exact=pa==pb,matrix_roundtrip_exact=bool(np.array_equal(ma,mb)),
                                     matrix_max_delta=float(np.max(np.abs(ma-mb))),
                                     successor_position_delta=math.dist(direct['after']['position'],roundtrip['after']['position'])))
                finally:a.close();b.close()
            record=dict(task_key=t['task_key'],old_result_sha256=case['old_result_sha256'],actions=rows,classification=classify_actions(rows))
            records.append(record);write_json(out/'cases'/f"{t['task_key'].replace(':','-')}.json",record)
        assert len(records)==27 and actions_count==162
        summary=dict(status='COMPLETE_FIXED27_PRIMITIVE_CAUSAL_DIAGNOSTIC_NOT_NAVIGATION_RESULT',time=timestamp(),
                     tasks=27,primitive_executions=actions_count,navigation_tasks_evaluated=0,navigation_tasks_recovered=0,
                     all_direct_actions_rejected_tasks=sum(r['classification']['all_direct_actions_rejected'] for r in records),
                     pose_model_admission_disagreement_tasks=sum(r['classification']['admission_disagreement'] for r in records),
                     projection=projection,native_environment=runtime_identity(),protocol=protocol,
                     input_cases_sha256=digest(selection),wall_seconds=time.perf_counter()-started,process_cpu_seconds=time.process_time(),
                     cpu_reservation_seconds=cfg['cpu_reservation_seconds'],
                     limits='Explicit diagnostic resets and single-step branches, never a continuous navigation route. All original failures preserved. Source-contact interpretation and native state completeness are not assumed; no simulator, annotation or acceptance change.')
        write_json(out/'validation.json',summary);return summary
    except BaseException as error:
        write_json(out/'failure.json',dict(error=repr(error),completed_cases=len(records),primitive_executions=actions_count,time=timestamp()));raise
    finally:signal.alarm(0);write_json(out/'source-freeze.json',dict(status='CLOSED',live_phase_receipts=[]),immutable=False)
