"""All90 failed nominal/remaining native shortest corridors, with source sweeps."""
import ast,collections,datetime,hashlib,json,math,os,struct,sys,time
from pathlib import Path
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.nice(15)
import numpy as np,habitat_sim,psutil
u=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<10 and i not in [6,12,18,20,22,24,27,30]];assert idle;os.sched_setaffinity(0,[min(idle,key=lambda i:u[i])])
B=R/'outputs/landmark-connectivity';O=B/'D7-phasehalf-new90-native-corridors-v1';O.mkdir(exist_ok=False)
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':list(os.sched_getaffinity(0))})
run=B/'full-source-guard-D7-tiled-phasehalf-v1/guarded';m=json.loads((run/'manifest.json').read_text());tasks={t['task_key']:t for t in json.loads(Path(m['candidate_tasks_path']).read_text())['tasks']};source=json.loads((run/'validation.json').read_text());results={r['task_key']:r for r in source['results']};comparison=B/'D7-tiled-phasehalf-proof-comparison-v1/validation.json';selected=json.loads(comparison.read_text())['new90_failed'];assert len(selected)==90
profile=json.loads(Path(m['profile_path']).read_text());assert digest(m['profile_path'])==m['profile_sha256'];asset=profile['assets']['mp3d/D7N2EKCX4Sj/D7N2EKCX4Sj.glb'];pf=habitat_sim.PathFinder();assert digest(asset['navmesh_path'])==asset['navmesh_sha256'] and pf.load_nav_mesh(asset['navmesh_path'])
receipt=Path(m['native_geometry']['receipt_path']);assert digest(receipt)==m['native_geometry']['receipt_sha256'];native=json.loads(receipt.read_text());gp=Path(native['native_geometry_path']);assert digest(gp)==native['native_geometry_sha256'];raw=gp.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);vs=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ix=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vs[ix].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);cache={};regions={}
helper=R/'tests/landmark_diagnostics/audit_prb_step_interpretations.py';bound=json.loads((B/'pRb-original-trace-step-interpretation-v1/validation.json').read_text());assert digest(helper)==bound['script_sha256'];functions=[n for n in ast.parse(helper.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='sweep'];assert len(functions)==1;exec(compile(ast.Module(body=functions,type_ignores=[]),str(helper),'exec'),globals())
paths={};rows=[]
def query_path(start,end):
    identity=hashlib.sha256(json.dumps([start,end],sort_keys=True).encode()).hexdigest()
    if identity in paths:return identity
    query=habitat_sim.ShortestPath();query.requested_start=start;query.requested_end=end;assert pf.find_path(query) and math.isfinite(query.geodesic_distance)
    native_points=[[float(v) for v in p] for p in query.points];assert len(native_points)>=2
    points=[list(start),*native_points,list(end)];assert np.isfinite(points).all()
    actual=[];segments=[]
    for i,p in enumerate(points):
        hit=sweep(p,p)
        if hit:actual.append({'index':i,**hit})
    for i,(a,b) in enumerate(zip(points,points[1:])):
        hit=sweep(a,b)
        if hit:segments.append({'index':i,**hit})
    paths[identity]={'start':start,'end':end,'native_geodesic_distance':float(query.geodesic_distance),'points_with_projection_connectors':points,'start_projection_distance':math.dist(start,native_points[0]),'end_projection_distance':math.dist(end,native_points[-1]),'point_contacts':actual,'segment_contacts':segments,'source_clear':not actual and not segments}
    return identity
for key in selected:
    row=results[key];assert digest(row['result_path'])==row['sha256'];d=json.loads(Path(row['result_path']).read_text());assert d['status']=='FAILED_DIAGNOSTIC' and d['error']=="RuntimeError('legal_action_search_exhausted:5000')";t=tasks[key];n=len(d['boundaries']);target=t['targets'][n+1]
    nominal=query_path(t['targets'][n],target);remaining=query_path(d['positions'][-1],target)
    rows.append({'task_key':key,'failed_reference':n+1,'nominal_path_id':nominal,'remaining_path_id':remaining,'source_result_sha256':row['sha256']})
assert len(rows)==90
counts={'tasks':90,'unique_queries':len(paths),'nominal_source_clear_tasks':sum(paths[r['nominal_path_id']]['source_clear'] for r in rows),'remaining_source_clear_tasks':sum(paths[r['remaining_path_id']]['source_clear'] for r in rows),'unique_queries_with_point_contact':sum(bool(p['point_contacts']) for p in paths.values()),'unique_queries_with_segment_contact':sum(bool(p['segment_contacts']) for p in paths.values())}
atomic_json(O/'validation.json',{'status':'COMPLETE_ALL90_NATIVE_CORRIDOR_SOURCE_DIAGNOSIS','counts':counts,'records':rows,'paths':paths,'source_guard_manifest_sha256':digest(run/'manifest.json'),'comparison_sha256':digest(comparison),'profile_sha256':m['profile_sha256'],'source_geometry_sha256':digest(gp),'sweep_traversal_sha256':digest(helper),'script_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'Native shortest polyline/source geometry diagnostic only; includes both projection connectors. Not an actual primitive trajectory or proof that all alternative routes are impossible. No targets, heading, body, budget, geometry or runtime changed.'});print(counts)

