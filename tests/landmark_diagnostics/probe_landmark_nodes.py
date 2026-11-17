import sys,os,json,gzip,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import digest,atomic_json,ROOT
os.environ['CUDA_VISIBLE_DEVICES']=''
import habitat_sim
mapping=json.loads(Path('outputs/landmark-connectivity/native-mapping.json').read_text());native={(r['scene'],r['node']):r['native_candidates'][0] for r in mapping['nodes']}
profile=json.loads(Path('data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json').read_text());old=json.loads(Path('outputs/landmark-connectivity/original.json').read_text());nodes=[];stats=collections.Counter()
for scene in old['scenes']:
 sc=scene['scene'];asset=profile['assets'].get(f'mp3d/{sc}/{sc}.glb');mesh=asset['navmesh_path'] if asset else scene['mesh'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(mesh)
 for r in scene['offmesh_nodes']:
  key=(sc,r['node']);camera=r['position'];seed=native.get(key)
  method='official_rxr_reference' if seed else 'camera_minus_1point5_candidate'
  if seed is None:seed=[camera[0],camera[1]-1.5,camera[2]]
  projected=list(pf.snap_point(seed))
  valid=all(math.isfinite(v) for v in projected)
  if not valid:position=seed;stats['no_snap']+=1
  elif pf.is_navigable(seed):position=seed;stats['already_navigable']+=1
  else:position=projected;stats['projected']+=1
  horizontal=math.hypot(position[0]-seed[0],position[2]-seed[2]);vertical=abs(position[1]-seed[1])
  stats[method]+=1
  if horizontal>.25 or vertical>.5:stats['large_projection']+=1
  nodes.append({'scene':sc,'node':r['node'],'position':position,'camera_position':camera,'seed':seed,'method':method,'projection_horizontal':horizontal,'projection_vertical':vertical,'needs_geometric_review':not valid or horizontal>.25 or vertical>.5})
atomic_json(ROOT/'outputs/landmark-connectivity/candidate-nodes.json',{'status':'DIAGNOSTIC_NOT_ACCEPTED','nodes':nodes,'counts':dict(stats)})
print(json.dumps(dict(stats)))
