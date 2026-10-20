import json,os,sys,time,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
os.environ['CUDA_VISIBLE_DEVICES']=''
import habitat_sim
profilepath=Path('data/derived/navmeshes/landmark-fine-candidate-v1/profile.json')
if not profilepath.exists():raise RuntimeError('Mesh build incomplete')
profile=json.loads(profilepath.read_text());source=json.loads(Path('outputs/landmark-connectivity/candidate-nodes.json').read_text());groups=collections.defaultdict(list)
for row in source['nodes']:groups[row['scene']].append(row)
records=[];counts=collections.Counter()
for scene,rows in groups.items():
 asset=profile['assets'][f'mp3d/{scene}/{scene}.glb'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path'])
 gp=Path('outputs/landmark-connectivity/geometry')/(scene+'.json');geometry={r['node']:r for r in json.loads(gp.read_text())['nodes']} if gp.exists() else {}
 for row in rows:
  seed=row['seed'];g=geometry.get(row['node']);ground=[]
  if g:
   for hit in g['hits']:
    if hit['normal_y']>.707 and .25<=hit['camera_drop']<=2.5:ground.append(hit)
  if row['method']=='official_rxr_reference':chosen_seed=seed;method=row['method']
  elif ground:
   hit=min(ground,key=lambda h:abs(h['height']-seed[1]));chosen_seed=[seed[0],hit['height']+.02,seed[2]];method='geometry_floor_candidate'
  else:chosen_seed=seed;method='unsupported_floor_candidate'
  snap=list(pf.snap_point(chosen_seed));finite=all(math.isfinite(x) for x in snap)
  pos=chosen_seed if pf.is_navigable(chosen_seed) else snap if finite else chosen_seed
  dx=math.hypot(pos[0]-chosen_seed[0],pos[2]-chosen_seed[2]);dy=abs(pos[1]-chosen_seed[1])
  review=(method=='unsupported_floor_candidate' or not finite or dx>.25 or dy>.2)
  counts[method]+=1;counts['requires_review']+=review;counts['offmesh']+=not pf.is_navigable(pos)
  records.append({**row,'position':pos,'candidate_seed':chosen_seed,'method':method,'projection_horizontal':dx,'projection_vertical':dy,'needs_geometric_review':review,'geometry_hits':ground})
atomic_json(ROOT/'outputs/landmark-connectivity/fine-candidate-nodes.json',{'status':'DIAGNOSTIC_NOT_ACCEPTED','counts':dict(counts),'nodes':records,'profile_sha256':digest(profilepath)})
print(json.dumps(dict(counts)))
