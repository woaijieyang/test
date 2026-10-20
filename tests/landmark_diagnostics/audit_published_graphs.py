import os,sys,json,zipfile,collections,math
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,digest,atomic_json
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
os.environ['CUDA_VISIBLE_DEVICES']=''
import habitat_sim
archive=ROOT/'outputs/landmark-connectivity/habitat_mp3d_connectivity_graphs.zip';assert digest(archive)=='41f2a7b7803b7a751fea73657cdd57907ec3bdadb4867ad3b12aef94445e8086';z=zipfile.ZipFile(archive);raw=Path('/data/zy/vln/data/raw_data/landmark-rxr');needed=collections.defaultdict(set);rows=[]
for split in ('train','val_seen','val_unseen'):
 for row in json.loads((raw/f'LandmarkRxR_{split}.json').read_text()):
  rows.append((split,row));needed[row['scan']].update(row['path'])
report={'archive_sha256':digest(archive),'status':'PUBLISHED_ARTIFACT_AUDIT_NOT_ACCEPTANCE','scenes':[],'splits':{}}
profile=json.loads(Path('data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json').read_text());graphs={}
for sc,wanted in sorted(needed.items()):
 graph=json.loads(z.read(f'habitat_mp3d_connectivity_graphs/{sc}.json'));graphs[sc]=graph;rec={'scene':sc,'required_nodes':len(wanted),'retained_required_ids':len(wanted&set(graph['nodes'])),'missing_required_ids':sorted(wanted-set(graph['nodes'])),'published_nodes':len(graph['nodes']),'published_edges':len(graph['edges']),'checks':{}}
 for mode in ('original','case1_v2'):
  key=f'mp3d/{sc}/{sc}.glb';asset=profile['assets'].get(key) if mode=='case1_v2' else None;mesh=asset['navmesh_path'] if asset else str((ROOT/'data/scene_datasets'/key).with_suffix('.navmesh'));pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(mesh);badpoints=[n for n,pos in graph['nodes'].items() if not pf.is_navigable(pos)];badedges=[]
  for name,edge in graph['edges'].items():
   q=habitat_sim.ShortestPath();q.requested_start=edge['start_coor'];q.requested_end=edge['end_coor']
   if not pf.find_path(q) or not math.isfinite(q.geodesic_distance):badedges.append(name)
  rec['checks'][mode]={'offmesh_nodes':badpoints,'unreachable_edges':badedges,'mesh_sha256':digest(mesh)}
 report['scenes'].append(rec)
for split,row in rows:
 counts=report['splits'].setdefault(split,{'total':0,'all_original_node_ids_retained':0,'missing_one_or_more_node_ids':0});counts['total']+=1;ok=set(row['path']).issubset(graphs[row['scan']]['nodes']);counts['all_original_node_ids_retained']+=ok;counts['missing_one_or_more_node_ids']+=not ok
report['summary']={'required_nodes':sum(r['required_nodes'] for r in report['scenes']),'retained_required_ids':sum(r['retained_required_ids'] for r in report['scenes']),'published_nodes_in_71_scenes':sum(r['published_nodes'] for r in report['scenes']),'published_edges_in_71_scenes':sum(r['published_edges'] for r in report['scenes'])}
for mode in ('original','case1_v2'):report['summary'][mode]={'offmesh_nodes':sum(len(r['checks'][mode]['offmesh_nodes']) for r in report['scenes']),'unreachable_edges':sum(len(r['checks'][mode]['unreachable_edges']) for r in report['scenes'])}
report['auditor_sha256']=digest(__file__);atomic_json(ROOT/'outputs/landmark-connectivity/published-graphs-audit.json',report);print(json.dumps({'summary':report['summary'],'splits':report['splits']}))
