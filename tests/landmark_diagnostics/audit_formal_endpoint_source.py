"""Complete formal endpoint source-cylinder audit, keeping raw and float32 coordinates."""
import ast,collections,datetime,json,os,struct,sys,time
from pathlib import Path
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from preflight import SPECS,dataset_base,load,task_key
from swept_cylinder_reference import triangle_linear_sweep_distance
from cylinder_contact_height import contact_height_range
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
import numpy as np,psutil,habitat_sim
while True:
    u=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<10 and i not in [1,2,6,7,8,12,18,20,22,24,27,30]]
    if idle:os.sched_setaffinity(0,[min(idle,key=lambda i:u[i])]);break
    time.sleep(30)
O=R/'outputs/connectivity/formal-endpoint-source-v1';O.mkdir(exist_ok=False);(O/'scenes').mkdir()
atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'cpu':list(os.sched_getaffinity(0))})
def note(status,**kw):atomic_json(O/'state.json',{'status':status,'time':datetime.datetime.now().astimezone().isoformat(),**kw})
try:
    profile_path=R/'data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json';profile=json.loads(profile_path.read_text());assert profile['agent']=={'height':1.5,'radius':.1}
    catalog_path=R/'outputs/landmark-connectivity/native-source-catalog-v1/catalog.json';catalog={r['scene']:r for r in json.loads(catalog_path.read_text())['scenes']}
    helper=R/'tests/landmark_diagnostics/audit_prb_step_interpretations.py';prior=json.loads((R/'outputs/landmark-connectivity/pRb-original-trace-step-interpretation-v1/validation.json').read_text());assert digest(helper)==prior['script_sha256']
    functions=[n for n in ast.parse(helper.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='sweep'];assert len(functions)==1;exec(compile(ast.Module(body=functions,type_ignores=[]),str(helper),'exec'),globals())
    scene_jobs=collections.defaultdict(list);datasets={};keys=set()
    for dataset,spec in SPECS.items():
        path=dataset_base(dataset)/spec[1];episodes=[e for e in load(path)['episodes'] if dataset!='rxr' or e['instruction']['language']=='en-US'];assert len(episodes)==spec[3]
        datasets[dataset]={'annotation_path':str(path),'annotation_sha256':digest(path),'expected':len(episodes)}
        for ep in episodes:
            key=task_key(dataset,ep);assert key not in keys;keys.add(key)
            points=[('start',ep['start_position'])]+[(f'goal:{i}',g['position']) for i,g in enumerate(ep['goals'])]
            scene_jobs[ep['scene_id']].append({'task_key':key,'dataset':dataset,'points':points})
    assert len(keys)==3062
    atomic_json(O/'manifest.json',{'profile_path':str(profile_path),'profile_sha256':digest(profile_path),'datasets':datasets,'expected_tasks':sorted(keys),'expected_endpoints':sum(len(t['points']) for tasks in scene_jobs.values() for t in tasks),'scene_count':len(scene_jobs),'catalog_sha256':digest(catalog_path),'script_sha256':digest(__file__),'sweep_traversal_sha256':digest(helper),'sweep_math_sha256':digest(R/'tests/landmark_diagnostics/swept_cylinder_reference.py'),'height_helper_sha256':digest(R/'tests/landmark_diagnostics/cylinder_contact_height.py'),'limits':'No source or derived annotation modifications. Raw coordinates and native float32 quantization checked independently. Source geometry body/endpoint check, not route or model evaluation.'})
    reports=[];task_failures=set();counts=collections.Counter()
    for scene_id,jobs in sorted(scene_jobs.items()):
        scene=scene_id.split('/')[1];native=catalog[scene];rp=Path(native['receipt_path']);receipt=json.loads(rp.read_text());asset=profile['assets'][scene_id]
        assert receipt['scene']==scene and receipt['scene_sha256']==asset['scene_sha256']
        gp=Path(receipt['native_geometry_path']);assert digest(gp)==receipt['native_geometry_sha256'];raw=gp.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);assert len(raw)==8+12*nv+12*nt
        vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vertices[indices].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);cache={};regions={}
        assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path'])
        rows=[]
        for task in jobs:
            for kind,raw_point in task['points']:
                point=np.asarray(raw_point,dtype=float);quantized=point.astype(np.float32).astype(float);assert np.isfinite(point).all()
                contact=sweep(point,point);native_contact=sweep(quantized,quantized)
                height=None if contact is None else contact_height_range(tri[contact['native_triangle']],point)
                if contact is not None or native_contact is not None:task_failures.add(task['task_key'])
                counts['endpoints']+=1;counts['raw_source_contacts']+=contact is not None;counts['float32_source_contacts']+=native_contact is not None;counts['classification_disagreements']+=(contact is None)!=(native_contact is None)
                counts['native_offmesh']+=not pf.is_navigable(point)
                rows.append({'task_key':task['task_key'],'dataset':task['dataset'],'kind':kind,'position':point.tolist(),'native_float32_position':quantized.tolist(),'native_navigable':bool(pf.is_navigable(point)),'raw_contact':contact,'float32_contact':native_contact,'raw_first_contact_height':height})
        output=O/'scenes'/(scene+'.json');atomic_json(output,{'scene':scene,'tasks':len(jobs),'records':rows,'native_geometry_sha256':digest(gp),'native_geometry_receipt_sha256':digest(rp),'navmesh_sha256':asset['navmesh_sha256']})
        reports.append({'scene':scene,'tasks':len(jobs),'endpoints':len(rows),'raw_contact_endpoints':sum(r['raw_contact'] is not None for r in rows),'affected_tasks':len({r['task_key'] for r in rows if r['raw_contact'] is not None or r['float32_contact'] is not None}),'receipt_path':str(output),'receipt_sha256':digest(output)})
        note('RUNNING_FULL_ENDPOINT_SOURCE_AUDIT',completed_scenes=len(reports),expected_scenes=len(scene_jobs),counts=dict(counts))
    assert counts['endpoints']==json.loads((O/'manifest.json').read_text())['expected_endpoints']
    atomic_json(O/'validation.json',{'status':'COMPLETE_ENDPOINT_SOURCE_AUDIT_WITH_FAILURES' if task_failures else 'PASS_ALL_ENDPOINT_SOURCE_BODY','expected_tasks':3062,'counts':dict(counts),'affected_tasks':sorted(task_failures),'affected_task_count':len(task_failures),'scenes':reports,'manifest_sha256':digest(O/'manifest.json'),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'Complete endpoints only. Positive first triangle retained; absence of endpoint contact does not prove route sweeps. Low contact remains failure; no support/step protocol change or annotation edit authorized by this audit.'})
    note('COMPLETE_ENDPOINT_SOURCE_AUDIT',counts=dict(counts),affected_tasks=len(task_failures))
except Exception as error:note('FAILED_ENDPOINT_SOURCE_AUDIT',error=repr(error));raise

