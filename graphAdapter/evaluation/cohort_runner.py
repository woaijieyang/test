"""Explicit sealed-member stage001 runner for the active simulator provider.

Uses the unchanged native evaluator. This entry replaces experiment-specific
launch scripts; it never starts native pose, changes policy, or selects B/Remaining.
"""
from pathlib import Path
import gzip,json,os,subprocess,time
from .selector import selected_rows
from .registry_binding import sha,source_snapshot
from .runner import navigation_worker_environment,navigation_policy_identity

def choose_members(entries,dataset,allowed):
    by_identity={tuple(row['identity']):row for row in allowed}
    selected=[];seen=set()
    for entry in entries:
        member=tuple(entry['member'])
        if len(member)!=4:raise ValueError('Full four-field cohort identity required')
        if member[0]!=dataset:continue
        if member in seen:raise ValueError('Duplicate cohort member')
        if member not in by_identity:raise ValueError('Cohort member is outside sealed A')
        seen.add(member);selected.append(by_identity[member])
    return selected

def evaluate_cohort(bindings,profile_path,registry,partition,datasets,output,*,cohort_plan,hook_mode='on',attempt_id='attempt0',preflight_only=False,registered_limit=None,exact_registered=False):
    from graphAdapter.map_memory.storage.routing import load_run
    from graphAdapter.interfaces.pose.policy import require_simulator_profile
    from case1_runtime.scene_assets import verify_scene_binding
    root=Path(bindings['project_root']).resolve();out=Path(output).resolve()
    if root!=Path(__file__).resolve().parents[3]:raise ValueError('Binding project differs from protected execution root')
    if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
    if partition!='A' or hook_mode not in ('on','off'):raise ValueError('Explicit stage001 A/cohort hook mode required')
    if not datasets or len(set(datasets))!=len(datasets) or not set(datasets)<={'r2r','rxr_us'}:raise ValueError('Declared dataset list required')
    route_path=os.environ.get('CASE2_STORAGE_RUN')
    if not route_path:raise RuntimeError('Prepare an owned storage run and use --storage-run')
    run,route=load_run(route_path);plan_path=Path(cohort_plan).resolve()
    if plan_path!=run/'retention_plan.json' or not out.is_relative_to(run):raise ValueError('Cohort/output must belong to the active routing run')
    plan=json.loads(plan_path.read_bytes())
    stage=plan.get('stage')
    if stage not in ('001','002'):raise ValueError('This entry implements registered001/002 cohorts')
    if plan.get('production_schema')!='simulator_endpoint_v1':raise ValueError('Simulator cohort requires its endpoint schema')
    if len({x['key']for x in plan['entries']})!=len(plan['entries']):raise ValueError('Duplicate cohort key')
    profile={}
    if hook_mode=='on':
        profile=json.loads(Path(profile_path).read_bytes());require_simulator_profile(profile)
        if profile.get('stage')!=stage or profile.get('frontier') or profile.get('navigation'):
            raise ValueError('Profile stage must match its registered memory cohort')
        if stage=='001' and profile.get('memory_injection'):
            raise ValueError('001 only builds and stores shadow memory')
        if stage=='002':
            from graphAdapter.interfaces.retrieval import retrieval_settings
            settings=retrieval_settings(profile.get('map_memory',{}))
            if settings is None or profile.get('mode')!=settings['mode']:
                raise ValueError('002 host and worker retrieval mode must match')
        memory=profile.get('map_memory',{})
        if not memory.get('enabled') or memory.get('execution_mode','live')!='live':raise ValueError('Actual live geometry/perception required')
        from graphAdapter.map_memory.worker import validate_mapping_profile
        validate_mapping_profile(memory)
        if not os.environ.get('GRAPH_MEMORY_BROKER'):raise RuntimeError('Hook-on requires --memory-broker')
        if plan.get('owner_components',{}).get('pose')!='pose_provider':raise ValueError('Typed pose-provider owner required')
    if sha(Path(registry)/'seal.json')!=bindings['dataset_seal_sha256']:raise ValueError('Dataset seal drift')
    assets=verify_scene_binding(root,bindings);prepared={}
    for dataset in datasets:
        asset=bindings['datasets'][dataset]
        for name in ('annotation','gt'):
            if sha(Path(asset[name]))!=asset[name+'_sha256']:raise ValueError('Dataset asset drift')
        with gzip.open(asset['annotation'],'rt')as stream:data=json.load(stream)
        allowed=selected_rows(registry,dataset,'A',data,None)
        chosen=choose_members(plan['entries'],dataset,allowed)
        if exact_registered:
            if registered_limit is not None and (type(registered_limit)is not int or registered_limit<=0):
                raise ValueError('Positive limit per dataset required')
            if [row['identity']for row in chosen]!=[row['identity']for row in allowed[:registered_limit]]:
                raise ValueError('Storage plan must match the requested sealed A prefix in order')
        if not chosen:raise ValueError('Empty undeclared domain')
        if any(row['identity'][1]not in assets['assets']for row in chosen):raise ValueError('Scene absent from frozen asset binding')
        prepared[dataset]=(data,chosen)
    if not set(os.sched_getaffinity(0))<=set(bindings['cpu_assignment']):raise ValueError('CPU affinity outside registered assignment')
    gpus=[int(x)for x in os.environ.get('CUDA_VISIBLE_DEVICES','').split(',')if x]
    if len(gpus)!=1 or gpus[0]not in bindings['gpu_assignment']:raise ValueError('One registered GPU required')
    out.mkdir(parents=True,exist_ok=False)
    source_files,source_sha=source_snapshot(root,map_stage=True)
    metadata=dict(stage=stage,hook_mode=hook_mode,cohort_plan=str(plan_path),plan_sha256=route['plan_sha256'],source_sha256=source_sha,
        domains={d:[list(x['identity'])for x in rows]for d,(_,rows)in prepared.items()},scope='Registered explicit members; no inferred sample size; native evaluator unchanged')
    (out/'preflight.json').write_text(json.dumps(dict(metadata,status='PREFLIGHT_ONLY'if preflight_only else'ADMITTED'),indent=2))
    if preflight_only:return [dict(status='preflight_verified',dataset=d,members=len(rows))for d,(_,rows)in prepared.items()]
    from .resources import admit
    results=[]
    for dataset,(data,chosen)in prepared.items():
        domain=out/dataset;domain.mkdir()
        with gzip.open(domain/'annotation.json.gz','wt')as stream:json.dump(dict(data,episodes=[x['row']for x in chosen]),stream)
        asset=bindings['datasets'][dataset]
        spec=dict(annotation=str(domain/'annotation.json.gz'),annotation_sha256=sha(domain/'annotation.json.gz'),gt=asset['gt'],gt_sha256=asset['gt_sha256'])
        (domain/'dataset-spec.json').write_text(json.dumps(spec));(domain/'ids.json').write_text(json.dumps([str(x['row']['episode_id'])for x in chosen]))
        policy=navigation_policy_identity(True,hook_mode)
        if stage=='002':
            policy.update(sidecar_feature='graph_memory',policy_input_mode=profile.get('mode','uniform_original') if hook_mode=='on'else'uniform_original',pose_condition='simulator_pose_diagnostic')
        manifest=dict(metadata,**policy,frozen_files=source_files,scene_assets=assets,
            dataset_spec_sha256=sha(domain/'dataset-spec.json'),profile_sha256=sha(Path(profile_path))if hook_mode=='on'else None)
        (domain/'run_manifest.json').write_text(json.dumps(manifest,indent=2))
        env=navigation_worker_environment(os.environ,domain=domain,source_sha=source_sha,run_uid=route['run_uid'],attempt_id=attempt_id,dataset=dataset,map_stage=True,hook_mode=hook_mode,profile_path=profile_path)
        for name in ('POSEADAPTER_BROKER','POSEADAPTER_BROKER_PID'):env.pop(name,None)
        env['CASE2_STORAGE_BINDING']=json.dumps(dict(root=str(run),plan_sha256=route['plan_sha256'],side='shadow'if hook_mode=='on'else'control',attempt=attempt_id,worker_id=dataset+'-'+hook_mode))
        command=[bindings['host_python'],str(root/'scripts/evaluate_worker.py'),'--dataset','rxr'if dataset=='rxr_us'else dataset,'--output',str(domain/'worker'),'--scenes',assets['scene_root'],'--chunk','0','--chunks','1','--ids',str(domain/'ids.json'),'--dataset-spec',str(domain/'dataset-spec.json')]
        admit(gpus[0],bindings['minimum_free_gpu_mib']);started=time.monotonic()
        with(domain/'stdout.log').open('x')as log:process=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
        record=dict(dataset=dataset,returncode=process.returncode,seconds=time.monotonic()-started,status='execution_complete_pending_audit'if process.returncode==0 else'failed')
        missing=[]
        side='shadow'if hook_mode=='on'else'control'
        entries={tuple(entry['member']):entry for entry in plan['entries']}
        for chosen_row in chosen:
            entry=entries[tuple(chosen_row['identity'])]
            result_dir=run/'results'/entry['key']/side/attempt_id
            terminal=result_dir/'retention.json'
            if not terminal.exists() or json.loads(terminal.read_bytes())['summary'].get('status')!='completed':missing.append(entry['member'])
        if missing:record.update(status='failed',missing_or_incomplete_members=missing)
        (domain/'execution_result.json').write_text(json.dumps(record,indent=2));results.append(record)
        if process.returncode or missing:break
    return results
