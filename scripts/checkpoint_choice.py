"""Fixed VLN leaf-cohort evaluation; original model policy and metrics are unchanged."""
import argparse,datetime,fcntl,hashlib,json,os,subprocess,time,signal
from pathlib import Path
from workspace import ROOT,atomic_json,digest,owned,read_json
from preflight import load,task_key
from result_contract import aggregate,rows
from evaluate import source_identity,merge

DATA=Path('/data/zy/vln/data/checkpoint-choice/VLN-awareVLN')
RUN_PREFIX='awarevln-checkpoint-choice-endpoint9-20261024-shared24-v1'
LEAVES=('A1','A2','A3','B1','B2','B3','Remaining')

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()

def scene_view(profile):
    # Mount namespaces may resolve the same profile to a different read-only alias.
    # Separate namespaces by effective target paths; never replace historical links.
    links=[]
    for scene,a in profile['assets'].items():
        for relative,path,sha in [(scene,a['scene_path'],a['scene_sha256']),(str(Path(scene).with_suffix('.navmesh')),a['navmesh_path'],a['navmesh_sha256'])]:
            source=Path(path).resolve()
            if digest(source)!=sha:raise ValueError('Scene asset drift')
            links.append({'relative':relative,'source':str(source),'sha256':sha})
    key=hashlib.sha256(json.dumps(links,sort_keys=True).encode()).hexdigest()[:24]
    view=owned(ROOT/'data/derived/checkpoint-choice-scenes'/key);view.mkdir(parents=True,exist_ok=True)
    for row in links:
        p=view/row['relative'];p.parent.mkdir(parents=True,exist_ok=True)
        if p.is_symlink():
            if p.resolve()!=Path(row['source']):raise ValueError('Existing scene alias collision')
        elif p.exists():raise ValueError('Existing nonlink scene entry')
        else:p.symlink_to(row['source'])
    return view

def pools(leaves):
    result={k:list(leaves[k]) for k in LEAVES}
    for name,parts in [('A1+A2',('A1','A2')),('A',('A1','A2','A3')),('B1+B2',('B1','B2')),('B',('B1','B2','B3')),('Full',LEAVES)]:
        values=[v for k in parts for v in leaves[k]]
        if len(values)!=len(set(values)):raise ValueError('Overlapping leaf identity')
        result[name]=values
    return result

def summarize(manifest,results,leaves):
    expected={r['task_key'].split('|')[-2]:r for r in manifest['expected_tasks']}
    if len(expected)!=len(manifest['expected_tasks']):raise ValueError('Ambiguous episode IDs')
    if set(expected)!=set(pools(leaves)['Full']):raise ValueError('Full cohort mismatch')
    if len({r['task_key'] for r in results})!=len(results):raise ValueError('Duplicate result')
    if any(r['task_key'] not in {x['task_key'] for x in expected.values()} for r in results):raise ValueError('Unexpected result')
    output={}
    for label,ids in pools(leaves).items():
        keys={expected[e]['task_key'] for e in ids}
        m={**manifest,'expected_tasks':[expected[e] for e in ids]}
        output[label]=aggregate(m,[r for r in results if r['task_key'] in keys])
    return output

def idle_gpus():
    listing=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
    active=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],text=True)
    found=[]
    for line in listing.splitlines():
        index,uuid,mem,util=[v.strip() for v in line.split(',')]
        if int(index) in (4,5,6,7) and uuid not in active and int(mem)<1024 and int(util)<10:found.append(int(index))
    return found

def shared_gpus():
    # Explicit 2026-10-24 authorization; external jobs are allowed and never controlled.
    listing=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.total,memory.used','--format=csv,noheader,nounits'],text=True)
    return [int(parts[0]) for line in listing.splitlines() if len(parts:=[v.strip() for v in line.split(',')])==3 and int(parts[0]) in (4,5,6,7) and int(parts[1])-int(parts[2])>=24576+2048]

def owned_gpu_memory(pid):
    import psutil
    process=psutil.Process(pid)
    family={pid}|{p.pid for p in process.children(recursive=True)}
    data=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_memory','--format=csv,noheader,nounits'],text=True)
    total=0
    for line in data.splitlines():
        parts=[v.strip() for v in line.split(',')]
        if len(parts)==2 and parts[0].isdigit() and int(parts[0]) in family and parts[1].isdigit():total+=int(parts[1])
    return total

def require_protection():
    p=json.loads(os.environ.get('CASE1_PROTECTION','{}'))
    if not p.get('landlock_abi') or p.get('results_write') or p.get('prepare_configs'):raise RuntimeError('Protected non-administrative runtime required')

def prepare():
    require_protection()
    success=read_json(DATA/'_SUCCESS');material=read_json(DATA/'audit/materialization.json')
    assert digest(DATA/'audit/materialization.json')==success['materialization_sha256']
    assert digest(DATA/'audit/content-manifest.json')==success['content_manifest_sha256']
    for rel,sha in read_json(DATA/'audit/content-manifest.json').items():
        p=DATA/rel
        if DATA not in p.resolve().parents or digest(p)!=sha:raise ValueError('Copied dataset identity changed '+rel)
    source_sha,sources=source_identity()
    env=read_json(ROOT/'outputs/setup/runtime-files.json');model=read_json(ROOT/'outputs/preflight/model.json')
    # All model/environment files are checked once before launch and again bound per task.
    for f in env['files']+model['files']:
        if digest(f['path'])!=f['sha256']:raise ValueError('Environment/model drift '+f['path'])
    profile=ROOT/material['annotation_protocol']['mesh_profile']
    assert digest(profile)==material['profile_sha256']
    scenes=scene_view(read_json(profile))
    for ds in ('r2r','rxr'):
        old=read_json(ROOT/f'outputs/awarevln-{ds}-valunseen-endpoint9-20261015-v2/run_manifest.json')
        # Retain policy, base config, model and native mesh; the new controller/reporting identity is separate.
        invariant=[]
        for f in old['frozen_files']:
            p=Path(f['path']);rel=p.relative_to(ROOT) if p.is_relative_to(ROOT) else None
            if rel and (rel.parts[0]=='src' or str(rel) in ('scripts/preflight.py',f'configs/vlnce_baselines/config/{ds}_baselines/awarevln.yaml')):
                if digest(p)!=f['sha256']:raise ValueError('Published baseline policy changed '+str(p))
                invariant.append(f)
        assert model['model_sha256']==old['model_sha256'] and digest(profile)==old['navmesh_sha256']
        spec=material['effective_datasets'][ds]
        dataset={'annotation':spec['annotation'],'annotation_sha256':digest(spec['annotation']),'gt':spec['gt'],'gt_sha256':digest(spec['gt']),'auxiliary_inputs':[{'path':x['copied_path'],'sha256':x['sha256']} for x in spec['auxiliary_inputs']]}
        assert dataset['annotation_sha256']==old['datasets'][ds]['annotation_sha256'] and dataset['gt_sha256']==old['datasets'][ds]['gt_sha256']
        episodes=[e for e in load(dataset['annotation'])['episodes'] if ds=='r2r' or e['instruction']['language']=='en-US']
        expected=[{'task_key':task_key(ds,e),'dataset':ds} for e in episodes]
        assert {x['task_key'] for x in expected}=={x['task_key'] for x in old['expected_tasks']}
        run=owned(ROOT/'outputs'/f'{RUN_PREFIX}-{ds}');run.mkdir(exist_ok=False)
        native=[]
        from vlnce_baselines.config.default import get_config
        from habitat import make_dataset
        for leaf,ids in material['leaves'][ds].items():
            c=get_config(str(ROOT/f'configs/vlnce_baselines/config/{ds}_baselines/awarevln.yaml'))
            c.defrost();c.TASK_CONFIG.DATASET.DATA_PATH=dataset['annotation'];c.TASK_CONFIG.DATASET.EPISODES_ALLOWED=ids
            c.TASK_CONFIG.DATASET.NUM_CHUNKS=1;c.TASK_CONFIG.DATASET.CHUNK_IDX=0;c.TASK_CONFIG.DATASET.SCENES_DIR=str(scenes)
            c.TASK_CONFIG.DATASET.ROLES=['guide'];c.TASK_CONFIG.DATASET.LANGUAGES=['en-US'] if ds=='rxr' else ['*'];c.freeze()
            loaded=make_dataset(c.TASK_CONFIG.DATASET.TYPE,config=c.TASK_CONFIG.DATASET)
            actual=[str(e.episode_id) for e in loaded.episodes]
            assert len(actual)==len(ids) and set(actual)==set(ids),(ds,leaf,len(actual),len(ids))
            native.append({'leaf':leaf,'expected':len(ids),'actual':len(actual),'identity_matches':True})
        manifest={**old,'run_id':run.name,'record_id':run.name,'created_at':now(),'source_sha256':source_sha,'expected_tasks':expected,'datasets':{ds:dataset},'allowed_gpu_ids':[4,5,6,7],'max_gpus':4,'max_logical_cpus':64,'logical_chunks':1,'resource_budget':{'mode':'user_authorized_shared_capacity','gpu_ids':[4,5,6,7],'per_gpu_total_budget_mib':24576,'pytorch_allocator_cap_mib':22528,'non_torch_reserve_mib':2048,'launch_free_headroom_mib':2048,'watchdog_interval_seconds':5,'authorization':'2026-10-24 human: GPU4-7 each about24GB, start progressing'},'jobs':[{'leaf':k,'ids':v} for k,v in material['leaves'][ds].items()],'partition_source':str(DATA),'partition_materialization_sha256':digest(DATA/'audit/materialization.json'),'baseline_run':old['run_id'],'baseline_policy_files':invariant,'baseline_limitations':'Endpoint9 protocol retained, R2R prior offmesh/retracted limitation not resolved by this rerun; no claim of full source geometry or independent tensor validation.','effective_config_change':'Explicit copied annotation/GT paths and exact selected IDs; NUM_CHUNKS=1; per-leaf fresh process. Original model policy/action/budget preserved.','environment_sha256':env['environment_sha256'],'frozen_files':sources+model['files']+env['files']+[{'path':str(profile),'sha256':digest(profile)},{'path':str(DATA/'audit/materialization.json'),'sha256':digest(DATA/'audit/materialization.json')},{'path':dataset['annotation'],'sha256':dataset['annotation_sha256']},{'path':dataset['gt'],'sha256':dataset['gt_sha256']}]+dataset['auxiliary_inputs']}
        manifest.pop('resource_policy',None)
        for a in read_json(profile)['assets'].values():
            manifest['frozen_files'] += [{'path':a['scene_path'],'sha256':a['scene_sha256']},{'path':a['navmesh_path'],'sha256':a['navmesh_sha256']}]
        atomic_json(run/'dataset-spec.json',dataset);manifest['dataset_spec_sha256']=digest(run/'dataset-spec.json')
        atomic_json(run/'run_manifest.json',manifest)
        atomic_json(run/'launch-gate.json',{'status':'PASS_BASELINE_EQUIVALENCE_AND_EXACT_PARTITION','scope':'Published endpoint9 rerun, not strict geometry reacceptance','native_reader':native,'manifest_sha256':digest(run/'run_manifest.json'),'known_limitations':manifest['baseline_limitations']})
        atomic_json(run/'progress.json',{'status':'PREPARED_NOT_STARTED','completed':0,'expected':len(expected)})
    print('Both complete scopes prepared; native 14-leaf reader verified; model not started.')

def run_all():
    require_protection()
    base=owned(ROOT/'outputs/checkpoint-choice-20261024-shared24-v1');base.mkdir(exist_ok=True)
    lock=(base/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    stat=Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')',1)[1].split()
    atomic_json(base/'controller-process.json',{'pid':os.getpid(),'start_ticks':stat[19],'command':'scripts/checkpoint_choice.py run','started_at':now()})
    manifests={};pending=[];active={};failures=[];source_sha,sources=source_identity()
    for ds in ('r2r','rxr'):
        run=ROOT/'outputs'/f'{RUN_PREFIX}-{ds}';m=read_json(run/'run_manifest.json');manifests[ds]=(run,m)
        assert m['source_sha256']==source_sha
        assert read_json(run/'launch-gate.json')['manifest_sha256']==digest(run/'run_manifest.json')
        assert digest(run/'dataset-spec.json')==m['dataset_spec_sha256']
        if (run/'shards').exists():raise RuntimeError('Existing attempts require explicit recovery review; do not rerun')
        for i,job in enumerate(m['jobs']):pending.append((ds,i,job))
    atomic_json(base/'source-freeze.json',{'status':'OPEN','source_sha256':source_sha,'pid':os.getpid(),'start_ticks':stat[19]})
    allowed=sorted(os.sched_getaffinity(0))[:64]
    last_source_check=0
    resource_observed={}
    while pending or active:
        # Stop dispatch on source drift; already running workers finish under their frozen identity.
        if time.monotonic()-last_source_check>=60:
            if any(digest(x['path'])!=x['sha256'] for x in sources):failures.append({'kind':'SOURCE_DRIFT'});pending=[]
            last_source_check=time.monotonic()
        for gpu in shared_gpus() if not failures else []:
            if gpu in active or not pending:continue
            ds,i,job=pending.pop(0);run,m=manifests[ds]
            shard=run/'shards'/f'shard-{i:02}';shard.mkdir(parents=True,exist_ok=False)
            ids=shard/'ids-1.json';atomic_json(ids,job['ids']);out=shard/'attempt-01'
            command=[str(ROOT/'runtime/awarevln/bin/python'),'-B',str(ROOT/'scripts/evaluate_worker.py'),'--dataset',ds,'--output',str(out),'--scenes',str(scene_view(read_json(m['navmesh_profile']))),'--chunk','0','--chunks','1','--ids',str(ids),'--dataset-spec',str(run/'dataset-spec.json')]
            env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(gpu),CASE1_RUN_ROOT=str(run),CASE1_SOURCE_SHA256=source_sha,OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',CASE1_GPU_TOTAL_BUDGET_MIB='24576',CASE1_TORCH_BUDGET_MIB='22528')
            log=(shard/'attempt-01.log').open('x')
            cpu=allowed[((gpu-4)*16):((gpu-3)*16)] or allowed[:1]
            p=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=lambda c=cpu:os.sched_setaffinity(0,c))
            binding={'pid':p.pid,'start_ticks':Path(f'/proc/{p.pid}/stat').read_text().rsplit(')',1)[1].split()[19],'gpu':gpu,'cpu_affinity':cpu,'leaf':job['leaf'],'command':command,'worker_sha256':digest(ROOT/'scripts/evaluate_worker.py'),'manifest_sha256':digest(run/'run_manifest.json')}
            atomic_json(shard/'process-1.json',binding);active[gpu]=(p,log,ds,job['leaf'])
        for gpu,(p,log,ds,leaf) in list(active.items()):
            if p.poll() is None:
                used=owned_gpu_memory(p.pid)
                resource_observed[gpu]={'pid':p.pid,'own_process_tree_gpu_mib':used,'peak_mib':max(used,resource_observed.get(gpu,{}).get('peak_mib',0))}
                if used>24576:
                    failures.append({'kind':'OWN_GPU_BUDGET_EXCEEDED','gpu':gpu,'pid':p.pid,'used_mib':used})
                    if os.getpgid(p.pid)!=p.pid:raise RuntimeError('Owned process group mismatch')
                    os.killpg(p.pid,signal.SIGTERM)
                    try:p.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(p.pid,signal.SIGKILL);p.wait()
            if p.poll() is not None:
                log.close()
                if p.returncode:failures.append({'dataset':ds,'leaf':leaf,'returncode':p.returncode})
                del active[gpu]
        counts={}
        for ds,(run,m) in manifests.items():
            merged=merge(run);counts[ds]={'completed':len(merged),'expected':len(m['expected_tasks'])}
            atomic_json(run/'progress.json',{**counts[ds],'status':'FAILED' if failures else 'RUNNING','active':sum(x[2]==ds for x in active.values()),'pending':sum(x[0]==ds for x in pending),'failed':failures})
        atomic_json(base/'state.json',{'status':'FAILED' if failures else 'RUNNING' if active else 'WAITING_FOR_SHARED_24GIB_CAPACITY','at':now(),'datasets':counts,'active':{g:{'pid':v[0].pid,'dataset':v[2],'leaf':v[3]} for g,v in active.items()},'pending':len(pending),'failures':failures,'resource_observed':resource_observed})
        if failures and not active:break
        if pending or active:time.sleep(5)
    if not failures:
        for ds,(run,m) in manifests.items():
            atomic_json(run/'summary.json',aggregate(m,merge(run)))
            for script in ['audit_model_trace.py','recompute_metrics.py','validate_results.py']:
                log=base/f'{ds}-{script}.log'
                with log.open('x') as f:r=subprocess.run([str(ROOT/'runtime/awarevln/bin/python'),'-B',str(ROOT/'scripts'/script),'--run',str(run)],stdout=f,stderr=subprocess.STDOUT)
                if r.returncode:failures.append({'dataset':ds,'audit':script,'returncode':r.returncode});break
            if failures:break
    atomic_json(base/'source-freeze.json',{'status':'CLOSED','source_sha256':source_sha,'ended_at':now(),'failures':failures})
    atomic_json(base/'state.json',{'status':'AUDITED_COMPLETE_PENDING_REGISTRATION' if not failures else 'FAILED_REQUIRES_REVIEW','at':now(),'failures':failures})
    if failures:raise SystemExit(1)

def report(historical=False):
    if not json.loads(os.environ.get('CASE1_PROTECTION','{}')).get('results_write'):raise RuntimeError('Use --results-write')
    material=read_json(DATA/'audit/materialization.json');dest=ROOT/'results-show'
    index=read_json(dest/'records.json');by_run={r['run_id']:r for r in index['records']}
    result=[]
    for ds in ('r2r','rxr'):
        rid=f'awarevln-{ds}-valunseen-endpoint9-20261015-v2' if historical else f'{RUN_PREFIX}-{ds}'
        run=ROOT/'outputs'/rid;m=read_json(run/'run_manifest.json');rs=rows(run/'results.jsonl');validation=read_json(run/'validation.json')
        assert validation['status']=='PASS'
        for file,sha in validation['receipts'].items():assert digest(run/file)==sha,(rid,file)
        s=summarize(m,rs,material['leaves'][ds]);assert all(v['complete'] for v in s.values())
        result.append({'dataset':ds,'run_id':rid,'status':by_run.get(rid,{}).get('status','audited'), 'origin':'historical_reaggregation_not_new_inference' if historical else 'fresh_model_evaluation','manifest_sha256':digest(run/'run_manifest.json'),'source_sha256':m['source_sha256'],'model_sha256':m['model_sha256'],'profile_sha256':m['navmesh_sha256'],'partition_sha256':digest(DATA/'audit/materialization.json'),'subsets':s})
    if not historical:
        # Paired deltas are emitted only after every task and evaluation identity matches.
        for current in result:
            ds=current['dataset'];newrun=ROOT/'outputs'/current['run_id'];newm=read_json(newrun/'run_manifest.json')
            oldid=f'awarevln-{ds}-valunseen-endpoint9-20261015-v2';oldrun=ROOT/'outputs'/oldid;oldm=read_json(oldrun/'run_manifest.json')
            identity_fields=('model_sha256','config_sha256','navmesh_sha256','benchmark_sha256','environment_sha256','split','language')
            mismatches=[key for key in identity_fields if oldm.get(key)!=newm.get(key)]
            expected_policy=[]
            for entry in oldm['frozen_files']:
                path=Path(entry['path'])
                try:relative=path.relative_to(ROOT)
                except ValueError:continue
                if relative.parts[0]=='src' or str(relative) in ('scripts/preflight.py',f'configs/vlnce_baselines/config/{ds}_baselines/awarevln.yaml'):
                    expected_policy.append(entry)
            if expected_policy!=newm.get('baseline_policy_files'):mismatches += ['baseline_policy_file_hashes']
            oldproto=oldm.get('annotation_protocol',{}).get('protocol_id','original')
            newproto=newm.get('annotation_protocol',{}).get('protocol_id','original')
            if oldproto!=newproto:mismatches += ['annotation_protocol']
            oldspec=oldm['datasets'][ds];newspec=newm['datasets'][ds]
            if oldspec['annotation_sha256']!=newspec['annotation_sha256'] or oldspec['gt_sha256']!=newspec['gt_sha256']:
                mismatches += ['annotation_sha256_or_gt_sha256']
            oldkeys={x['task_key'] for x in oldm['expected_tasks']};newkeys={x['task_key'] for x in newm['expected_tasks']}
            if oldkeys!=newkeys:mismatches += ['expected_task_keys']
            if mismatches:raise ValueError(f'Cannot report paired delta for {ds}: {mismatches}')
            oldrows={x['task_key']:x for x in rows(oldrun/'results.jsonl')}
            newrows={x['task_key']:x for x in rows(newrun/'results.jsonl')}
            if oldrows.keys()!=newrows.keys() or oldrows.keys()!=oldkeys:raise ValueError(f'Paired result coverage mismatch for {ds}')
            pairs={}
            for label,ids in material['leaves'][ds].items():pairs[label]=ids
            for label,parts in [('A1+A2',['A1','A2']),('A',['A1','A2','A3']),('B1+B2',['B1','B2']),('B',['B1','B2','B3']),('Full',['A1','A2','A3','B1','B2','B3','Remaining'])]:pairs[label]=[i for part in parts for i in material['leaves'][ds][part]]
            deltas={}
            for label,ids in pairs.items():
                keyset={k for k in oldkeys if k.split('|')[-2] in set(ids)}
                if len(keyset)!=len(ids):raise ValueError(f'Unexpected pair subset membership {ds}/{label}')
                delta={}
                for metric in ('sr','spl','ndtw','ne','oracle_sr'):
                    diffs=[newrows[k]['metrics'][metric]-oldrows[k]['metrics'][metric] for k in keyset]
                    delta[metric]={'new_minus_old_mean':sum(diffs)/len(diffs),'changed_task_count':sum(abs(v)>1e-12 for v in diffs),'display_unit':'percentage_points' if metric!='ne' else 'meters'}
                deltas[label]={'episodes':len(keyset),'metrics':delta}
            current['paired_comparison']={'baseline_run_id':oldid,'baseline_status':by_run.get(oldid,{}).get('status','unregistered'),'baseline_manifest_sha256':digest(oldrun/'run_manifest.json'),'baseline_results_sha256':digest(oldrun/'results.jsonl'),'matched_identity_fields':list(identity_fields)+['baseline_policy_file_hashes','annotation_protocol','annotation_sha256','gt_sha256','expected_task_keys'],'matched_policy_file_count':len(expected_policy),'overall_source_sha256_equal':oldm['source_sha256']==newm['source_sha256'],'runner_scope_note':'Overall source SHA differs because the new fixed-partition data-binding/reporting harness is included in source identity; all 427 frozen model/data/evaluator source/config policy files are byte-identical.','metrics':'per episode, new minus old; ratios converted to percentage points for presentation','subsets':deltas,'acceptance_caveat':'Metric deltas do not change a prior retracted status or strict geometry gate.'}
    name='checkpoint-choice-historical' if historical else 'checkpoint-choice-20261024'
    atomic_json(dest/(name+'.json'),{'records':result})
    text=['# '+('历史完整测评按VLN固定划分重算' if historical else '2026-10-24 VLN-awareVLN baseline测评'),'','历史重分组不是新模型推理；R2R retracted状态与已知几何限制不因换目录或分块消失。当前endpoint9与原始VLN的9条RxR差异见物化回执。','']
    for r in result:
        text+=['## '+r['dataset'],'',f"Run `{r['run_id']}`；状态 `{r['status']}`；来源 `{r['origin']}`。",'',f"模型 `{r['model_sha256']}`；源码 `{r['source_sha256']}`；profile `{r['profile_sha256']}`。",'', '| Scope | Episodes | SR % | SPL % | nDTW % | NE m | Oracle SR % | 普通失败 |','|---|---:|---:|---:|---:|---:|---:|---:|']
        for label,s in r['subsets'].items():
            v=s['datasets'][r['dataset']];x=v['metrics']
            text.append(f"| {label} | {v['completed']}/{v['expected']} | {x['sr']*100:.6f} | {x['spl']*100:.6f} | {x['ndtw']*100:.6f} | {x['ne']:.6f} | {x['oracle_sr']*100:.6f} | {v['navigation_failures']} |")
        if r.get('paired_comparison'):
            pair=r['paired_comparison'];text+=['','### 与旧完整run逐任务配对差异（新减旧）','',f"Baseline `{pair['baseline_run_id']}`（状态 `{pair['baseline_status']}`）；模型、基础配置、environment、网格、benchmark、endpoint9协议、annotation/GT哈希、完整task_key集合均匹配；模型/评测关键src、preflight和公开任务config共{pair['matched_policy_file_count']}个冻结文件逐项SHA完全相同。整体source SHA不同，是新固定划分数据绑定与报告入口加入源码身份所致，不属于模型策略改动。Δ基于逐任务差值平均；SR/SPL/nDTW/Oracle SR为百分点，NE为米。差值只描述指标，不能清除旧R2R retracted或几何限制。",'','| Scope | Episodes | ΔSR pp | ΔSPL pp | ΔnDTW pp | ΔNE m | ΔOracle SR pp | 指标变化任务数 SR/SPL/nDTW/NE/OSR |','|---|---:|---:|---:|---:|---:|---:|---|']
            for label,row in pair['subsets'].items():
                m=row['metrics'];fmt=lambda k:f"{m[k]['new_minus_old_mean']*(100 if k!='ne' else 1):+.6f}"
                counts='/'.join(str(m[k]['changed_task_count']) for k in ('sr','spl','ndtw','ne','oracle_sr'))
                text.append(f"| {label} | {row['episodes']} | {fmt('sr')} | {fmt('spl')} | {fmt('ndtw')} | {fmt('ne')} | {fmt('oracle_sr')} | {counts} |")
            text+=['']
        text+=['',f"manifest SHA `{r['manifest_sha256']}`；划分物化SHA `{r['partition_sha256']}`。累计指标以任务级记录聚合，不能平均块均值。",'']
    (dest/(name+'.md')).write_text('\n'.join(text))
    # Main comparison remains generated from machine records; histories and new runs are separate.
    table=['# VLN 模型测试总表 / Case1','','R2R/RxR分别展示；不同scope或配置不自动计算收益。原始轨迹在outputs，不随Git发布。','']
    collections=[]
    for p in [dest/'checkpoint-choice-historical.json',dest/'checkpoint-choice-20261024.json']:
        if p.exists():collections+=read_json(p)['records']
    for ds in ('r2r','rxr'):
        table+=['## '+ds,'','| Scope | Episodes | Model | Run | Status | SR % | SPL % | nDTW % | NE m | Oracle SR % | ΔSR pp | ΔSPL pp | ΔnDTW pp | ΔNE m | ΔOracle pp | 来源 |','|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|']
        for r in collections:
            if r['dataset']!=ds:continue
            for label,s in r['subsets'].items():
                v=s['datasets'][ds];x=v['metrics'];report='checkpoint-choice-historical.md' if r['origin'].startswith('historical') else 'checkpoint-choice-20261024.md'
                pair=r.get('paired_comparison',{}).get('subsets',{}).get(label,{}).get('metrics',{})
                dsr=f"{pair['sr']['new_minus_old_mean']*100:+.3f}" if pair else '—';dspl=f"{pair['spl']['new_minus_old_mean']*100:+.3f}" if pair else '—';dndtw=f"{pair['ndtw']['new_minus_old_mean']*100:+.3f}" if pair else '—';dne=f"{pair['ne']['new_minus_old_mean']:+.4f}" if pair else '—';doracle=f"{pair['oracle_sr']['new_minus_old_mean']*100:+.3f}" if pair else '—'
                table.append(f"| {label} | {v['completed']} | AwareVLN official | [{r['run_id']}]({report}) | {r['status']} | {x['sr']*100:.3f} | {x['spl']*100:.3f} | {x['ndtw']*100:.3f} | {x['ne']:.4f} | {x['oracle_sr']*100:.3f} | {dsr} | {dspl} | {dndtw} | {dne} | {doracle} | {r['origin']} |")
        table.append('')
    table+=['Δ列仅在冻结身份/数据/profile/task集合一致的逐任务配对下报告，均为新减旧；SR/SPL/nDTW/Oracle SR单位百分点，NE单位米。历史重分组只说明历史同一完整run按固定集合拆分，不是新模型推理。R2R旧结果保持retracted；新旧分数相等不解除其额外严格几何限制。','[原完整测评登记与详细身份](model_results.md)。新运行未结束/未审计时不填完整成绩；状态见outputs/checkpoint-choice-20261024/state.json。','']
    (dest/'MODEL_TEST_RESULTS.md').write_text('\n'.join(table))
    print('Generated '+name+' and MODEL_TEST_RESULTS.md')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','run','report','report-historical']);a=p.parse_args()
    if a.command=='prepare':prepare()
    elif a.command=='run':run_all()
    else:report(a.command=='report-historical')
