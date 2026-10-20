"""Single-factor detail mesh construction, gated by native byte controls."""
import json,math,os,signal,subprocess,time
from pathlib import Path
from oracle.common.artifacts import digest,owned_output,write_json,package_sources,freeze_sources,runtime_identity


def check_single_factor(before,after):
    changed={k for k in set(before)|set(after) if before.get(k)!=after.get(k)}
    if (changed!={'detail_sample_max_error'} or not math.isclose(before['detail_sample_max_error'],1.,abs_tol=1e-7)
            or not math.isclose(after['detail_sample_max_error'],.1,abs_tol=1e-7)
            or not math.isclose(before['agent_height'],1.5,abs_tol=1e-7)
            or not math.isclose(before['agent_radius'],.1,abs_tol=1e-7)):
        raise ValueError('Only fixed detail error1to0.1 with unchanged body is permitted')


def check_control(receipt,scene_sha,binding_sha,mesh_sha,expected_mesh):
    if (receipt['scene_sha256']!=scene_sha or receipt['binding_sha256']!=binding_sha
            or receipt['mesh_sha256']!=mesh_sha or mesh_sha!=expected_mesh):
        raise ValueError('Native scene/binding/control mesh identity mismatch')


def idle_gpu():
    rows=subprocess.check_output(['nvidia-smi','--id=4,5,6,7','--query-gpu=index,uuid,memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True).splitlines()
    active=set(subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid','--format=csv,noheader'],text=True).splitlines())
    for row in rows:
        i,uuid,used,free,busy=[x.strip() for x in row.split(',')]
        if uuid not in active and int(used)<1024 and int(free)>4096 and int(busy)<10:
            return {'index':int(i),'uuid':uuid,'memory_used_mib':int(used),'memory_free_mib':int(free),'utilization_percent':int(busy)}
    raise RuntimeError('No idle authorized GPU4-7; no build launched')


def settings_record(settings):
    return {k:getattr(settings,k) for k in dir(settings) if not k.startswith('_') and type(getattr(settings,k)) in (int,float,bool)}


def run(case_root,output):
    import resource,psutil
    if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
    root=Path(case_root).resolve();out=owned_output(root,output);package,sources=package_sources()
    cfg=json.loads((package/'configs/experiments/detail_mesh_study_v1.json').read_text())
    bp=root/cfg['budget_receipt'];assert digest(bp)==cfg['budget_sha256'];budget=json.loads(bp.read_text())
    assert budget['development_after_new_reservation_seconds']+840+1800<86400
    assert budget['overall_after_new_reservation_seconds']+840+1800<2592000
    gpu=idle_gpu();os.environ['CUDA_VISIBLE_DEVICES']=str(gpu['index']);os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
    usage=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<15]
    if not idle:raise RuntimeError('No idle authorized CPU')
    cpu=min(idle,key=lambda i:usage[i]);os.sched_setaffinity(0,{cpu});os.nice(15)
    resource.setrlimit(resource.RLIMIT_CPU,(1795,1800))
    def expired(*_):raise TimeoutError('Fixed1800second construction cap')
    signal.signal(signal.SIGALRM,expired);signal.alarm(1795)
    import habitat_sim,habitat_sim._ext.habitat_sim_bindings as binding
    from oracle.verification.source_scene import SourceScene
    from oracle.research.full_worker import process_identity
    binding_sha=digest(binding.__file__)
    if binding_sha!=cfg['binding_sha256']:raise ValueError('Actual installed binding differs from historical native control')
    profile_path=root/cfg['profile'];assert digest(profile_path)==cfg['profile_sha256'];profile=json.loads(profile_path.read_text())
    cp=root/cfg['catalog'];assert digest(cp)==cfg['catalog_sha256'];catalog={x['scene']:x for x in json.loads(cp.read_text())['scenes']}
    hp=root/cfg['height_queries'];assert digest(hp)==cfg['height_queries_sha256'];height=json.loads(hp.read_text())
    pubp=root/cfg['published'];assert digest(pubp)==cfg['published_sha256'];pub={(x['scene'],x['node']):x for x in json.loads(pubp.read_text())['nodes']}
    parent=root/cfg['parent'];assert digest(parent/'manifest.json')==cfg['parent_manifest_sha256'];protocol=json.loads((parent/'manifest.json').read_text())['protocol']
    out.mkdir();freeze_sources(out,sources);write_json(out/'controller-process.json',process_identity());write_json(out/'source-freeze.json',{'status':'OPEN'})
    write_json(out/'manifest.json',{'config':cfg,'sources':sources,'gpu':gpu,'cpu':cpu,'environment':runtime_identity(),'binding':binding.__file__})
    started=time.process_time();results=[]
    def build(scene,label,parameters):
        glb=root/f'data/scene_datasets/mp3d/{scene}/{scene}.glb';assert digest(glb)==catalog[scene]['scene_sha256']
        sc=habitat_sim.SimulatorConfiguration();sc.scene_id=str(glb);sc.create_renderer=True;sc.enable_physics=False;sc.gpu_device_id=0
        agent=habitat_sim.agent.AgentConfiguration();agent.height=1.5;agent.radius=.1
        sensor=habitat_sim.SensorSpec();sensor.uuid='build';sensor.sensor_type=habitat_sim.SensorType.COLOR;sensor.resolution=[16,16];agent.sensor_specifications=[sensor]
        ns=habitat_sim.NavMeshSettings();ns.set_defaults()
        for k,v in parameters.items():setattr(ns,k,v)
        settings=settings_record(ns);mesh=out/(scene+'-'+label+'.navmesh')
        sim=habitat_sim.Simulator(habitat_sim.Configuration(sc,[agent]))
        try:
            if not sim.recompute_navmesh(sim.pathfinder,ns):raise RuntimeError('Native mesh build failed')
            if not sim.pathfinder.save_nav_mesh(str(mesh)):raise RuntimeError('Native mesh save failed')
        finally:sim.close()
        record={'scene':scene,'scene_sha256':catalog[scene]['scene_sha256'],'binding_sha256':binding_sha,
            'mesh_path':str(mesh),'mesh_sha256':digest(mesh),'settings':settings}
        write_json(out/(scene+'-'+label+'-build.json'),record);return record
    try:
        for scene in cfg['scenes']:
            asset=profile['assets']['mp3d/'+scene+'/'+scene+'.glb'];parameters=asset['build_settings']
            if not isinstance(parameters,dict):raise ValueError('Unknown source build settings cannot be guessed')
            assert digest(asset['navmesh_path'])==asset['navmesh_sha256']
            if scene=='HxpKQynjfin':
                old_path=root/cfg['hxp_control_receipt'];old=json.loads(old_path.read_text());assert old['settings']==parameters
                check_control(old,catalog[scene]['scene_sha256'],binding_sha,digest(old['mesh_path']),asset['navmesh_sha256'])
                ns=habitat_sim.NavMeshSettings();ns.set_defaults()
                for k,v in parameters.items():setattr(ns,k,v)
                control={**old,'settings':settings_record(ns),'reused_verified_control_receipt':str(old_path),'reused_receipt_sha256':digest(old_path)}
                write_json(out/(scene+'-reused-control.json'),control)
            else:
                control=build(scene,'control',parameters)
                try:check_control(control,catalog[scene]['scene_sha256'],binding_sha,control['mesh_sha256'],asset['navmesh_sha256'])
                except ValueError as error:
                    result={'scene':scene,'status':'CONTROL_MISMATCH_NO_CANDIDATE_BUILT','error':str(error),
                        'control':control,'expected_mesh_sha256':asset['navmesh_sha256'],'point_passes':0,'covered_occurrences_with_point_pass':0}
                    results.append(result);write_json(out/(scene+'-control-rejection.json'),result);continue
            candidate=build(scene,'detail01',{**parameters,'detail_sample_max_error':.1});check_single_factor(control['settings'],candidate['settings'])
            pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(candidate['mesh_path']);g=catalog[scene];source=SourceScene(g['receipt_path'],g['receipt_sha256'],protocol,catalog=g)
            points=[]
            for row in [x for x in height['reports'] if x['scene']==scene]:
                before=row['original'];q=[float(v) for v in pf.snap_point(before)];finite=all(math.isfinite(v) for v in q)
                if not finite:points.append({'task_key':row['task_key'],'finite':False,'point_pass':False,'covered_occurrences':row['covered_occurrences']});continue
                # This is snap(current), the existing rank0 seed family.
                # The horizontal extra-ring cap applies only to rank>=3.
                anchor=row['source_anchor'];bound=math.dist(q,anchor)<=.5
                if row['anchor_kind']=='bounded_camera_projection':
                    camera=pub[(scene,row['node'])]['camera_position'];bound=bound and math.hypot(q[0]-camera[0],q[2]-camera[2])<.5 and 0<=camera[1]-q[1]<=2
                floating=source.contact(q,q,certificate=True);rational=source.contact(q,q,arithmetic='rational_hull');snap=[float(v) for v in pf.snap_point(q)]
                checks={'finite':finite,'source_bound':bound,'navigable':bool(pf.is_navigable(q)),'snap_fixed':all(math.isfinite(v) for v in snap) and math.dist(q,snap)<=1e-5,'source_float_clear':floating is None,'source_rational_clear':rational is None}
                points.append({'task_key':row['task_key'],'original':before,'candidate':q,'candidate_seed_family':'existing_current_rank0','delta_y':q[1]-before[1],'checks':checks,'point_pass':all(checks.values()),'float_contact':floating,'rational_contact':rational,'covered_occurrences':row['covered_occurrences']})
            result={'scene':scene,'control_byte_match':True,'control':control,'candidate':candidate,'points':points,'point_passes':sum(x['point_pass'] for x in points),'covered_occurrences_with_point_pass':sum(len(x['covered_occurrences']) for x in points if x['point_pass'])}
            results.append(result);write_json(out/(scene+'-point-review.json'),result)
        result={'status':'COMPLETE_SINGLE_FACTOR_DETAIL_POINT_DIAGNOSTIC_NOT_ROUTE_ACCEPTANCE','scenes':results,
            'whole_route_recoveries':0,'original_data_modified':False,'profile_adopted':False,'reserved_cpu_seconds':1800,'process_cpu_seconds':time.process_time()-started,'manifest_sha256':digest(out/'manifest.json')}
        write_json(out/'validation.json',result);return result
    except BaseException as error:
        write_json(out/'failure.json',{'error':repr(error),'completed_scenes':[x['scene'] for x in results]});raise
    finally:
        signal.alarm(0);write_json(out/'source-freeze.json',{'status':'CLOSED'},immutable=False)
