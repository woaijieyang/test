"""Fixed old action sequences on a new mesh: diagnosis, never a PASS union."""
import json,math,os,signal,subprocess,sys,time
from pathlib import Path
from oracle.common.artifacts import digest,content_digest,owned_output,write_json,package_sources,freeze_sources,require_sources


def follow_plan(adapter,initial,targets,plan,radius,violation,contact,initial_check=lambda a,b:None):
    adapter.restore(initial);state=adapter.snapshot();positions=[list(state.position)];rotations=[list(state.quaternion_xyzw)];actions=[];boundaries=[];alerts=[];next_ref=1
    error=initial_check(initial,state)
    if error:alerts.append({'index':0,'kind':'initial_contract','detail':error})
    hit=contact(state.position,state.position)
    if hit:alerts.append({'index':0,'kind':'initial_source_contact','contact':hit})
    def advance():
        nonlocal next_ref
        while next_ref<len(targets) and adapter.geodesic_distance(state.position,targets[next_ref])<=radius:
            boundaries.append({'reference_index':next_ref,'action_index':len(actions)});next_ref+=1
    if not alerts:advance()
    for action in plan:
        if alerts or next_ref==len(targets):break
        if action not in (1,2,3):raise ValueError('Only original native primitives allowed')
        before=state;state=adapter.step(action);actions.append(action);positions.append(list(state.position));rotations.append(list(state.quaternion_xyzw))
        bad=violation(adapter,before,state,action);hit=contact(before.position,state.position)
        if bad:alerts.append({'index':len(actions),'kind':'native_action','reason':bad})
        if hit:alerts.append({'index':len(actions),'kind':'source_contact','contact':hit})
        if not alerts:advance()
    return dict(actions=actions,positions=positions,rotations=rotations,boundaries=boundaries,alerts=alerts,
        route_complete=next_ref==len(targets) and not alerts,next_reference_index=next_ref if next_ref<len(targets) else None,
        plan_primitives_available=len(plan),plan_primitives_consumed=len(actions))


def worker(case_root,manifest_path,task_file,output,cpu,arithmetic):
    import resource
    from oracle.adapters.habitat.assets import resolve
    from oracle.adapters.habitat.native import NativeAdapter,NativeState
    from oracle.contracts import MotionContract
    from oracle.verification.source_scene import SourceScene
    from oracle.verification.motion import native_violation
    from oracle.verification.execution_evidence import initial_contract_errors
    from oracle.research.full_worker import process_identity
    root=Path(case_root).resolve();out=owned_output(root,output);mp=Path(manifest_path);m=json.loads(mp.read_text());require_sources(m['sources'])
    job_path=Path(task_file);assert digest(job_path)==m['job_sha256'][job_path.name]
    job=json.loads(job_path.read_text());assert cpu in m['cpu_ids'] and arithmetic in ('float_projection','rational_hull')
    os.sched_setaffinity(0,{cpu});os.nice(15);resource.setrlimit(resource.RLIMIT_CPU,(39,40))
    def expired(*_):raise TimeoutError('Fixed45second replay diagnostic cap')
    signal.signal(signal.SIGALRM,expired);signal.alarm(45)
    out.mkdir(parents=True);write_json(out/'start.json',{**process_identity(),'manifest_sha256':digest(mp),'actual_module':__file__,'module_sha256':digest(__file__),'arithmetic':arithmetic,'cpu':cpu})
    task=job['task'];protocol=job['protocol'];asset,geometry=resolve(root,task)
    source=SourceScene(geometry['receipt_path'],geometry['receipt_sha256'],protocol,catalog=geometry)
    adapter=NativeAdapter(asset['navmesh_path'],asset['navmesh_sha256'],MotionContract(**{k:protocol[k] for k in MotionContract.__dataclass_fields__}))
    try:
        result=follow_plan(adapter,NativeState(tuple(task['targets'][0]),tuple(task['start_rotation'])),task['targets'],job['plan'],protocol['goal_radius_m'],
            lambda a,b,c,d:native_violation(a,b,c,d,protocol),lambda a,b:source.contact(a,b,certificate=arithmetic=='float_projection',arithmetic=arithmetic),
            lambda a,b:initial_contract_errors(a,b,protocol))
        endpoint_gate=all(source.contact(task['targets'][i],task['targets'][i],arithmetic=arithmetic) is None for i in {0,len(task['targets'])-1,*task['landmark_target_indices']})
        result.update(task_key=task['task_key'],endpoint_source_gate=endpoint_gate,initialization_count=adapter.restore_calls,
            source_plan_sha256=job['source_plan_sha256'],source_old_result_sha256=job['source_old_result_sha256'],
            task_sha256=content_digest(task),protocol_sha256=content_digest(protocol),profile_sha256=task['profile_sha256'],
            geometry_sha256=source.geometry_sha256,process_cpu_seconds=time.process_time(),arithmetic=arithmetic,
            meaning='Counterfactual execution of historical privileged actions, not the uniform Oracle method or a model result.')
        write_json(out/'result.json',result)
    finally:adapter.close();signal.alarm(0)


def run(case_root,output):
    import psutil,resource
    from oracle.verification.motion import orientation_error
    from oracle.research.full_worker import process_identity
    root=Path(case_root).resolve();out=owned_output(root,output);package,sources=package_sources();cfg=json.loads((package/'configs/experiments/prb_regression_plan_v1.json').read_text())
    budget=root/cfg['budget_receipt'];assert digest(budget)==cfg['budget_sha256'];b=json.loads(budget.read_text())
    assert b['development_after_new_reservation_seconds']+840+1800+2400+300<86400
    assert b['overall_after_new_reservation_seconds']+840+1800+2400+20*3600+300<2592000
    parent=root/cfg['new_run'];mp=parent/'manifest.json';assert digest(mp)==cfg['manifest_sha256'];m=json.loads(mp.read_text());comparison=json.loads((parent/'scene-comparison.json').read_text())
    assert comparison['regressed']==cfg['tasks'] and json.loads((parent/'source-freeze.json').read_text())['status']=='CLOSED'
    old=Path(m['parent_run']);oldm=json.loads((old/'manifest.json').read_text());assert digest(old/'manifest.json')==m['parent_manifest_sha256']
    assert digest(old/'results-index.json')==json.loads((old/'validation.json').read_text())['results_index_sha256']
    oldrows={x['task_key']:x for x in json.loads((old/'results-index.json').read_text())};tasks={t['task_key']:t for t in map(json.loads,(parent/'tasks.jsonl').read_text().splitlines())}
    assert digest(parent/'tasks.jsonl')==m['tasks_file_sha256']
    usage=psutil.cpu_percent(interval=1,percpu=True);cpus=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<15][:2]
    if len(cpus)<2:raise RuntimeError('Need2idleCPUs; no diagnostic started')
    resource.setrlimit(resource.RLIMIT_CPU,(39,40));out.mkdir();freeze_sources(out,sources);write_json(out/'controller-process.json',process_identity());write_json(out/'source-freeze.json',{'status':'OPEN'})
    jobs={}
    for key in cfg['tasks']:
        entry=oldrows[key];receipt=Path(entry['receipt']);assert digest(receipt)==entry['receipt_sha256'];record_path=receipt.parent.parent/'execute/motion/result.json';record=json.loads(record_path.read_text())
        assert digest(record_path)==json.loads(receipt.read_text())['result_sha256']
        assert entry['status']=='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES' and record['protocol']==m['protocol']
        oldindex=next(x['record'] for x in json.loads((old/'index.json').read_text()) if x['record']['task_key']==key)
        with (old/'tasks.jsonl').open('rb') as stream:stream.seek(oldindex['offset']);raw=stream.read(oldindex['bytes'])
        assert __import__('hashlib').sha256(raw).hexdigest()==oldindex['sha256'];oldtask=json.loads(raw);task=tasks[key]
        assert oldtask['targets']==task['targets'] and oldtask['start_rotation']==task['start_rotation'] and oldtask['privileges']==task['privileges']
        job=out/(key.replace(':','-')+'.json');write_json(job,dict(task=task,protocol=m['protocol'],plan=record['actions'],source_plan_sha256=content_digest(record['actions']),source_old_result_sha256=digest(record_path)))
        jobs[job.name]=digest(job)
    write_json(out/'manifest.json',dict(config=cfg,sources=sources,cpu_ids=cpus,job_sha256=jobs,privileged_information='Historical same-task successful action sequence; diagnostic only, not added to model or uniform Oracle.'))
    results=[]
    try:
        for number,name in enumerate(jobs):
            phases=[]
            for arithmetic in ('float_projection','rational_hull'):
                directory=out/name.removesuffix('.json')/arithmetic
                with (out/(name+'.'+arithmetic+'.log')).open('xb') as log:
                    subprocess.run([sys.executable,'-B',str(root/'oracleAdapter/run.py'),'diagnose-prb-plans','--case-root',str(root),'--manifest',str(out/'manifest.json'),'--task-file',str(out/name),'--output',str(directory),'--cpu',str(cpus[number]),'--method',arithmetic],stdout=log,stderr=subprocess.STDOUT,check=True,env={**os.environ,'CUDA_VISIBLE_DEVICES':'','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'})
                phases.append(json.loads((directory/'result.json').read_text()))
            a,c=phases;assert a['initialization_count']==c['initialization_count']==1
            same=a['actions']==c['actions'] and len(a['positions'])==len(c['positions'])
            error=max((math.dist(p,q) for p,q in zip(a['positions'],c['positions'])),default=0.) if same else None
            angle=max((orientation_error(p,q) for p,q in zip(a['rotations'],c['rotations'])),default=0.) if same else None
            results.append(dict(task_key=a['task_key'],float_complete=a['route_complete'],rational_complete=c['route_complete'],
                matched_actions=same,max_position_error_m=error,max_orientation_error_rad=angle,attempted_actions=len(a['actions']),
                float_alerts=a['alerts'],rational_alerts=c['alerts'],next_reference_index=a['next_reference_index'],
                route_witness_in_new_profile=same and error<=m['protocol']['maximum_replay_error_m'] and angle<=m['protocol']['maximum_orientation_error_rad'] and a['route_complete'] and c['route_complete'] and a['endpoint_source_gate'] and c['endpoint_source_gate']))
        result=dict(status='COMPLETE2_COUNTERFACTUAL_PLAN_DIAGNOSTIC_NOT_UNIFORM_ORACLE_RESULT',tasks=2,results=results,
            manifest_sha256=digest(out/'manifest.json'),reserved_cpu_seconds=300,whole660_result_modified=False)
        write_json(out/'validation.json',result);return result
    except BaseException as error:write_json(out/'failure.json',{'error':repr(error)});raise
    finally:write_json(out/'source-freeze.json',{'status':'CLOSED'},immutable=False)
