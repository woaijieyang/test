"""Sealed-order native smoke through the inherited single-environment evaluator."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time,uuid
from types import SimpleNamespace
from .selector import selected_rows,shard
from .registry_binding import sha,copy_frozen_json

def dump(path,value):
    with Path(path).open("x") as stream:
        json.dump(value,stream,indent=2,allow_nan=False)
        stream.write("\n")

def verify_map_prerequisites(root,profile,*,full_A=False,hook_mode="on"):
    if full_A and profile.get('storage_admission',{}).get('mode')=='capacity_only':
        from .admission import verify_capacity_only
        return verify_capacity_only(root,profile)
    lock_path=Path(profile.get("prerequisite_lock",""))
    if not lock_path.is_file()or sha(lock_path)!=profile.get("prerequisite_lock_sha256"):
        raise RuntimeError("001 prerequisite lock missing or changed")
    lock=json.loads(lock_path.read_text())
    if lock.get("status")!="READY_FOR_16_PER_DOMAIN":
        raise RuntimeError("001 recorded/resource gates have not passed")
    for item in lock["code_files"]+lock["evidence_files"]:
        path=Path(item["path"])
        if not path.is_file()or sha(path)!=item["sha256"]:raise RuntimeError("001 prerequisite source/evidence drift: "+str(path))
    if lock["map_memory_config_sha256"]!=__import__("hashlib").sha256(
            json.dumps(profile["map_memory"],sort_keys=True,separators=(",",":")).encode()).hexdigest():
        raise RuntimeError("001 model/geometry/resource profile differs from validated recording")
    for file in lock["asset_locks"]:
        path=Path(file["path"])
        if sha(path)!=file["sha256"]:raise RuntimeError("001 asset lock changed")
        asset=json.loads(path.read_text())
        for item in asset.get("weights",[])+asset.get("model_small_and_native",[])+asset.get("files",[]):
            if sha(Path(item["path"]))!=item["sha256"]:raise RuntimeError("001 model/runtime/scene asset drift: "+item["path"])
    if full_A:
        gate=Path(profile.get("full_A_gate",""))
        if not gate.is_file():raise RuntimeError("001 fullA requires completed16/domain paired shadow smoke")
        result=json.loads(gate.read_text())
        if result.get("status")!="PASS_ENGINEERING"or result.get("hard_contract_errors"):
            raise RuntimeError("001 smoke engineering gate failed or incomplete")
        if [(x["dataset"],x["fixed_denominator"])for x in result["domains"]]!=[("r2r",16),("rxr_us",16)]:
            raise RuntimeError("001 smoke coverage mismatch")
        forecast=result.get("full_A_resource_forecast",{})
        if forecast.get("status")!="ADMITTED":raise RuntimeError("001 fullA storage forecast missing or insufficient")
        # Launch matched control first. Its admission reserves both runs;the
        # following shadow needs only its remaining predicted bytes.
        needed=(forecast["estimated_additional_bytes"]if hook_mode=="off"else
                forecast["estimated_additional_by_variant_bytes"]["shadow"])
        import shutil
        if shutil.disk_usage(root).free<needed+forecast["reserve_bytes"]:
            raise RuntimeError("001 fullA current free space no longer meets frozen smoke forecast")
    return lock

def navigation_policy_identity(map_stage,hook_mode):
    # The inherited HAMLET gate interprets method as the navigation policy.
    # A stage001 memory sidecar changes only its own feature identity.
    return dict(method="baseline",sidecar_feature="geometry_shadow"if map_stage and hook_mode=="on"else
                "pose_shadow"if hook_mode=="on"else"disabled")

def navigation_worker_environment(base,*,domain,source_sha,run_uid,attempt_id,dataset,map_stage,hook_mode,profile_path):
    env=dict(base,CASE1_RUN_ROOT=str(domain),CASE1_SOURCE_SHA256=source_sha,
        CASE2_RUN_UID=run_uid,CASE2_ATTEMPT_ID=attempt_id,CASE2_DATASET_KEY=dataset,
        CASE2_STAGE000="1",CASE2_MAP_MEMORY="1"if map_stage else"0",CASE2_HOOK_MODE=hook_mode)
    if hook_mode=="on":env["CASE2_POSE_PROFILE"]=str(profile_path)
    else:
        for key in ("CASE2_POSE_PROFILE","POSEADAPTER_BROKER","POSEADAPTER_BROKER_PID","GRAPH_MEMORY_BROKER","GRAPH_MEMORY_BROKER_PID"):
            env.pop(key,None)
    env.pop("CASE2_HAMLET_CONFIG",None)
    return env

def evaluate(bindings,profile_path,registry,partition,datasets,limit,output,*,start_offset=0,hook_mode="on",attempt_id="attempt0",worker_index=0,worker_count=1,selection_manifest=None,execution_segment=None,preflight_only=False):
    root=Path(bindings["project_root"]).resolve()
    out=Path(output).absolute()
    if root/"outputs/graph_memory" not in out.parents:
        raise ValueError("Smoke output must be under case2 graph_memory")
    if hook_mode not in {"on","off"} or not isinstance(attempt_id,str) or not attempt_id:
        raise ValueError("Explicit hook mode and attempt identity required")
    if not os.environ.get("CASE1_PROTECTION") or (hook_mode=="on" and not os.environ.get("POSEADAPTER_BROKER")):
        raise RuntimeError("Use protected runtime and the broker for hook-on")
    from case1_runtime.scene_assets import verify_scene_binding
    scene_assets=verify_scene_binding(root,bindings)
    profile_path=Path(profile_path).resolve()
    profile=json.loads(profile_path.read_text())
    if profile.get("pose_sampling")=="release4_12":
        from graphAdapter.observation_pose.production import verify_package
        verify_package(profile["pose_package"])
    map_stage=profile.get("feature")=="map_memory"
    storage_binding=None
    routing=profile.get('storage_lifecycle',{}).get('routing')
    if routing:
        from graphAdapter.map_memory.storage.routing import RunRouting
        storage_binding=dict(root=routing['root'],plan_sha256=routing['plan_sha256'],
            side='shadow'if hook_mode=='on'else'control',attempt=attempt_id,worker_id=('shadow'if hook_mode=='on'else'control')+str(worker_index))
        storage_route=RunRouting(storage_binding)
        if storage_route.root not in out.parents:raise ValueError('Evaluation output must belong to this new storage run')
        manifest_path=os.environ.get('CASE2_STORAGE_RUN')
        if not manifest_path or Path(manifest_path).resolve()!=storage_route.root/'routing_run.json':
            raise RuntimeError('Use --storage-run for production process caches and brokers')
    selection=None
    if selection_manifest is not None:
        lock=profile.get("random_validation",{})
        selection=Path(selection_manifest).resolve()
        if (not map_stage or Path(lock.get("file","")).resolve()!=selection
            or not selection.is_file()or sha(selection)!=lock.get("sha256")):
            raise ValueError("Random validation must match the frozen profile manifest")
    elif profile.get("random_validation"):raise ValueError("Frozen random validation manifest is required")
    if map_stage:
        if profile.get('map_memory',{}).get('execution_mode','live')!='live':
            raise RuntimeError('Navigation requires live model/geometry execution,not archive-only IO')
        if profile.get("implementation_status")!="FROZEN_READY_FOR_SHADOW":
            raise RuntimeError("001 CPU/formal-recorded validation gates are not ready for navigation")
        if profile.get('production_admission'):
            from .admission import verify_release4_production
            contract=verify_release4_production(root,profile)
            actual_binding=hashlib.sha256(json.dumps(bindings,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if actual_binding!=contract['bindings_content_sha256']:raise RuntimeError('Frozen host binding changed')
        else:contract=verify_map_prerequisites(root,profile,full_A=limit is None,hook_mode=hook_mode)
        if partition!="A"or start_offset!=0 or limit not in (None,16)or datasets!=["r2r","rxr_us"]:
            raise ValueError("001 permits sealedA16/domain smoke or fullA only")
        if profile.get("memory_injection")or profile.get("frontier")or profile.get("navigation"):
            raise ValueError("001 is shadow memory only")
        if hook_mode=="on"and not os.environ.get("GRAPH_MEMORY_BROKER"):
            raise RuntimeError("001on requires dedicated memory broker")
        if type(worker_count)is not int or type(worker_index)is not int or not 0<=worker_index<worker_count:
            raise ValueError("Invalid sealed-index worker shard")
    else:
        if hook_mode=="off" and (start_offset,limit)!=(0,5):
            raise ValueError("No-hook000controls are restricted to requiredsealed5plus5")
        if partition!="A"or (start_offset,limit)not in {(0,5),(0,15),(15,10)}or datasets!=["r2r","rxr_us"]or (worker_index,worker_count)!=(0,1):
            raise ValueError("Stage000requires authorizedsealedArange,no new shards")
    segment_spec=None
    if execution_segment is not None:
        if not profile.get('production_admission') or execution_segment not in contract['segments']:raise ValueError('Unknown frozen execution segment')
        segment_spec=contract['segments'][execution_segment]
        if (worker_index,worker_count)!=(segment_spec['worker_index'],4):raise ValueError('Frozen segment worker assignment mismatch')
    elif profile.get('production_admission'):raise ValueError('Production requires explicit frozen execution segment')
    if not set(os.sched_getaffinity(0))<=set(bindings["cpu_assignment"]):
        raise ValueError("CPU affinity exceeds the registered assignment")
    gpu_ids=[int(value) for value in os.environ.get("CUDA_VISIBLE_DEVICES","").split(",") if value]
    if len(gpu_ids)!=1 or gpu_ids[0] not in bindings["gpu_assignment"]:
        raise ValueError("Use one registered physical GPU")
    from .resources import admit
    admission=admit(gpu_ids[0],bindings["minimum_free_gpu_mib"])
    profile_path=Path(profile_path).resolve()
    if sha(Path(registry)/"seal.json")!=bindings["dataset_seal_sha256"]:
        raise ValueError("Dataset seal drift")
    for name,entry in bindings["datasets"].items():
        for asset in ("annotation","gt"):
            if sha(Path(entry[asset]))!=entry[asset+"_sha256"]:
                raise ValueError("Data drift: "+name+"/"+asset)
    prepared={}
    from habitat_extensions.task import VLNCEDatasetV1,RxRVLNCEDatasetV1
    # Deserialize the exact complete domain subsets before loading either model.
    for ds in datasets:
        with gzip.open(bindings["datasets"][ds]["annotation"],"rt") as stream:
            annotation=json.load(stream)
        chosen=selected_rows(registry,ds,partition,annotation,limit,start_offset=start_offset,
            selection_manifest=selection,selection_sha256=sha(selection)if selection is not None else None)
        if map_stage:
            if limit is None and len(chosen)!={"r2r":612,"rxr_us":407}[ds]:
                raise ValueError("FullA fixed domain denominator mismatch")
            chosen=shard(chosen,worker_index,worker_count)
            if segment_spec is not None:
                begin,end=segment_spec['ranges'][ds]
                chosen=chosen[begin:end]
                expected_count=segment_spec['expected_counts'][ds]
                if type(expected_count)is not int or len(chosen)!=expected_count:
                    raise RuntimeError('Frozen sealed segment count mismatch: '+ds)
                if not chosen and (begin,end)!=(0,0):raise RuntimeError('Undeclared empty native domain: '+ds)
            expected=[str(item["row"]["episode_id"])for item in chosen]
        else:
            expected=bindings["smoke_ids"][ds][:limit]
            if [str(item["row"]["episode_id"]) for item in chosen]!=expected:
                raise ValueError("Selected IDs differ from sealed approved order")
        if any("/".join(Path(item["row"]["scene_id"]).parts[-3:]) not in scene_assets["assets"] for item in chosen):
            raise ValueError("Selected scene is absent from frozen scene profile")
        subset=dict(annotation)
        subset["episodes"]=[item["row"] for item in chosen]
        if not chosen:
            if segment_spec is None or segment_spec['ranges'][ds]!=[0,0]or segment_spec['expected_counts'][ds]!=0:
                raise RuntimeError('Nonempty sealed expectation became empty: '+ds)
            prepared[ds]=(subset,chosen)
            continue
        native=(VLNCEDatasetV1 if ds=="r2r" else RxRVLNCEDatasetV1)()
        if ds=="rxr_us":
            native.config=SimpleNamespace(SPLIT="val_unseen")
        native.from_json(json.dumps(subset),scenes_dir=scene_assets["scene_root"],num_chunks=1,chunk_idx=0)
        if [str(episode.episode_id) for episode in native.episodes]!=expected:
            raise ValueError("Native dataset reordered members")
        def member(ep):
            scene=Path(ep.scene_id)
            return (ds,"/".join(scene.parts[-3:]),str(ep.episode_id),
                    str(getattr(ep.instruction,"instruction_id","-")))
        native_full=[member(ep)for ep in native.episodes]
        expected_full=[(ds,"/".join(Path(item["row"]["scene_id"]).parts[-3:]),str(item["row"]["episode_id"]),
                        str(item["row"]["instruction"].get("instruction_id","-")))for item in chosen]
        if native_full!=expected_full:raise ValueError("Native full scene/episode/instruction identity drift")
        prepared[ds]=(subset,chosen)
    if preflight_only:
        from .registry_binding import source_snapshot
        _,source_sha=source_snapshot(root,map_stage=map_stage)
        out.mkdir(parents=True,exist_ok=False)
        package=None
        if hook_mode=='on'and profile.get('pose_sampling')=='release4_12':
            import poseAdapter
            from graphAdapter.observation_pose.production import verify_package
            package=verify_package(profile['pose_package'],actual_import=True)
        proof=dict(status='PASS_PRE_MODEL_PUBLIC_ENTRY_PREFLIGHT',scope='Data/arguments/package/brokers only; not navigation or private model execution',
            source_sha256=source_sha,profile_sha256=sha(profile_path),hook_mode=hook_mode,segment=execution_segment,
            domains={ds:dict(expected=len(rows),status='NATIVE_READER_VERIFIED'if rows else'NO_WORK_FROZEN_EMPTY_SEGMENT',
                sealed_indexes=[r['sealed_index']for r in rows],identities=[r['identity']for r in rows])for ds,(_,rows)in prepared.items()},
            pose_package=package,pose_broker_supplied=bool(os.environ.get('POSEADAPTER_BROKER')),
            memory_broker_supplied=bool(os.environ.get('GRAPH_MEMORY_BROKER')),model_instances=0,evaluator_registered=False)
        dump(out/'preflight.json',proof)
        return []
    out.mkdir(parents=True,exist_ok=False)
    from .registry_binding import source_snapshot
    frozen,source_sha=source_snapshot(root,map_stage=map_stage)
    if storage_binding is not None and storage_route.plan.get('evidence_source_sha256')!=source_sha:
        raise RuntimeError('Storage plan differs from actual evaluator source identity')
    if map_stage and limit is None and not profile.get('production_admission') and profile.get('storage_admission',{}).get('mode')!='capacity_only':
        smoke_gate=json.loads(Path(profile["full_A_gate"]).read_text())
        if smoke_gate["source_sha256"]!=source_sha or smoke_gate.get("profile_sha256")!=sha(profile_path):
            raise RuntimeError("001 fullA source/profile differs from passed smoke")
    run_uid="run-"+uuid.uuid4().hex
    manifest=dict(**navigation_policy_identity(map_stage,hook_mode),
        stage="001"if map_stage else"000",partition=partition,smoke=limit is not None,
        shard=dict(worker_index=worker_index,worker_count=worker_count),
        run_uid=run_uid,attempt_id=attempt_id,hook_mode=hook_mode,execution_segment=execution_segment,execution_ranges=segment_spec["ranges"]if segment_spec else None,execution_expected_counts=segment_spec["expected_counts"]if segment_spec else None,
        selection_start_offset=start_offset,
        selection_kind="random32"if selection is not None else"sealed_order",
        selection_manifest_sha256=sha(selection)if selection is not None else None,
        source_sha256=source_sha,frozen_files=frozen,scene_assets=scene_assets,pose_package=profile.get("pose_package"),pose_sampling=profile.get("pose_sampling"),
        profile_sha256=sha(profile_path),registry_sha256=bindings["dataset_seal_sha256"],
        resource_budget=dict(gpus=gpu_ids,cpu=sorted(os.sched_getaffinity(0))),
        gpu_admission=admission,
        gpu_identity=subprocess.check_output(["nvidia-smi","--query-gpu=index,uuid,memory.used","--format=csv,noheader"],text=True),
        attempt_selection="first complete valid attempt; all prior failed infrastructure attempts retained",
        registered_scope=("randomA32:16/domain"if selection is not None else"A16/domain smoke"if limit==16 else"fullA612/407")if map_stage else str(limit)+" plus "+str(limit)+" pose chain;one native environment/domain;sealed order")
    if storage_binding is not None:
        manifest['storage_routing']=storage_binding
        from graphAdapter.map_memory.storage.lifecycle import atomic_json
        registrations=storage_route.root/'control/evaluations';registrations.mkdir(parents=True,exist_ok=True)
        atomic_json(registrations/(run_uid+'.json'),dict(path=str(out),side=storage_binding['side'],manifest=manifest))
    dump(out/"no-work.json",{ds:dict(expected=0,status="NO_WORK_FROZEN_EMPTY_SEGMENT")for ds,(_,rows)in prepared.items()if not rows})
    dump(out/"run_identity.json",manifest)
    copy_frozen_json(profile_path,out/"effective_config.json",manifest["profile_sha256"])
    if map_stage:
        policy=Path(profile["acceptance_policy"])
        if sha(policy)!=profile["acceptance_policy_sha256"]:raise ValueError("Frozen acceptance policy drift")
        copy_frozen_json(policy,out/"acceptance_policy.json",profile["acceptance_policy_sha256"])
    results=[]
    for ds in datasets:
        subset,chosen=prepared[ds]
        if not chosen:continue
        domain=out/ds
        domain.mkdir(exist_ok=False)
        annotation=domain/"annotation.json.gz"
        with gzip.open(annotation,"wt") as stream:
            json.dump(subset,stream)
        entry=bindings["datasets"][ds]
        spec=dict(annotation=str(annotation),annotation_sha256=sha(annotation),gt=entry["gt"],gt_sha256=entry["gt_sha256"])
        dump(domain/"dataset-spec.json",spec)
        expected=[str(item["row"]["episode_id"])for item in chosen]
        dump(domain/"ids.json",expected)
        dump(domain/"registered_identities.json",[dict(identity=item["identity"],registered_identity=item["registered_identity"],sealed_index=item["sealed_index"],
            original_sealed_index=item["original_sealed_index"],selection_index=item["selection_index"]) for item in chosen])
        dump(domain/"run_manifest.json",dict(manifest,dataset_spec_sha256=sha(domain/"dataset-spec.json")))
        env=navigation_worker_environment(os.environ,domain=domain,source_sha=source_sha,run_uid=run_uid,
            attempt_id=attempt_id,dataset=ds,map_stage=map_stage,hook_mode=hook_mode,profile_path=profile_path)
        if storage_binding is not None:env['CASE2_STORAGE_BINDING']=json.dumps(storage_binding)
        command=[bindings["host_python"],str(root/"scripts/evaluate_worker.py"),
            "--dataset","rxr" if ds=="rxr_us" else ds,"--output",str(domain/"worker"),
            "--scenes",scene_assets["scene_root"],"--chunk","0","--chunks","1",
            "--ids",str(domain/"ids.json"),"--dataset-spec",str(domain/"dataset-spec.json")]
        current_admission=admit(gpu_ids[0],bindings["minimum_free_gpu_mib"])
        dump(domain/"gpu-admission.json",current_admission)
        started=time.monotonic()
        with (domain/"stdout.log").open("x") as log:
            process=subprocess.Popen(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
            dump(domain/"process.json",dict(pid=process.pid,
                starttime=Path(f"/proc/{process.pid}/stat").read_text().split()[21],command=command))
            with(domain/"resource_samples.jsonl").open("x")as samples:
                while process.poll()is None:
                    try:
                        snapshot=subprocess.check_output(["nvidia-smi","--query-gpu=index,uuid,memory.used,utilization.gpu",
                            "--format=csv,noheader,nounits"],text=True,timeout=10)
                        values=next(line.split(",")for line in snapshot.splitlines()if int(line.split(",")[0])==gpu_ids[0])
                        sample=dict(monotonic=time.monotonic(),physical_gpu=gpu_ids[0],uuid=values[1].strip(),
                            used_mib=int(values[2]),utilization_percent=int(values[3]),
                            scope="sampled total physical GPU use,all owned host/pose/memory processes")
                    except (subprocess.SubprocessError,ValueError,StopIteration)as error:
                        sample=dict(monotonic=time.monotonic(),resource_sample_error=repr(error))
                    samples.write(json.dumps(sample)+"\n");samples.flush()
                    time.sleep(2)
            code=process.wait()
        observed={}
        order=[]
        if storage_binding is not None:
            for item in chosen:
                member=list(item['identity'])
                entry=next((e for e in storage_route.plan['entries']if e['member']==member),None)
                if entry is None:raise ValueError('Selected member is absent from storage plan')
                result_dir=storage_route.root/'results'/entry['key']/storage_binding['side']/attempt_id
                terminal=result_dir/'retention.json'
                if terminal.exists():
                    saved=json.loads(terminal.read_bytes())['summary'];ep=str(item['row']['episode_id'])
                    observed[ep]=(result_dir/'trace.jsonl.gz',saved.get('status')=='completed')
                    order.append((saved['episode_sequence'],ep))
        for path in ([]if storage_binding is not None else sorted((domain/"worker/episodes").glob("*/trace.jsonl"))):
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            if not rows:
                continue
            reset=rows[0]
            episode=str(reset["episode_id"])
            if episode in observed:
                raise ValueError("Duplicate recorded episode")
            observed[episode]=(path,rows[-1]["kind"]=="terminal")
            order.append((reset["episode_sequence"],episode))
        if [episode for _,episode in sorted(order)]!=expected[:len(order)]:
            raise ValueError("Executed episode order differs from sealed order")
        domain_elapsed=time.monotonic()-started
        for item in chosen:
            ep=str(item["row"]["episode_id"])
            record=observed.get(ep)
            row=dict(dataset=ds,episode_id=ep,identity=item["identity"],exit_code=code,
                elapsed_seconds_domain=domain_elapsed,status="execution_complete_pending_audit" if record and record[1] and code==0 else "failed",
                log=str(domain/"stdout.log"),host_trace=str(record[0]) if record else None,
                flow_trace=str(domain/"worker/observation_pose/flow_trace.jsonl") if hook_mode=="on" else None,hook_mode=hook_mode)
            results.append(row)
            with (out/"per_episode.jsonl").open("a") as stream:
                stream.write(json.dumps(row)+"\n")
        dump(domain/"execution_result.json",dict(exit_code=code,observed_order=sorted(order),elapsed_seconds=domain_elapsed))
    dump(out/"execution_summary.json",dict(expected=sum(len(x[1])for x in prepared.values()),fixed_A_denominators={"r2r":612,"rxr_us":407}if map_stage and limit is None else None,
        attempted=len(results),domain_work={ds:dict(expected=len(rows),status="EXECUTED"if rows else"NO_WORK_FROZEN_EMPTY_SEGMENT")for ds,(_,rows)in prepared.items()},results=results))
    return results


def finalize_retained_episode(lifecycle,request):
    """Terminal controller entry: publish standalone evidence then free owned work.

    Only new lifecycle-owned trees qualify. Legacy/frozen run outputs cannot be
    adopted. Offline pair auditing remains possible from terminal receipts.
    """
    from graphAdapter.map_memory.storage.lifecycle import audit_single
    state=lifecycle._state()['state']
    if state in ('SEALED','DELETING','DELETED'):
        sealed=json.loads((lifecycle.result/'retention.json').read_bytes())
    else:
        sealed=lifecycle.seal(**request)
    audited=audit_single(lifecycle)
    finalized=lifecycle.finalize(audited)
    return dict(retention=sealed,single_side_audit=audited,finalization=finalized)
