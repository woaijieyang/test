"""Fixed-denominator paired diagnostics for stage002 supplementary evidence experiments."""
import gzip,hashlib,json,os
from pathlib import Path
from collections import Counter
from .retrieval_behavior import summarize,compare_decision_modes,audit_reasoning_requests
from .additive_material_audit import audit
from .paired_prefix import compare_paired_prefix

def load(p):return json.loads(p.read_bytes())
def trace_rows(p):
    with gzip.open(p,'rt') as stream:return [json.loads(line) for line in stream]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def verify_runtime_side(side, manifest, hook):
    """Check what the worker actually started, separately from the declared side."""
    mode = {"control":"off", "shadow":"on"}.get(side)
    if (mode is None or manifest.get("method")!="baseline" or manifest.get("hook_mode",mode)!=mode
            or hook.get("completed") is not True or hook.get("requested_mode")!=mode):
        raise ValueError("Navigation method, requested hook mode or completion disagrees")
    enabled=side=="shadow"
    for key in ("profile_requested","hook_enabled","memory_broker_supplied","memory_worker_started"):
        if hook.get(key) is not enabled:raise ValueError("Runtime hook receipt differs: "+key)
    if hook.get("broker_supplied") is not False or hook.get("native_initialization_attempts")!=0:
        raise ValueError("Unexpected native pose broker or initialization")
    counters=[hook.get(key) for key in ("reset_attempts","packet_count","memory_packet_count")]
    if any(type(x)is not int or x<0 for x in counters):
        raise ValueError("Incomplete hook execution counters")
    resets,packets,mapped=counters
    if enabled:
        if (not resets or not packets or mapped!=packets or hook.get("provider_initialization_attempts")!=resets
                or hook.get("pose_provider")!="simulator_ground_truth" or not hook.get("hook_class")):
            raise ValueError("Simulator pose or mapping execution receipt disagrees")
        if manifest.get("stage")=="002" and (manifest.get("sidecar_feature")!="graph_memory"
                or manifest.get("pose_condition")!="simulator_pose_diagnostic"):
            raise ValueError("Stage002 not bound to simulator pose and graph memory")
    elif (any(counters) or hook.get("provider_initialization_attempts",0)!=0 or hook.get("hook_class") is not None
          or manifest.get("sidecar_feature","disabled")!="disabled"):
        raise ValueError("Control executed a sidecar")


def bind(d,member,side):
    doc=load(d/'retention.json')
    ident=doc['identity']
    if ident['member']!=member or ident['side']!=side or ident['attempt']!='attempt0' or doc['summary']['status']!='completed':
        raise ValueError('Wrong member, side, attempt or incomplete retained trace')
    actual_plan=d.resolve().parents[3]/'retention_plan.json'
    if ident['key']!=d.parents[1].name or sha(actual_plan)!=ident['plan_sha256']:
        raise ValueError('Retention identity differs from its sealed plan')
    if doc['trace_audit']['errors'] or sha(d/'trace.jsonl.gz')!=doc['trace']['sha256']:
        raise ValueError('Unverified or modified trace')
    paths=[Path(v['path']).parents[1] for v in load(d/'routes.json')['scopes'] if v['role']=='host']
    if len(paths)!=1 or not paths[0].resolve().is_relative_to(d.resolve().parents[3]):
        raise ValueError('Ambiguous/out-of-run host receipt')
    worker=paths[0];domain=worker.parent;model=load(worker/'model-receipt.json')
    cfg=worker/'effective-config.yaml'
    if sha(cfg)!=doc['summary']['effective_config_sha256']:raise ValueError('Host effective config differs from retained record')
    # YACS stringifies Python tuples; preserve exact values as text, including indentation.
    normalized=[]
    for line in cfg.read_text().splitlines():
        stripped=line.strip()
        if stripped.startswith('EPISODES_ALLOWED:'):continue
        if stripped.startswith('DATA_PATH:') and 'outputs/graph_memory/' in stripped:
            normalized.append(line[:line.index('DATA_PATH:')]+'DATA_PATH: $REGISTERED_EPISODE');continue
        normalized.append(line.replace(str(domain.resolve())+'/','$DOMAIN/'))
    spec_path=domain/'dataset-spec.json';manifest=load(domain/'run_manifest.json')
    if manifest['dataset_spec_sha256']!=sha(spec_path):raise ValueError('Dataset specification drift')
    launch=load(worker/'launch-binding.json')
    if (launch.get('manifest_sha256')!=sha(domain/'run_manifest.json')
            or launch.get('dataset_spec_sha256')!=manifest['dataset_spec_sha256']
            or model.get('source_sha256')!=manifest.get('source_sha256')):
        raise ValueError('Worker launch or model receipt differs from run manifest')
    plan_stage=load(actual_plan).get('stage')
    if plan_stage not in ('001','002') or manifest.get('stage')!=plan_stage:
        raise ValueError('Host stage differs from retained run plan')
    if not manifest.get('source_sha256'):
        raise ValueError('Missing host source identity')
    verify_runtime_side(side,manifest,load(worker/'hook-load.json'))
    if side=='shadow' and manifest.get('stage')=='002':
        profile=d.resolve().parents[3]/'control/effective-profile.json'
        settings=load(profile)
        if (settings.get('stage')!=plan_stage
                or settings['map_memory']['retrieval']['mode']!=manifest.get('policy_input_mode')):
            raise ValueError('Executed memory input mode differs from run profile')
        if sha(profile)!=manifest.get('profile_sha256'):
            raise ValueError('Reported retrieval profile differs from executed profile')
    spec=load(spec_path);annotation=Path(spec['annotation'])
    if sha(annotation)!=spec['annotation_sha256']:raise ValueError('Annotation shard drift')
    with gzip.open(annotation,'rt')as f:episodes=json.load(f)['episodes']
    records=[e for e in episodes if str(e['episode_id'])==member[2] and e['scene_id']==member[1]
             and str(e['instruction'].get('instruction_id','-'))==member[3]]
    if len(records)!=1:raise ValueError('Ambiguous or missing exact annotation member')
    required=('checkpoint','python','torch','transformers','model_class','mode_token_ids','tokenizer_size','tokenizer_source','llm_source','dtype','num_video_frames')
    return dict(model={k:model[k]for k in required},scene=manifest['scene_assets']['assets'][member[1]],
        config=normalized,annotation=records[0],gt=spec['gt_sha256'])

def domain_summary(entries):
    n=len(entries);valid=[p for p in entries if p['status']=='verified']
    result=dict(registered=n,verified=len(valid),missing_or_invalid=n-len(valid),paired_delta_sr=None,
                candidate_success_lower_bound=sum(x['metrics']['success'][1]for x in valid)/n,
                original_success_lower_bound=sum(x['metrics']['success'][0]for x in valid)/n)
    if len(valid)==n:
        differences=[p['metrics']['success'][1]-p['metrics']['success'][0] for p in valid]
        result.update(paired_delta_sr=sum(differences)/n,win=sum(d>0 for d in differences),
            loss=sum(d<0 for d in differences),tie=differences.count(0))
    return result

def report(run,control,out):
    run=Path(run).resolve();control=Path(control).resolve()
    if not control.is_dir() or not run.is_dir():raise ValueError('Explicit run and control directories required')
    plan=load(run/'retention_plan.json'); entries=plan['entries']
    if not __debug__:raise RuntimeError('Input-audit assertions require standard Python execution')
    for entry in entries:
        member=entry['member']
        if len(member)!=4 or hashlib.sha256(json.dumps(member,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=entry['key']:
            raise ValueError('Plan member/key mismatch')
    if plan.get('stage')!='002' or not entries or len({e['key']for e in entries})!=len(entries):raise ValueError('Invalid002 cohort')
    profile=load(run/'control/effective-profile.json')
    mode,policy=profile.get('mode'),profile['map_memory']['retrieval'].get('evidence_policy','ranked')
    native_control=mode in ('uniform_original','uniform_tagged') and policy=='ranked'
    if not native_control and (mode,policy) not in {('native_plus_attachment','evo_topology'),('facts_only','additive_text'),('native_plus_attachment','dynamic_evo_context'),('facts_only','historical_approach'),('native_plus_attachment','historical_approach')}:
        raise ValueError('Unsupported paired retrieval report profile')
    dynamic=policy=='dynamic_evo_context'
    registry_path=control/'control/REUSED_CONTROLS.json'
    registry=load(registry_path)if registry_path.exists()else {}
    root=Path(__file__).resolve().parents[3]
    vocab=list(dict.fromkeys(x.strip()for x in (root/'vendor_sources/EvoMemNav/data/scannet200_classes.txt').read_text().splitlines()if x.strip()and x.strip()!='unknown'))
    results=[]
    for e in entries:
        row=dict(member=e['member'],key=e['key'],status='incomplete');results.append(row)
        try:
            cand=run/'results'/e['key']/'shadow/attempt0';base=control/'results'/e['key']/'control/attempt0'
            if not base.is_dir():
                receipt=registry[e['key']];base=Path(receipt['result']).resolve()
                if not base.is_relative_to(root/'outputs/graph_memory') or receipt['member']!=e['member'] or sha(base/'retention.json')!=receipt['retention_sha256']:
                    raise ValueError('Invalid reused control evidence')
            left=bind(base,e['member'],'control');right=bind(cand,e['member'],'shadow')
            for k in left:
                if left[k]!=right[k]:raise ValueError('Control/candidate identity mismatch: '+k)
            if native_control:
                from .native_control_audit import audit_native_control
                native_checks=audit_native_control(cand,base,mode)
            elif policy=='evo_topology':
                from .evo_material_audit import audit_evo
                checks=audit_evo(cand,right['annotation']['instruction']['instruction_text'])
            elif dynamic:
                from .dynamic_material_audit import audit_episode
                checks=audit_episode(cand,e,instruction=right['annotation']['instruction']['instruction_text'])
            elif policy=='historical_approach':
                from .approach_material_audit import audit_approach
                checks=audit_approach(cand,base)
            else:
                evidence=audit(cand,base,vocab)
            original,candidate=[trace_rows(p/'trace.jsonl.gz')for p in (base,cand)]
            behavior=[summarize(original),summarize(candidate)]
            flow=trace_rows(cand/'flow.jsonl.gz')
            intervals=[(v['ended_monotonic_ns']-v['started_monotonic_ns'])/1e9 for v in flow if v['kind']=='HostModelInterval']
            counts=[sum(len(x['input_ids'][0])for x in trace if x['kind']=='model_input')for trace in (original,candidate)]
            if native_control:
                metrics={k:[tr[-1]['native_metrics'][k] for tr in (original,candidate)]
                         for k in ('success','spl','ndtw','distance_to_goal','path_length','steps_taken')}
                input_audit=native_checks
            elif policy=='evo_topology':
                metrics={k:[t[-1]['native_metrics'][k] for t in (original,candidate)] for k in
                         ('success','spl','ndtw','distance_to_goal','path_length','steps_taken')}
                input_audit=checks
            elif dynamic:
                keys=('success','spl','ndtw','distance_to_goal','path_length','steps_taken')
                metrics={k:[tr[-1]['native_metrics'][k]for tr in (original,candidate)]for k in keys}
                input_audit=dict(calls=checks['calls'],native_slots_verified=checks.get('native_slots',0),
                    injected=checks.get('readbacks',0),path_records=checks.get('path_records',0),
                    attachments=checks.get('attachments',0),verified_distances=checks.get('photos_distance_and_labels',0),
                    verified_object_centers=checks.get('object_centers_verified',0),
                    native_object_matches=checks.get('native_object_matches',0),retained_object_reads=checks.get('retained_object_reads',0),
                    fallbacks=dict(Counter(checks['fallbacks'].values())))
            elif policy=='historical_approach':
                metrics=checks['metrics']
                input_audit=dict(calls=checks['calls'][1],native_slots_verified=checks['raw_native_slots'],
                    injections=checks['injections'],reads=checks['reads'],fallbacks=checks['fallback_reasons'],
                    retained_approach_reads=checks['retained_approach_reads'],
                    first_output_difference=checks['first_output_difference'],first_action_difference=checks['first_action_difference'])
            else:
                metrics=evidence['metrics']
                input_audit={k:evidence[k] for k in ('calls','native_slots_verified','injected','facts_verified','oldest_evidence_steps','fallbacks','first_output_difference')}
            from .read_latency import audit_read_latency
            input_audit['read_latency']=audit_read_latency(flow)
            from .reasoning_chain import audit_material_chains
            input_audit['material_to_execution']=audit_material_chains(candidate,flow)
            input_audit['reasoning_binding']=audit_reasoning_requests(candidate,flow)
            input_audit['paired_prefix']=compare_paired_prefix(original,candidate,flow)
            if mode=='uniform_original':
                actions=[[v['action'] for v in trace if v['kind']=='primitive_action'] for trace in (original,candidate)]
                equal=(native_checks['original_outputs_equal'] and actions[0]==actions[1]
                       and original[-1]['stop_source']==candidate[-1]['stop_source']
                       and original[-1]['native_metrics']==candidate[-1]['native_metrics'])
                native_checks['closed_loop_equal']=equal
                if not equal:
                    row['input_audit']=native_checks
                    raise ValueError('Uniform original failed closed-loop parity with hook-off')
            row.update(status='verified',control_result=str(base),candidate_result=str(cand),metrics=metrics,input_audit=input_audit,
                behavior=dict(original=behavior[0],candidate=behavior[1],
                              paired_modes=compare_decision_modes(original,candidate)),cost=dict(prompt_ids_total=counts,model_calls=[b['model_calls']for b in behavior],
                    candidate_generation_decode_seconds=sum(intervals) if len(intervals)==behavior[1]['model_calls'] else None,
                    paired_latency_delta_seconds=None,latency_scope='Equivalent per-call timing unavailable on retained hook-off control'))
        except (OSError,ValueError,KeyError,AssertionError,IndexError,TypeError)as error:
            row.update(error_type=type(error).__name__,error=str(error) or 'Input evidence invariant failed')
    groups={ds:domain_summary([r for r in results if r['member'][0]==ds])for ds in sorted({e['member'][0]for e in entries})}
    ok=all(x['status']=='verified' for x in results)
    result=dict(status='VERIFIED_PAIRED_DIAGNOSTIC' if ok else 'INCOMPLETE_PAIRED_DIAGNOSTIC',fixed_denominator=len(entries),domains=groups,episodes=results,
        profile=mode if native_control else policy,scope='Small registered development cohort. Descriptive paired metrics; no effect promotion or source-generalization claim.')
    target=Path(out).resolve()if out else run/'control/paired-retrieval.json'
    if not target.is_relative_to(root/'outputs/graph_memory') or target.exists():raise ValueError('Fresh graph-memory report path required')
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x')as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(dict(status=result['status'],out=str(target),domains=groups)))
    return ok

