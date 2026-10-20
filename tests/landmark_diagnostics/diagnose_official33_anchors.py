import os,sys,json,gzip,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[10:11]);os.nice(10)
import habitat_sim
b=ROOT/'outputs/landmark-connectivity';alignment=json.loads((b/'official-GT-alignment.json').read_text());matched={r['split']+':'+str(r['instruction_id']):r for r in alignment['records'] if 'ce_episode_id' in r};blocked=[r for r in json.loads((b/'remaining-static-v4-causes.json').read_text())['records'] if r['task_key'] in matched];m=json.loads((b/'full-native-v4/manifest.json').read_text());tasks={t['task_key']:t for t in m['tasks']};profile=json.loads(Path(m['profile_path']).read_text());native={(x['scene'],x['node']):x['native_candidates'][0] for x in json.loads((b/'native-mapping.json').read_text())['nodes']};result=[];sources=[]
for split in sorted({tasks[r['task_key']]['split'] for r in blocked}):
 base=ROOT/f'data/datasets/RxR_VLNCE_v0/{split}';ep=base/f'{split}_guide.json.gz';gp=base/f'{split}_guide_gt.json.gz';eps={str(e['instruction']['instruction_id']):e for e in json.load(gzip.open(ep,'rt'))['episodes']};gt=json.load(gzip.open(gp,'rt'));sources += [{'path':str(p),'sha256':digest(p)} for p in [ep,gp]]
 for r in blocked:
  t=tasks[r['task_key']]
  if t['split']!=split:continue
  e=eps[t['instruction_id']];locations=gt[str(e['episode_id'])]['locations'];sc=t['scene'];meshes={'original':ROOT/f'data/scene_datasets/mp3d/{sc}/{sc}.navmesh','candidate':Path(profile['assets'][f'mp3d/{sc}/{sc}.glb']['navmesh_path'])};rows=[]
  for node in r['missing_nodes']:
   i=t['original_viewpoint_path'].index(node);p=e['reference_path'][i];assert math.dist(p,native[(sc,node)])<1e-5;row={'node':node,'reference_index':i,'reference':p,'minimum_official_GT_distance':min(math.dist(p,q) for q in locations),'official_start':e['start_position'],'first_GT':locations[0],'meshes':{}}
   for name,mp in meshes.items():
    pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(str(mp));q=list(pf.snap_point(p));finite=all(math.isfinite(x) for x in q);row['meshes'][name]={'source_is_navigable':pf.is_navigable(p),'snap':q if finite else None,'snap_distance':math.dist(p,q) if finite else None,'mesh_sha256':digest(mp),'nearest_GT_snap_distance':min((math.dist(p,list(pf.snap_point(x))) for x in locations if all(math.isfinite(v) for v in pf.snap_point(x))),default=None)}
   rows.append(row)
  result.append({'task_key':t['task_key'],'scene':sc,'ce_episode_id':str(e['episode_id']),'missing_nodes':rows})
atomic_json(b/'official33-anchor-diagnostic.json',{'status':'DIAGNOSTIC_ONLY','records':result,'sources':sources,'script_sha256':digest(__file__),'limits':'Distances diagnose source reference and mesh mismatch; no changed bound, new mapping or acceptance.'})
for sc,node in sorted({(r['scene'],n['node']) for r in result for n in r['missing_nodes']}):
 rows=[n for r in result if r['scene']==sc for n in r['missing_nodes'] if n['node']==node];print(sc,node,len(rows),json.dumps(rows[0]),flush=True)
