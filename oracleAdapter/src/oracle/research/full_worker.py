"""Frozen full-run worker phases; each audit is a separate native process."""
import json
import math
import os
from pathlib import Path
import time
import traceback
import sys
import signal

from oracle.adapters.habitat.assets import resolve
from oracle.adapters.habitat.native import NativeAdapter
from oracle.adapters.unified_inventory import finite_point,pose_relation
from oracle.common.artifacts import content_digest,digest,owned_output,require_sources,timestamp,write_json
from oracle.common.task_index import verify_entry
from oracle.contracts import MotionContract
from oracle.verification.binding import bind_callable
from oracle.verification.source_scene import SourceScene


def process_identity():
    fields=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()
    return {'pid':os.getpid(),'start_ticks':fields[19]}


def load_task(root,manifest,entry,stream_path):
    indexed=verify_entry(entry,manifest['task_merkle_root'],manifest['task_count'])
    with Path(stream_path).open('rb') as stream:
        stream.seek(indexed['offset']);raw=stream.read(indexed['bytes'])
    if __import__('hashlib').sha256(raw).hexdigest()!=indexed['sha256']:raise ValueError('Frozen task bytes changed')
    task=json.loads(raw)
    if task['task_key']!=indexed['task_key']:raise ValueError('Actual task differs from ticket')
    return task,indexed


def effective_method(task,manifest):
    hint=task.get('official_demonstration')
    eligible=False
    if hint is not None:
        relation=pose_relation(task,{'start_position':hint['start_position'],'quaternion_xyzw':hint['start_rotation']},
            manifest['protocol']['maximum_prediction_error_m'],manifest['protocol']['maximum_orientation_error_rad'])
        eligible=bool(relation['numeric_initial_pose_match'] and task['coordinates_complete'])
        if not eligible or hint['instruction_id']!=task['instruction_id'] or hint['scene']!=task['scene']:
            raise ValueError('Incompatible official initial state/identity must not be silently used')
        if content_digest(hint['actions'])!=hint['actions_sha256']:raise ValueError('Official action digest changed')
    policy='guard_then_search' if eligible else 'none'
    if task['method_selection']['official_policy']!=policy or ('official_actions' in task['privileges'])!=eligible:
        raise ValueError('Selected information/policy differs from compiled input')
    default_id='matched_reference_prefix' if eligible else 'bounded_reference_search'
    return {**manifest['base_method'],'id':manifest['base_method'].get('id',default_id),'official_policy':policy}


def preflight(root,task,protocol,rational=False):
    missing=[i for i,p in enumerate(task['targets']) if not finite_point(p)]
    if not task['targets'] or missing or not task['geometry_catalog_present']:
        return {'native_ready':False,'failure':'identity_or_adaptation_missing','missing_target_indices':missing,
                'geometry_catalog_present':task['geometry_catalog_present'],'points':[],'links':[],
                'endpoint_source_gate':False,'native_actions':0}
    asset,geometry=resolve(root,task)
    motion=MotionContract(**{k:protocol[k] for k in MotionContract.__dataclass_fields__})
    simulator=NativeAdapter(asset['navmesh_path'],asset['navmesh_sha256'],motion)
    source=SourceScene(geometry['receipt_path'],geometry['receipt_sha256'],protocol,catalog=geometry)
    points=[];links=[]
    try:
        for i,p in enumerate(task['targets']):
            contact=source.contact(p,p,arithmetic='rational_hull') if rational else source.contact(p,p,certificate=True)
            points.append({'index':i,'navigable':simulator.is_navigable(p),'source_contact':contact})
        for i,(a,b) in enumerate(zip(task['targets'],task['targets'][1:])):
            distance=simulator.geodesic_distance(a,b)
            links.append({'index':i,'finite':math.isfinite(distance),'distance_m':distance if math.isfinite(distance) else None})
    finally:simulator.close()
    endpoints={0,len(points)-1,*task.get('landmark_target_indices',[])}
    endpoint_gate=all(points[i]['source_contact'] is None for i in endpoints)
    ready=all(p['navigable'] for p in points) and all(p['finite'] for p in links)
    return {'native_ready':ready,'failure':None if ready else 'topology_mapping_error',
            'missing_target_indices':[],'geometry_catalog_present':True,'points':points,'links':links,
            'endpoint_indices':sorted(endpoints),'endpoint_source_gate':endpoint_gate,'native_actions':0,
            'source_geometry_sha256':source.geometry_sha256,
            'scope':'All target navigability/adjacency; source body checked at every anchor, endpoint gate separate from route-region feasibility'}


def compare_preflight(a,b):
    for field in ('native_ready','failure','missing_target_indices','geometry_catalog_present','endpoint_source_gate'):
        if a[field]!=b[field]:raise ValueError('Independent preflight disagreement: '+field)
    if len(a['points'])!=len(b['points']) or len(a['links'])!=len(b['links']):raise ValueError('Static scope differs')
    for x,y in zip(a['points'],b['points']):
        if x['index']!=y['index'] or x['navigable']!=y['navigable'] or bool(x['source_contact'])!=bool(y['source_contact']):
            raise ValueError('Native/source anchor verdict differs')
    for x,y in zip(a['links'],b['links']):
        if x['index']!=y['index'] or x['finite']!=y['finite']:raise ValueError('Connectivity verdict differs')
        if x['finite'] and not math.isclose(x['distance_m'],y['distance_m'],rel_tol=1e-6,abs_tol=1e-5):raise ValueError('Geodesic distance differs')


def validate_launchers(root,manifest):
    root=Path(root).resolve()
    expected={str(root/'oracleAdapter/run.py'),str(root/'scripts/with_runtime.sh')}
    launchers=manifest.get('launchers')
    if not isinstance(launchers,dict) or set(launchers)!=expected:
        raise ValueError('Both exact Case1 launcher identities must be frozen before startup')
    if any(digest(p)!=sha for p,sha in launchers.items()):raise ValueError('Launcher changed')


def phase(case_root,manifest_path,ticket_path,phase_dir,cpu,role):
    import resource
    root=Path(case_root).resolve();manifest_path=Path(manifest_path);study=owned_output(root,manifest_path.parent)
    directory=owned_output(root,phase_dir);ticket_path=owned_output(root,ticket_path)
    manifest=json.loads(manifest_path.read_text());package=require_sources(manifest['sources'])
    cap=int(manifest['config']['per_process_wall_seconds'])
    resource.setrlimit(resource.RLIMIT_CPU,(cap,cap+5))
    if not directory.is_relative_to(study) or not ticket_path.is_relative_to(study):raise ValueError('Phase escaped frozen run')
    validate_launchers(root,manifest)
    ticket=json.loads(ticket_path.read_text())
    if ticket['manifest_sha256']!=digest(manifest_path):raise ValueError('Ticket manifest identity mismatch')
    task,entry=load_task(root,manifest,ticket['entry'],study/'tasks.jsonl');method=effective_method(task,manifest)
    if cpu not in sorted(os.sched_getaffinity(0))[:64]:raise ValueError('CPU outside allowed affinity')
    os.sched_setaffinity(0,[cpu]);os.nice(10);os.environ['CUDA_VISIBLE_DEVICES']=''
    directory.mkdir(parents=True,exist_ok=True)
    from oracle.teachers.ordered import execute
    from oracle.verification.route_replay import audit
    teacher=bind_callable(execute,manifest['config']['teacher'],package);auditor=bind_callable(audit,manifest['config']['auditor'],package)
    worker_binding=bind_callable(phase,manifest['config']['worker'],package)
    identity=process_identity()
    startup={**identity,'role':role,'started_at':timestamp(),'started_monotonic':time.monotonic(),
        'manifest_sha256':digest(manifest_path),'ticket_sha256':digest(ticket_path),'task_sha256':content_digest(task),
        'method_sha256':content_digest(method),'teacher':teacher,'auditor':auditor,'worker':worker_binding,'cpu':cpu,'entry':entry,'argv':sys.argv}
    write_json(directory/'start.json',startup)
    status='INFRASTRUCTURE_FAILURE';error=None;error_type=None
    try:
        deadline=time.monotonic()+300
        while not (directory/'permit.json').exists():
            if time.monotonic()>deadline:raise RuntimeError('Controller did not grant the identity-bound start permit')
            time.sleep(.2)
        permit=json.loads((directory/'permit.json').read_text())
        if any(permit[k]!=startup[k] for k in ('pid','start_ticks','manifest_sha256','task_sha256')):raise ValueError('Start permit identity mismatch')
        def expired(*_):raise TimeoutError('Declared phase wall cap exceeded')
        signal.signal(signal.SIGALRM,expired);signal.alarm(cap)
        if role=='execute':
            static=preflight(root,task,manifest['protocol']);write_json(directory/'preflight.json',static)
            if static['native_ready']:
                result=execute(root,task,method,manifest['protocol'],directory/'motion')
                if result['teacher_sha256']!=teacher['sha256']:raise ValueError('Actual teacher identity differs')
            receipt={'status':'EXECUTION_PHASE_COMPLETE','task_sha256':content_digest(task),'method':method,
                'preflight_sha256':digest(directory/'preflight.json'),'manifest_sha256':startup['manifest_sha256'],
                'result_sha256':digest(directory/'motion/result.json') if static['native_ready'] else None}
            write_json(directory/'receipt.json',receipt)
        elif role=='audit':
            execution=owned_output(root,ticket['execution_directory'])
            if execution.parent!=directory.parent or execution.name!='execute':raise ValueError('Audit cannot attach a different execution attempt')
            start=json.loads((execution/'start.json').read_text())
            if any(start[k]!=startup[k] for k in ('manifest_sha256','task_sha256','method_sha256')) or start['teacher']!=teacher:
                raise ValueError('Execution startup identity mismatch')
            original=json.loads((execution/'preflight.json').read_text())
            independent=preflight(root,task,manifest['protocol'],rational=True);compare_preflight(original,independent)
            write_json(directory/'preflight.json',independent)
            if independent['native_ready']:
                result_path=execution/'motion/result.json';record=json.loads(result_path.read_text())
                if (record['task_sha256']!=startup['task_sha256'] or record['method']!=method or record['protocol']!=manifest['protocol']
                    or record['teacher_sha256']!=teacher['sha256'] or Path(record['actual_teacher_path']).resolve()!=Path(teacher['actual_path']).resolve()):
                    raise ValueError('Actual task/method/teacher binding mismatch')
                motion=audit(root,task,result_path,directory/'motion-audit.json')
                if motion['issues']:raise ValueError('Independent motion audit disagreement')
                accepted=motion['full_route_accepted'] and independent['endpoint_source_gate']
                outcome='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES' if accepted else 'ROUTE_WITNESS_ONLY_ENDPOINT_SOURCE_GATE_FAIL' if motion['full_route_accepted'] else 'FAILURE_PRESERVED'
                failure=record['failure'] if not motion['full_route_accepted'] else None if accepted else 'source_geometry_contact_at_reference_endpoint'
                counts={'actual_actions':len(record['actions']),'replayed_actions':motion['executed_actions_replayed'],
                        'motion_attempted':True,'official_primitives_consumed':record.get('official_primitives_consumed',0)}
            else:
                outcome='STATIC_FAILURE_PRESERVED';failure=independent['failure'];counts={'actual_actions':0,'replayed_actions':0,'motion_attempted':False,'official_primitives_consumed':0}
            receipt={'status':outcome,'failure':failure,'task_key':task['task_key'],'dataset':task['dataset'],'cohort':task['cohort'],
                'task_sha256':startup['task_sha256'],'manifest_sha256':startup['manifest_sha256'],'method':method,
                'execution_start_sha256':digest(execution/'start.json'),'preflight_sha256':digest(directory/'preflight.json'),
                'execution_receipt_present':(execution/'receipt.json').exists(),
                'result_sha256':digest(execution/'motion/result.json') if independent['native_ready'] else None,
                'motion_audit_sha256':digest(directory/'motion-audit.json') if independent['native_ready'] else None,**counts}
            write_json(directory/'receipt.json',receipt)
        else:raise ValueError('Unknown worker phase')
        require_sources(manifest['sources']);status='COMPLETE'
    except BaseException as exc:
        error=repr(exc);error_type=type(exc).__name__;raise
    finally:
        signal.alarm(0)
        write_json(directory/'exit.json',{'status':status,'error':error,'error_type':error_type,'ended_at':timestamp(),'ended_monotonic':time.monotonic(),
            'process_cpu_seconds':time.process_time(),'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,**identity})
