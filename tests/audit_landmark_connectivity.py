"""Audit raw Landmark-RxR node paths against continuous Habitat navigation meshes."""
import argparse,collections,datetime,gzip,hashlib,json,math,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from workspace import ROOT,owned,atomic_json,digest

def main():
 p=argparse.ArgumentParser();p.add_argument('--profile');p.add_argument('--node-overlay');p.add_argument('--output',required=True);a=p.parse_args()
 if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected runtime required')
 os.environ['CUDA_VISIBLE_DEVICES']=''
 import habitat_sim
 raw=Path('/data/zy/vln/data/raw_data/landmark-rxr');legacy=Path('/data/zy/vln/runs/landmark-rxr')
 manifest=json.loads((legacy/'inputs_manifest.json').read_text())
 profile=json.loads(Path(a.profile).read_text()) if a.profile else {'assets':{}}
 nodes={};rows_by_scene=collections.defaultdict(list);sources=[];split_counts={};structural=[]
 for split,expected in [('train',26464),('val_seen',2939),('val_unseen',4551)]:
  source=raw/f'LandmarkRxR_{split}.json';sha=digest(source)
  if sha!=manifest['splits'][split]['source_sha256']:raise RuntimeError('Source identity mismatch')
  rows=json.loads(source.read_text());assert len(rows)==expected
  joins={}
  joinpath=legacy/'join'/f'{split}.jsonl.gz'
  with gzip.open(joinpath,'rt') as stream:
   for line in stream:
    j=json.loads(line);k=str(j['landmark_record']['instruction_id'])
    if k in joins:raise RuntimeError('Duplicate join')
    joins[k]=j
  assert len(joins)==len(rows)
  for row in rows:
   key=str(row['instruction_id']);j=joins[key]
   if row!=j['landmark_record']:raise RuntimeError('Raw/join mismatch')
   if len(row['path'])!=len(j['reference_path']):raise RuntimeError('Node mapping mismatch')
   scene=row['scan']
   for node,position in zip(row['path'],j['reference_path']):
    nk=(scene,node);position=tuple(position)
    if nk in nodes and nodes[nk]!=position:raise RuntimeError('Inconsistent shared-node mapping')
    nodes[nk]=position
   rows_by_scene[scene].append((split,row))
  split_counts[split]={'episodes':len(rows),'subpaths':sum(len(r['sub_paths']) for r in rows)}
  sources.extend([{'path':str(source),'sha256':sha},{'path':str(joinpath),'sha256':digest(joinpath)}])
 if a.node_overlay:
  overlay=json.loads(Path(a.node_overlay).read_text());overrides={(r['scene'],r['node']):tuple(r['position']) for r in overlay['nodes']}
  if set(overrides)!=set(nodes):raise RuntimeError('Overlay must cover exact nodes')
  nodes=overrides
 errors=[];scene_reports=[];affected=collections.Counter();pair_count=0
 for scene,rows in sorted(rows_by_scene.items()):
  scene_id=f'mp3d/{scene}/{scene}.glb';asset=profile['assets'].get(scene_id)
  mesh=Path(asset['navmesh_path']) if asset else ROOT/f'data/scene_datasets/mp3d/{scene}/{scene}.navmesh'
  meshsha=digest(mesh)
  if asset and meshsha!=asset['navmesh_sha256']:raise RuntimeError('Mesh identity drift')
  pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(str(mesh))
  points={node:pos for (sc,node),pos in nodes.items() if sc==scene};bad={};cache={}
  for node,pos in points.items():
   if not pf.is_navigable(pos):
    snap=list(pf.snap_point(pos));bad[node]={'node':node,'position':pos,'snap':[v if math.isfinite(v) else None for v in snap],'distance':math.dist(pos,snap) if all(math.isfinite(v) for v in snap) else None}
  def reachable(n1,n2):
   k=(n1,n2)
   if k not in cache:
    if n1 not in points or n2 not in points:raise RuntimeError('Missing subpath node mapping')
    q=habitat_sim.ShortestPath();q.requested_start=points[n1];q.requested_end=points[n2]
    cache[k]=bool(pf.find_path(q)) and math.isfinite(q.geodesic_distance)
   return cache[k]
  scene_bad=[]
  for split,row in rows:
   reasons=[];paths=[('full',row['path'])]+[(f'subpath:{i}',v) for i,v in enumerate(row['sub_paths'])]
   for label,path in paths:
    if not path:reasons.append({'kind':'empty_path','section':label});continue
    for index,node in enumerate(path):
     if node in bad:reasons.append({'kind':'offmesh_node','section':label,'index':index,'node':node})
    for i,(start,end) in enumerate(zip(path,path[1:])):
     if not reachable(start,end):reasons.append({'kind':'unreachable_edge','section':label,'index':i,'start':start,'end':end})
    if not reachable(path[0],path[-1]):reasons.append({'kind':'unreachable_endpoints','section':label})
   if reasons:
    item={'split':split,'instruction_id':str(row['instruction_id']),'scene':scene,'reasons':reasons};errors.append(item);scene_bad.append(item);affected[split]+=1
  pair_count+=len(cache)
  report={'scene':scene,'mesh':str(mesh),'mesh_sha256':meshsha,'episodes':len(rows),'unique_nodes':len(points),'offmesh_nodes':list(bad.values()),'unreachable_unique_pairs':sum(not x for x in cache.values()),'unique_path_queries':len(cache),'affected_episodes':len(scene_bad)}
  scene_reports.append(report)
  print(json.dumps({k:report[k] for k in ('scene','episodes','unique_nodes','unreachable_unique_pairs','affected_episodes')}),flush=True)
 report={'status':'FAIL' if errors else 'PASS','scope':'all_raw_LandmarkRxR_full_and_subpaths_three_splits','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'split_counts':split_counts,'episodes':sum(x['episodes'] for x in split_counts.values()),'subpaths':sum(x['subpaths'] for x in split_counts.values()),'scenes':scene_reports,'unique_path_queries':pair_count,'affected_episodes':dict(affected),'errors':errors,'sources':sources,'auditor_sha256':digest(__file__),'profile_sha256':digest(a.profile) if a.profile else None,'node_overlay_sha256':digest(a.node_overlay) if a.node_overlay else None,'limits':'Raw viewpoint identities and instructions preserved; mapping independently matched to all raw records. is_navigable checked on every unique full/subpath node, finite paths on each edge and each path endpoints. No model rollout or arbitrary-space guarantee.'}
 atomic_json(owned(a.output),report)
 print(json.dumps({k:report[k] for k in ('status','episodes','subpaths','affected_episodes','unique_path_queries')}))
if __name__=='__main__':main()
