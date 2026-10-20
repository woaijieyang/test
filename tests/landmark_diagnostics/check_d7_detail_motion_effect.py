"""Check whether coarse shortest-corridor screening observes detail-height changes."""
import datetime,json,math,os,subprocess,sys
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
import habitat_sim
B=R/'outputs/landmark-connectivity';O=B/'d7-tiled-detail01-v1';C=R/'.cache/d7-tiled-detail01-v1'
source=R/'tests/landmark_diagnostics/compare_navmesh_detail_structure.cpp';receipt=json.loads((O/'compile-command.json').read_text());command=[str(source) if x.endswith('/build_tiled_detail_scene.cpp') else x for x in receipt['command']];command[command.index('-o')+1]=str(C/'compare-structure')
with (O/'structure-compile.log').open('xb') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
result=json.loads(subprocess.check_output([str(C/'compare-structure'),str(O/'control/scene.navmesh'),str(O/'mixed/scene.navmesh')],text=True))
for field in ['set_header_identical','normalized_tile_headers_identical','tile_refs_identical','base_vertices_identical','polygons_identical','links_identical','bv_tree_identical','offmesh_connections_identical']:assert result[field]
atomic_json(O/'structure-comparison.json',{**result,'source_sha256':digest(source),'control_sha256':digest(O/'control/scene.navmesh'),'candidate_sha256':digest(O/'mixed/scene.navmesh')})
control=habitat_sim.PathFinder();candidate=habitat_sim.PathFinder();assert control.load_nav_mesh(str(O/'control/scene.navmesh')) and candidate.load_nav_mesh(str(O/'mixed/scene.navmesh'))
run=B/'full-source-guard-D7-tiled-phasehalf-v1/guarded';index={r['task_key']:r for r in json.loads((run/'validation.json').read_text())['results']};selected=json.loads((B/'D7-tiled-phasehalf-proof-comparison-v1/validation.json').read_text())['new90_failed'];assert len(selected)==90
queries={};mapping=[]
for key in selected:
    r=index[key];assert digest(r['result_path'])==r['sha256'];d=json.loads(Path(r['result_path']).read_text())
    for i,action in enumerate(d['actions']):
        if action!=1:continue
        start,end=d['positions'][i],d['positions'][i+1];identity=(tuple(start),tuple(end))
        if identity not in queries:
            a=[float(x) for x in control.try_step(start,end)];b=[float(x) for x in candidate.try_step(start,end)];assert all(math.isfinite(v) for v in a+b)
            queries[identity]={'start':start,'requested':end,'control_return':a,'candidate_return':b,'difference_m':math.dist(a,b),'vertical_difference_m':abs(a[1]-b[1]),'horizontal_difference_m':math.hypot(a[0]-b[0],a[2]-b[2])}
        mapping.append({'task_key':key,'action_index':i+1,'query_index':list(queries).index(identity)})
rows=list(queries.values());changed=[r for r in rows if r['difference_m']>1e-5]
atomic_json(O/'native-detail-effect.json',{'status':'COMPLETE_CONTROLLED_NATIVE_QUERY_EFFECT_DIAGNOSIS','tasks':90,'input_forward_edges':len(mapping),'unique_queries':len(rows),'changed_queries':len(changed),'maximum_difference_m':max(r['difference_m'] for r in rows),'queries':rows,'mapping':mapping,'structure_receipt_sha256':digest(O/'structure-comparison.json'),'script_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat(),'limits':'Same start/request vectors queried in both PathFinders. Requested vector is a saved old actualendpoint, not claimed to be the old primitive unconstrained request. Proves detail mesh affects native movement queries despite unchanged coarse graph; does not prove source safety or task success.'})
atomic_json(O/'corridor-screen-scope-review.json',{'status':'COARSE_CORRIDOR_PROXY_INSUFFICIENT_FOR_DETAIL_MOTION_EFFECT' if changed else 'NO_OBSERVED_NATIVE_EFFECT_IN_THIS_COHORT','coarse_structure_identical':True,'native_queries_changed':len(changed),'existing_source_corridor_failures_preserved':True,'reason':'findStraightPath portal geometry uses basepolygons, while native movement/getPolyHeight uses detail surface. Identical unsafe coarse corridors alone do not establish absence of native-motion improvement. All original source/motion acceptance gates remain; only the experimental run-selection proxy is corrected.','evidence_sha256':digest(O/'native-detail-effect.json')});print('STRUCTURE',result);print('NATIVE_EFFECT',len(rows),len(changed),max(r['difference_m'] for r in rows))

