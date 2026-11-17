"""Complete pRb scene validation after byte-controlled detail-only construction."""
import copy,hashlib,json,math,os,time,sys
from collections import Counter
from pathlib import Path
from oracle.common.artifacts import digest,content_digest,owned_output,write_json,package_sources,freeze_sources,require_sources,timestamp
from oracle.common.task_index import merkle_index
from oracle.research.full_worker import validate_launchers,process_identity
from oracle.research.detail_mesh_study import check_single_factor

PASS='PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES'


def may_repair_targets(task,held):
    return not held and task['method_selection']['official_policy']=='none'


def candidate_task(old,points,profile_path,profile_sha,source_sha):
    if old['dataset']!='landmark_rxr' or old['scene']!='pRbA3pwrgk9' or len(points)!=len(old['targets']):raise ValueError('Exact complete scene/occurrences required')
    changed=points!=old['targets']
    if changed and old['method_selection']['official_policy']!='none':raise ValueError('Changed targets cannot silently reuse whole-episode official actions: '+old['task_key'])
    t=copy.deepcopy(old);t.update(targets=points,profile_path=profile_path,profile_sha256=profile_sha,module_source_sha256=source_sha,
        cohort='prb_detail01::'+('repaired_source_points' if changed else 'preserved_targets'))
    t['global_mapping_selection']=dict(family='detail01_preserve_source_clear',parent_selection=old.get('global_mapping_selection'),
        old_targets_sha256=content_digest(old['targets']),executed_targets_sha256=content_digest(points),raw_annotation_unchanged=True,navigation_results_used_for_selection=False)
    return t


def prepare(case_root,output,cpu):
    root=Path(case_root).resolve();out=owned_output(root,output);_,sources=package_sources()
    out.mkdir();freeze_sources(out,sources)
    write_json(out/'preparation-process.json',{**process_identity(),'actual_module':__file__,
        'actual_module_sha256':digest(__file__),'python':sys.executable,'source_digest':content_digest(sources)})
    write_json(out/'source-freeze.json',{'status':'OPEN','phase':'static_preparation'})
    try:
        result=_prepare(case_root,output,cpu)
        require_sources(sources)
        write_json(out/'preparation-state.json',{'status':result['status'],
            'manifest_sha256':digest(out/'manifest.json') if (out/'manifest.json').exists() else None})
        return result
    except BaseException as error:
        write_json(out/'preparation-failure.json',{'error':repr(error),'time':timestamp()})
        write_json(out/'preparation-state.json',{'status':'FAILED_PRESERVED'})
        raise
    finally:
        write_json(out/'source-freeze.json',{'status':'CLOSED','phase':'static_preparation'},immutable=False)


def _prepare(case_root,output,cpu):
    import resource,signal,habitat_sim
    from oracle.verification.source_scene import SourceScene
    from oracle.planners.collision_queries import CachedSourceQueries
    root=Path(case_root).resolve();out=owned_output(root,output);package,sources=package_sources()
    cfg=json.loads((package/'configs/experiments/detail_scene_validation_v1.json').read_text());bp=root/cfg['budget_receipt'];assert digest(bp)==cfg['budget_sha256'];b=json.loads(bp.read_text())
    retained=cfg.get('retained_failed_preparation_seconds',0)
    assert b['development_after_new_reservation_seconds']+840+1800+1200+retained<=86400
    assert b['overall_after_new_reservation_seconds']+840+1800+1200+retained+20*3600<=2592000
    if retained:
        from oracle.research.full_run import live
        failed=root/cfg['retained_failed_preparation']
        assert retained==1200 and json.loads((failed/'preparation-state.json').read_text())['status']=='FAILED_PRESERVED'
        assert not live(json.loads((failed/'preparation-process.json').read_text())) and not (failed/'controller-process.json').exists()
    if cpu not in sorted(os.sched_getaffinity(0))[:64]:raise ValueError('CPU outside authorized64')
    os.sched_setaffinity(0,{cpu});os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15);resource.setrlimit(resource.RLIMIT_CPU,(1195,1200))
    def expired(*_):raise TimeoutError('Fixed1200second static preparation cap')
    signal.signal(signal.SIGALRM,expired);signal.alarm(1195)
    producer=root/cfg['producer'];pv=json.loads((producer/'validation.json').read_text());assert pv['manifest_sha256']==cfg['producer_manifest_sha256'] and digest(producer/'manifest.json')==cfg['producer_manifest_sha256']
    if json.loads((producer/'source-freeze.json').read_text())['status']!='CLOSED':raise ValueError('Build still open')
    built=next(x for x in pv['scenes'] if x['scene']=='pRbA3pwrgk9');assert built['control_byte_match'] and built['point_passes']==18
    import habitat_sim._ext.habitat_sim_bindings as binding
    if digest(binding.__file__)!=built['control']['binding_sha256']:raise ValueError('Static preparation uses a different native binding')
    check_single_factor(built['control']['settings'],built['candidate']['settings']);assert digest(built['candidate']['mesh_path'])==built['candidate']['mesh_sha256']
    parent=root/cfg['parent'];pm=json.loads((parent/'manifest.json').read_text());assert digest(parent/'manifest.json')==cfg['parent_manifest_sha256']
    tasks=[];stream_hash=hashlib.sha256()
    with (parent/'tasks.jsonl').open('rb') as stream:
        for raw in stream:
            stream_hash.update(raw);t=json.loads(raw)
            if t['scene']=='pRbA3pwrgk9':tasks.append(t)
    assert stream_hash.hexdigest()==pm['tasks_file_sha256'] and len(tasks)==660
    pvalidation=json.loads((parent/'validation.json').read_text());assert digest(parent/'results-index.json')==pvalidation['results_index_sha256'];old={x['task_key']:x for x in json.loads((parent/'results-index.json').read_text())}
    policy=json.loads((package/'configs/experiments/global_bounded_mapping_v1.json').read_text());data={}
    for key in ('native','published','catalog','held'):
        p=root/policy['inputs'][key]['path'];assert digest(p)==policy['inputs'][key]['sha256'];data[key]=json.loads(p.read_text())
    native={(x['scene'],x['node']):x['native_candidates'] for x in data['native']['nodes']};published={(x['scene'],x['node']):x for x in data['published']['nodes']};held=set(data['held']['task_keys'])
    geometry=next(x for x in data['catalog']['scenes'] if x['scene']=='pRbA3pwrgk9');source=SourceScene(geometry['receipt_path'],geometry['receipt_sha256'],pm['protocol'],catalog=geometry)
    body=CachedSourceQueries(source,context_digest=content_digest([cfg,geometry,pm['protocol']]),cell_size_m=.5,max_regions=1024,max_queries=16384)
    profile_path=Path(tasks[0]['profile_path']);assert digest(profile_path)==tasks[0]['profile_sha256'];profile=json.loads(profile_path.read_text())
    profile.update(profile_id='landmark-detail01-prb-candidate-v1',status='DIAGNOSTIC_NOT_ADOPTED')
    profile['assets']['mp3d/pRbA3pwrgk9/pRbA3pwrgk9.glb']={**profile['assets']['mp3d/pRbA3pwrgk9/pRbA3pwrgk9.glb'],
        'navmesh_path':built['candidate']['mesh_path'],'navmesh_sha256':built['candidate']['mesh_sha256'],'build_settings':built['candidate']['settings']}
    write_json(out/'profile.json',profile);psha=digest(out/'profile.json');pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(built['candidate']['mesh_path'])
    changed=[];point_proofs=[];static=[];entries=[];newtasks=[];started=time.process_time()
    for t in tasks:
        points=[]
        for i,p in enumerate(t['targets']):
            q=p
            if p is not None and may_repair_targets(t,t['task_key'] in held) and body.contact(p,p) is not None:
                candidate=[float(v) for v in pf.snap_point(p)];node=t['original_viewpoint_path'][i];identity=published[('pRbA3pwrgk9',node)];kind=identity['method']
                if ('pRbA3pwrgk9',node) in native:
                    anchors=native[('pRbA3pwrgk9',node)];assert len(anchors)==1;anchor=anchors[0];kind='official_reference_node'
                elif kind!='UNRESOLVED_no_direct_identity':anchor=identity['position']
                else:anchor=p;kind='bounded_camera_projection'
                valid=all(math.isfinite(v) for v in candidate) and math.dist(candidate,anchor)<=.5
                if valid and kind=='bounded_camera_projection':
                    cam=identity['camera_position'];valid=math.hypot(candidate[0]-cam[0],candidate[2]-cam[2])<.5 and 0<=cam[1]-candidate[1]<=2
                valid=valid and pf.is_navigable(candidate) and math.dist(candidate,list(pf.snap_point(candidate)))<=1e-5
                valid=valid and body.contact(candidate,candidate,certificate=True) is None and body.contact(candidate,candidate,arithmetic='rational_hull') is None
                if valid:q=candidate
                point_proofs.append(dict(task_key=t['task_key'],index=i,old=p,candidate=candidate if all(math.isfinite(v) for v in candidate) else None,accepted=bool(valid),source_anchor=anchor,anchor_kind=kind))
            points.append(q)
        new=candidate_task(t,points,str(out/'profile.json'),psha,content_digest(sources));newtasks.append(new)
        complete=all(p is not None for p in points);nav=complete and all(pf.is_navigable(p) for p in points);connected=bool(nav)
        if connected:
            for a,c in zip(points,points[1:]):
                path=habitat_sim.ShortestPath();path.requested_start=a;path.requested_end=c
                if not pf.find_path(path) or not math.isfinite(path.geodesic_distance):connected=False;break
        endpoints=set(t['landmark_target_indices'])|{0,len(points)-1}
        source_gate=complete and all(body.contact(points[i],points[i],arithmetic='rational_hull') is None for i in endpoints)
        row=dict(task_key=t['task_key'],old_pass=old[t['task_key']]['status']==PASS,changed=points!=t['targets'],native_ready=connected,endpoint_source_gate=source_gate,held=t['task_key'] in held)
        static.append(row)
        if row['changed']:changed.append(t['task_key'])
    regress=[x['task_key'] for x in static if x['old_pass'] and not (x['native_ready'] and x['endpoint_source_gate'])]
    audit=dict(status='COMPLETE660_STATIC_SCREEN',records=660,changed_tasks=len(changed),old_pass_count=sum(x['old_pass'] for x in static),static_regressions=regress,rows=static,point_proofs=point_proofs,process_cpu_seconds=time.process_time()-started,reserved_cpu_seconds=1200)
    write_json(out/'static-audit.json',audit)
    if regress:write_json(out/'not-launched.json',{'reason':'old_strict_pass_static_regression','tasks':regress});signal.alarm(0);return {'status':'REJECTED_STATIC_REGRESSION','task_count':660,'regressions':len(regress)}
    with (out/'tasks.jsonl').open('xb') as stream:
        for t in newtasks:
            raw=(json.dumps(t,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode();offset=stream.tell();stream.write(raw);entries.append(dict(task_key=t['task_key'],dataset='landmark_rxr',offset=offset,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),cohort=t['cohort']))
    merkle,index=merkle_index(entries);write_json(out/'index.json',index)
    config={**pm['config'],'max_workers':32,'total_cpu_budget_hours':20,'expected':{'landmark_rxr':660},'scope':cfg['scope']}
    manifest={'status':'FROZEN_PRB_DETAIL01_COMPLETE660','created_at':timestamp(),'config':config,'sources':sources,'task_count':660,'datasets':{'landmark_rxr':660},
        'protocol':pm['protocol'],'base_method':pm['base_method'],'target_scope':pm['target_scope'],'official_action_sources':pm['official_action_sources'],
        'splits':dict(Counter(t['split'] for t in newtasks)),'information_mapping_groups':dict(Counter(t['cohort'] for t in newtasks)),
        'global_denominator_retained':33954,'held_records_in_scene':sum(t['task_key'] in held for t in tasks),
        'candidate_profile_path':str(out/'profile.json'),'candidate_profile_sha256':psha,
        'task_merkle_root':merkle,'tasks_file_sha256':digest(out/'tasks.jsonl'),'index_sha256':digest(out/'index.json'),
        'parent_run':str(parent),'parent_manifest_sha256':digest(parent/'manifest.json'),'static_audit_sha256':digest(out/'static-audit.json'),
        'launchers':{str(p):digest(p) for p in [root/'oracleAdapter/run.py',root/'scripts/with_runtime.sh']},'scope':cfg['scope']}
    validate_launchers(root,manifest);write_json(out/'manifest.json',manifest);signal.alarm(0);return manifest


def run_with_review(case_root,manifest_path):
    from oracle.research.full_run import run as execute,live
    from oracle.research.full_review import review
    from oracle.research.full_report import report
    root=Path(case_root).resolve();mp=owned_output(root,manifest_path);r=mp.parent;m=json.loads(mp.read_text())
    prep=json.loads((r/'preparation-state.json').read_text())
    if (prep['status']!='FROZEN_PRB_DETAIL01_COMPLETE660' or prep['manifest_sha256']!=digest(mp)
            or (r/'preparation-failure.json').exists() or live(json.loads((r/'preparation-process.json').read_text()))):
        raise ValueError('Complete terminal successful preparation and fresh execution process required')
    if (r/'controller-process.json').exists():raise ValueError('Existing run requires review, not automatic restart')
    if not execute(root,mp):raise RuntimeError('Complete scene run stopped; preserve all outcomes')
    review(root,r,r/'independent-full-review');report(root,r,r/'independent-full-review/validation.json',r/'grouped-report')
    audit=json.loads((r/'static-audit.json').read_text());assert digest(r/'static-audit.json')==m['static_audit_sha256']
    old={x['task_key'] for x in audit['rows'] if x['old_pass']};rows=json.loads((r/'results-index.json').read_text());assert len(rows)==660 and {x['task_key'] for x in rows}=={x['task_key'] for x in audit['rows']}
    new={x['task_key'] for x in rows if x['status']==PASS};iv=json.loads((r/'independent-full-review/validation.json').read_text())
    comparison=dict(status='COMPLETE660_HISTORICAL_SCENE_COMPARISON_NOT_GLOBAL',old_pass=len(old),new_pass=len(new),recovered=sorted(new-old),regressed=sorted(old-new),
        actual_actions=iv['actual_actions'],independently_replayed_actions=iv['independently_replayed_actions'],scene_promotion_gate=bool(new-old) and not old-new,
        limits='Mesh and bounded source-position adaptation jointly changed; same parent Oracle/information contracts. Historical parent comparison, not a randomized matched-time algorithm experiment.',global_acceptance=False)
    write_json(r/'scene-comparison.json',comparison);write_json(r/'review-complete.json',dict(status='COMPLETE660_REVIEW',comparison_sha256=digest(r/'scene-comparison.json'),manifest_sha256=digest(mp)))
