"""Frozen recorded-Landmark geometry queries, no navigation or model execution."""
import gc,json,time
from pathlib import Path
from oracle.common.artifacts import digest,content_digest,owned_output,write_json,package_sources,freeze_sources
from oracle.common.offline_audit import identity
from oracle.research.full_worker import load_task
from oracle.verification.source_scene import SourceScene
from oracle.planners.collision_queries import CachedSourceQueries


def audit(case_root,output):
    started=time.perf_counter();cpu_started=time.process_time()
    startup=identity();root=Path(case_root).resolve();output=owned_output(root,output)
    startup.update(method_category='planning_geometry_query_equivalence',
        task_contract='Compare finite recorded Landmark endpoint-pair queries; no task/target edits or navigation',
        privileged_information=['native_exported_scene_triangles','recorded_landmark_positions'],
        environment_limit='Protected Case1 geometry calculations only; no Habitat actions or route-success evidence')
    if output.exists():raise FileExistsError(output)
    cfg_path=Path(__file__).resolve().parents[1]/'configs/experiments/cache_equivalence_v1.json'
    cfg=json.loads(cfg_path.read_text());catalog_path=root/cfg['catalog'];lineage=root/cfg['lineage']
    if digest(catalog_path)!=cfg['catalog_sha256'] or digest(lineage)!=cfg['lineage_sha256']:
        raise ValueError('Geometry/evidence source changed')
    catalog=json.loads(catalog_path.read_text())['scenes'];rows=json.loads(lineage.read_text())
    old=root/'outputs/oracleAdapter/full-continuous-reference-v1'
    manifest=json.loads((old/'manifest.json').read_text())
    index={e['record']['task_key']:e for e in json.loads((old/'index.json').read_text())}
    protocol=manifest['protocol'];selected={};selected_contact={}
    for row in sorted(rows,key=lambda r:r['task_key']):
        if row['contract']['dataset']!='landmark_rxr':continue
        task,_=load_task(root,manifest,index[row['task_key']],old/'tasks.jsonl')
        scene=task['scene']
        if row['motion_attempted'] and row['teacher_cost'] and row['actions_by_origin']:
            selected.setdefault(scene,(row,task))
        if row['failure_explanation']['source_contact_reference_indices']:
            selected_contact.setdefault(scene,(row,task))
    output.mkdir();_,sources=package_sources();freeze_sources(output,sources)
    records=[]
    for geometry in catalog:
        scene=geometry['scene'];queries=[];bindings=[]
        if scene in selected:
            row,task=selected[scene];receipt_path=Path(row['receipt'])
            if digest(receipt_path)!=row['receipt_sha256']:raise ValueError('Recorded receipt changed')
            receipt=json.loads(receipt_path.read_text());rp=receipt_path.parent.parent/'execute/motion/result.json'
            if digest(rp)!=receipt['result_sha256']:raise ValueError('Recorded trace changed')
            result=json.loads(rp.read_text());positions=result['positions'];n=len(positions)-1
            for i in sorted({0,n//2,max(0,n-1)}):queries.append((positions[i],positions[i+1]))
            for i in sorted({0,len(task['targets'])//2,len(task['targets'])-1}):
                p=task['targets'][i]
                if p is not None:queries.append((p,p))
            bindings.append(dict(task_key=task['task_key'],receipt_sha256=digest(receipt_path),result_sha256=digest(rp)))
        if scene in selected_contact:
            row,task=selected_contact[scene]
            i=row['failure_explanation']['source_contact_reference_indices'][0];p=task['targets'][i]
            queries.append((p,p));bindings.append(dict(task_key=task['task_key'],source_reference_index=i,receipt_sha256=row['receipt_sha256']))
        if not queries:raise ValueError('No recorded Landmark query for scene '+scene)
        source=SourceScene(geometry['receipt_path'],geometry['receipt_sha256'],protocol,catalog=geometry)
        cache=CachedSourceQueries(source,context_digest=content_digest([scene,geometry,protocol,sources]),**cfg['cache'])
        control_cpu=cached_cpu=0.;positive=0;outcomes=[]
        for repetition in range(cfg['repetitions']):
            for i,(a,b) in enumerate(queries):
                t=time.process_time();expected=source.contact(a,b,certificate=True);control_cpu+=time.process_time()-t
                t=time.process_time();actual=cache.contact(a,b,certificate=True);cached_cpu+=time.process_time()-t
                if actual!=expected:raise ValueError('Cache verdict/certificate changed '+scene+':'+str(i))
                if expected:positive+=1
                outcomes.append(content_digest(actual))
        record=dict(scene=scene,geometry_sha256=source.geometry_sha256,bindings=bindings,queries=queries,
            repetitions=cfg['repetitions'],comparisons=len(queries)*cfg['repetitions'],positive_comparisons=positive,
            equal=True,control_cpu_seconds=control_cpu,cached_cpu_seconds=cached_cpu,
            cache_metrics=cache.metrics,control_triangle_checks=source.triangle_checks,
            cached_triangle_checks=cache.triangle_checks,verdict_digest=content_digest(outcomes))
        records.append(record);write_json(output/'progress'/f'{len(records):03d}.json',record)
        del source,cache;gc.collect()
        if time.perf_counter()-started>cfg['wall_seconds_cap']:raise RuntimeError('Recorded query audit wall cap')
    if len(records)!=71:raise ValueError('Incomplete catalog coverage')
    write_json(output/'records.json',records)
    summary=dict(status='ALL71_RECORDED_QUERY_CACHE_EQUIVALENCE_PASS_NOT_NAVIGATION',startup=startup,scenes=71,
        comparisons=sum(x['comparisons'] for x in records),positive_comparisons=sum(x['positive_comparisons'] for x in records),
        control_cpu_seconds=sum(x['control_cpu_seconds'] for x in records),cached_cpu_seconds=sum(x['cached_cpu_seconds'] for x in records),
        wall_seconds=time.perf_counter()-started,process_cpu_seconds=time.process_time()-cpu_started,
        native_actions=0,r2r_rxr_records_executed=0,records_sha256=digest(output/'records.json'),configuration_sha256=digest(cfg_path),
        limits='Finite recorded query equivalence, not all possible queries or native success. Repetitions explicitly include warm-cache hits; no end-to-end speedup claimed. Independent execution/replay do not use this cache.')
    write_json(output/'validation.json',summary);return summary
