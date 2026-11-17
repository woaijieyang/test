"""Stage A -> B -> Remaining on GPU4-7, retaining the baseline policy worker."""
import argparse,datetime,fcntl,hashlib,json,math,os,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from workspace import atomic_json,digest,read_json
from evaluate import source_identity,merge
from checkpoint_choice import scene_view,idle_gpus,pools
from preflight import load,task_key
from result_contract import aggregate,rows,finite_metrics,METRICS

DATA=Path('/data/zy/vln/data/checkpoint-choice/VLN-awareVLN')
SUITE=ROOT/'outputs/hamlet-abc-20261031-v2'
PREFIX='case2-hamlet-abc-20261031-v2'
PROFILE=ROOT/'data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json'
CPU=list(range(24,96))
STAGES={'A':['A1','A2','A3'],'B':['B1','B2','B3'],'Remaining':['Remaining']}
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def runpath(ds):return ROOT/'outputs'/f'{PREFIX}-{ds}'
def require_runtime():
    protection=json.loads(os.environ.get('CASE1_PROTECTION','{}'))
    if not protection.get('landlock_abi') or protection.get('prepare_configs') or protection.get('results_write'):raise RuntimeError('Protected non-administrative runtime required')
    if sorted(os.sched_getaffinity(0))!=CPU:raise RuntimeError('Expected CPU24-95 exactly')

def prepare():
    require_runtime()
    if SUITE.exists():raise RuntimeError('Existing suite; explicit recovery review required')
    SUITE.mkdir()
    material=read_json(DATA/'audit/materialization.json');success=read_json(DATA/'_SUCCESS')
    if digest(DATA/'audit/materialization.json')!=success['materialization_sha256'] or digest(DATA/'audit/content-manifest.json')!=success['content_manifest_sha256']:raise ValueError('Partition certificate drift')
    for rel,sha in read_json(DATA/'audit/content-manifest.json').items():
        p=DATA/rel
        if DATA not in p.resolve().parents or digest(p)!=sha:raise ValueError('Partition content drift '+rel)
    revision=read_json(ROOT/'outputs/resource-revision-20261031/validation.json');source_sha,sources=source_identity()
    if revision['status']!='PASS' or revision['source_sha256']!=source_sha:raise ValueError('Resource-only revision not validated')
    gate=read_json(ROOT/'outputs/gates/engineering.json')
    if gate['status']!='PASS' or gate['source_sha256']!=revision['previous_source_sha256']:raise ValueError('Prior full engineering gate not bound')
    for receipt in gate['receipts']:
        if digest(receipt['path'])!=receipt['sha256']:raise ValueError('Prior acceptance evidence changed')
    cpu=read_json(ROOT/'outputs/verification/cpu-resource72.json')
    if cpu['status']!='PASS' or cpu['source_sha256']!=source_sha:raise ValueError('Fresh resource CPU checks required')
    environment=read_json(ROOT/'outputs/setup/runtime-files.json');model=read_json(ROOT/'outputs/preflight/model.json')
    for item in environment['files']+model['files']:
        if digest(item['path'])!=item['sha256']:raise ValueError('Runtime/model drift')
    from hamlet_v2.policy import policy_identity
    policy=policy_identity(ROOT);profile=read_json(PROFILE);scene_root=scene_view(profile)
    bindings={}
    from vlnce_baselines.config.default import get_config
    from habitat import make_dataset
    for ds in ['r2r','rxr']:
        prior=read_json(ROOT/f'outputs/case2-hamlet-pilot-{ds}-v1/run_manifest.json')
        spec=material['effective_datasets'][ds]
        dataset={'annotation':spec['annotation'],'annotation_sha256':digest(spec['annotation']),'gt':spec['gt'],'gt_sha256':digest(spec['gt']),'auxiliary_inputs':[{'path':x['copied_path'],'sha256':x['sha256']} for x in spec['auxiliary_inputs']]}
        for key in ['annotation_sha256','gt_sha256']:
            if dataset[key]!=prior['datasets'][ds][key]:raise ValueError('Partition material changes accepted dataset')
        episodes=[e for e in load(dataset['annotation'])['episodes'] if ds=='r2r' or e['instruction']['language']=='en-US']
        expected=[{'task_key':task_key(ds,e),'dataset':ds} for e in episodes]
        ids={str(e['episode_id']) for e in episodes};leaves=material['leaves'][ds]
        if ids!=set(pools(leaves)['Full']) or len(ids)!=len(episodes):raise ValueError('Partition not a disjoint complete cohort')
        checks=[]
        for leaf,selection in leaves.items():
            config=get_config(str(ROOT/f'configs/vlnce_baselines/config/{ds}_baselines/awarevln.yaml'));config.defrost()
            d=config.TASK_CONFIG.DATASET;d.DATA_PATH=dataset['annotation'];d.EPISODES_ALLOWED=selection;d.NUM_CHUNKS=1;d.CHUNK_IDX=0;d.SCENES_DIR=str(scene_root);d.ROLES=['guide'];d.LANGUAGES=['en-US'] if ds=='rxr' else ['*'];config.freeze()
            actual=[str(e.episode_id) for e in make_dataset(d.TYPE,config=d).episodes]
            if len(actual)!=len(selection) or set(actual)!=set(selection):raise ValueError('Native leaf reader identity mismatch')
            checks.append({'leaf':leaf,'count':len(actual),'status':'PASS'})
        baseline=read_json(ROOT/f'outputs/comparison-sources/baseline-{ds}/run_manifest.json');base_profile=read_json(ROOT/f'outputs/comparison-sources/baseline-{ds}/profile.json')
        if {x['task_key'] for x in baseline['expected_tasks']}!={x['task_key'] for x in expected}:raise ValueError('Baseline full task identity mismatch')
        for key in ['annotation_sha256','gt_sha256']:
            if baseline['datasets'][ds][key]!=dataset[key]:raise ValueError('Baseline annotation/GT mismatch')
        if profile['agent']!=base_profile['agent'] or set(profile['assets'])!=set(base_profile['assets']):raise ValueError('Baseline mesh scope mismatch')
        for scene,asset in profile['assets'].items():
            for key in ['scene_sha256','navmesh_sha256']:
                if asset[key]!=base_profile['assets'][scene][key]:raise ValueError('Baseline mesh content mismatch')
        run=runpath(ds);run.mkdir(exist_ok=False)
        manifest={**prior,'run_id':run.name,'record_id':run.name,'created_at':now(),'scope':'full','claim_scope':'online_navigation','source_sha256':source_sha,'expected_tasks':expected,'datasets':{ds:dataset},'logical_chunks':1,'max_gpus':4,'allowed_gpu_ids':[4,5,6,7],'max_logical_cpus':72,'cpu_affinity':CPU,'policy_identity':policy,'jobs':[],'partition_source':str(DATA),'partition_materialization_sha256':digest(DATA/'audit/materialization.json'),'stage_order':list(STAGES),'resource_budget':{'gpu_ids':[4,5,6,7],'gpu_memory':'full available device memory; no inherited 24GiB allocator cap','cpu_ids':CPU,'per_worker_cpu_count':18},'benchmark_sha256':hashlib.sha256(json.dumps(expected,sort_keys=True).encode()).hexdigest(),'frozen_files':sources+model['files']+environment['files']+policy['files']}
        manifest['frozen_files'] += [{'path':dataset['annotation'],'sha256':dataset['annotation_sha256']},{'path':dataset['gt'],'sha256':dataset['gt_sha256']},{'path':str(PROFILE),'sha256':digest(PROFILE)},{'path':str(DATA/'audit/materialization.json'),'sha256':digest(DATA/'audit/materialization.json')},*dataset['auxiliary_inputs']]
        for asset in profile['assets'].values():
            manifest['frozen_files'] += [{'path':asset['scene_path'],'sha256':asset['scene_sha256']},{'path':asset['navmesh_path'],'sha256':asset['navmesh_sha256']}]
        # Freeze this scheduling implementation and comparison implementation separately too.
        manifest['frozen_files'] += [{'path':str(ROOT/'tools'/n),'sha256':digest(ROOT/'tools'/n)} for n in ['hamlet_abc.py','report_hamlet_abc.py']]
        index=0
        for stage,leafnames in STAGES.items():
            for leaf in leafnames:
                values=leaves[leaf];parts=[values] if leaf!='Remaining' else [values[i::4] for i in range(4)]
                for part in parts:
                    manifest['jobs'].append({'index':index,'stage':stage,'leaf':leaf,'ids':part});index+=1
        atomic_json(run/'dataset-spec.json',dataset);manifest['dataset_spec_sha256']=digest(run/'dataset-spec.json');atomic_json(run/'run_manifest.json',manifest)
        bindings[ds]={'native_reader':checks,'expected':len(expected),'baseline_protocol_match':True,'baseline_manifest_sha256':digest(ROOT/f'outputs/comparison-sources/baseline-{ds}/run_manifest.json'),'manifest_sha256':digest(run/'run_manifest.json')}
        atomic_json(run/'progress.json',{'status':'PREPARED','completed':0,'expected':len(expected)})
    atomic_json(SUITE/'launch-gate.json',{'status':'PASS','source_sha256':source_sha,'resource_revision':revision,'bindings':bindings,'phase_order':list(STAGES),'no_model_policy_changes':True})
    print(json.dumps({'status':'PREPARED','source_sha256':source_sha,'bindings':bindings}))

def audit_stage(stage,manifests):
    for ds,(run,m) in manifests.items():
        merged=merge(run);atomic_json(run/'summary.json',aggregate(m,merged))
        for script in ['audit_model_trace.py','recompute_metrics.py','audit_hamlet_flow.py']:
            with (SUITE/f'{stage}-{ds}-{script}.log').open('x') as stream:
                proc=subprocess.run([sys.executable,'-B',str(ROOT/'scripts'/script),'--run',str(run)],stdout=stream,stderr=subprocess.STDOUT,env={**os.environ,'CUDA_VISIBLE_DEVICES':''})
            if proc.returncode:raise RuntimeError('Stage audit failed: '+ds+'/'+script)
        done_stages=list(STAGES)[:list(STAGES).index(stage)+1]
        expected={i for j in m['jobs'] if j['stage'] in done_stages for i in j['ids']}
        if {row['task_key'].split('|')[-2] for row in merged}!=expected:raise ValueError('Stage coverage mismatch')
        independent={row['task_key']:row for row in read_json(run/'independent_metrics.json')['results']}
        for row in merged:
            finite_metrics(row);finite_metrics(independent[row['task_key']])
            if independent[row['task_key']]['trace_sha256']!=row['trace_sha256']:raise ValueError('Independent trace binding mismatch')
            for key in METRICS:
                if not math.isclose(row['metrics'][key],independent[row['task_key']]['metrics'][key],rel_tol=1e-6,abs_tol=1e-5):raise ValueError('Metric recomputation differs')
        atomic_json(SUITE/f'{stage}-{ds}-validation.json',{'status':'PASS','stage':stage,'completed_episodes':len(merged),'manifest_sha256':digest(run/'run_manifest.json'),'receipts':{n:digest(run/n) for n in ['results.jsonl','semantic_audit.json','independent_metrics.json','hamlet_dataflow_audit.json']}})
        atomic_json(SUITE/f'{stage}-{ds}-audited-results.json',{'stage':stage,'dataset':ds,'status':'PASS','manifest_sha256':digest(run/'run_manifest.json'),'results':merged,'memory_counts':read_json(run/'hamlet_dataflow_audit.json')['counts']})

def run_all():
    require_runtime();lock=(SUITE/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    manifests={ds:(runpath(ds),read_json(runpath(ds)/'run_manifest.json')) for ds in ['r2r','rxr']};source_sha,sources=source_identity();gate=read_json(SUITE/'launch-gate.json')
    if gate['status']!='PASS' or gate['source_sha256']!=source_sha:raise ValueError('Launch gate drift')
    for ds,(run,m) in manifests.items():
        if (run/'shards').exists():raise RuntimeError('Existing attempts; recovery must be reviewed')
        if m['source_sha256']!=source_sha or digest(run/'run_manifest.json')!=gate['bindings'][ds]['manifest_sha256']:raise ValueError('Manifest drift')
        for item in m['frozen_files']:
            if digest(item['path'])!=item['sha256']:raise ValueError('Frozen input drift '+item['path'])
    process={'pid':os.getpid(),'start_ticks':Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')',1)[1].split()[19],'cpu_affinity':CPU,'source_sha256':source_sha,'started_at':now()};atomic_json(SUITE/'controller-process.json',process)
    active={};completed_stages=[]
    try:
        for stage in STAGES:
            pending=[(ds,j) for ds,(run,m) in manifests.items() for j in m['jobs'] if j['stage']==stage];lastcheck=0
            while pending or active:
                if time.monotonic()-lastcheck>60:
                    if any(digest(x['path'])!=x['sha256'] for x in sources):raise RuntimeError('SOURCE_DRIFT')
                    lastcheck=time.monotonic()
                for gpu in idle_gpus():
                    if gpu in active or not pending:continue
                    ds,job=pending.pop(0);run,m=manifests[ds];shard=run/'shards'/f"shard-{job['index']:02}";shard.mkdir(parents=True,exist_ok=False)
                    ids=shard/'ids-1.json';atomic_json(ids,job['ids']);attempt=shard/'attempt-01';cpu=CPU[(gpu-4)*18:(gpu-3)*18]
                    env={**os.environ,'CUDA_VISIBLE_DEVICES':str(gpu),'CASE1_RUN_ROOT':str(run),'CASE1_SOURCE_SHA256':source_sha,'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
                    env.pop('CASE1_TORCH_BUDGET_MIB',None);env.pop('CASE1_GPU_TOTAL_BUDGET_MIB',None)
                    cmd=[sys.executable,'-B',str(ROOT/'scripts/evaluate_worker.py'),'--dataset',ds,'--output',str(attempt),'--scenes',str(scene_view(read_json(PROFILE))),'--chunk','0','--chunks','1','--ids',str(ids),'--dataset-spec',str(run/'dataset-spec.json')]
                    stream=(shard/'attempt-01.log').open('x');proc=subprocess.Popen(cmd,env=env,stdout=stream,stderr=subprocess.STDOUT,preexec_fn=lambda c=cpu:os.sched_setaffinity(0,c))
                    binding={'pid':proc.pid,'start_ticks':Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')',1)[1].split()[19],'gpu':gpu,'cpu_affinity':cpu,'stage':stage,'leaf':job['leaf'],'command':cmd,'manifest_sha256':digest(run/'run_manifest.json')};atomic_json(shard/'process-1.json',binding);active[gpu]=(proc,stream,ds,job)
                errors=[]
                for gpu,(proc,stream,ds,job) in list(active.items()):
                    if proc.poll() is not None:
                        stream.close()
                        if proc.returncode:errors.append({'dataset':ds,'job':job,'returncode':proc.returncode})
                        del active[gpu]
                counts={}
                for ds,(run,m) in manifests.items():
                    merged=merge(run);counts[ds]={'completed':len(merged),'expected':len(m['expected_tasks'])};atomic_json(run/'progress.json',{**counts[ds],'stage':stage,'active':sum(x[2]==ds for x in active.values()),'pending':sum(x[0]==ds for x in pending),'failed':errors})
                atomic_json(SUITE/'state.json',{'status':'RUNNING','stage':stage,'completed_stages':completed_stages,'datasets':counts,'active':{g:{'pid':x[0].pid,'dataset':x[2],'leaf':x[3]['leaf']} for g,x in active.items()},'pending':len(pending),'at':now(),'source_sha256':source_sha})
                if errors:raise RuntimeError(json.dumps(errors))
                if pending or active:time.sleep(10)
            atomic_json(SUITE/'state.json',{'status':'AUDITING_STAGE','stage':stage,'completed_stages':completed_stages,'at':now()})
            audit_stage(stage,manifests);completed_stages.append(stage)
            atomic_json(SUITE/'state.json',{'status':'STAGE_AUDITED','stage':stage,'completed_stages':completed_stages,'at':now()})
            # This protected controller cannot write reports: a separate narrow report process does so.
        for ds,(run,m) in manifests.items():
            with (SUITE/f'{ds}-formal-validation.log').open('x') as stream:subprocess.run([sys.executable,'-B',str(ROOT/'scripts/validate_results.py'),'--run',str(run)],stdout=stream,stderr=subprocess.STDOUT,check=True)
        atomic_json(SUITE/'state.json',{'status':'FULL_AUDITED_COMPLETE','completed_stages':completed_stages,'at':now(),'source_sha256':source_sha})
    except Exception as exc:
        # Keep completed and interrupted evidence. Terminate only owned active children.
        for proc,stream,ds,job in active.values():
            if proc.poll() is None:proc.terminate()
        atomic_json(SUITE/'state.json',{'status':'FAILED_REQUIRES_REVIEW','completed_stages':completed_stages,'error':str(exc),'at':now(),'source_sha256':source_sha});raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','run']);a=p.parse_args()
    prepare() if a.command=='prepare' else run_all()
