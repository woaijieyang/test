"""Join Landmark annotations to official RxR-CE without creating or relocating any point."""
import sys,os,json,gzip,hashlib,collections,math,datetime
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Protected launcher required')
os.environ['CUDA_VISIBLE_DEVICES']=''
import habitat_sim
raw=Path('/data/zy/vln/data/raw_data/landmark-rxr');ce=Path('/data/zy/vln/data/raw_data/eval_annotations/rxr_vlnce_v0');profile=json.loads(Path('data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json').read_text());finders={};report={'status':'CORRESPONDENCE_AUDIT_NOT_NAVIGATION_ACCEPTANCE','splits':{},'sources':[],'records':[]}
def finder(scene):
 if scene not in finders:
  asset=profile['assets'].get(scene);mesh=asset['navmesh_path'] if asset else str((ROOT/'data/scene_datasets'/scene).with_suffix('.navmesh'));pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(mesh);finders[scene]=pf
 return finders[scene]
def connected(pf,a,b):
 q=habitat_sim.ShortestPath();q.requested_start=a;q.requested_end=b;return bool(pf.find_path(q)) and math.isfinite(q.geodesic_distance)
for split in ('train','val_seen','val_unseen'):
 source=raw/f'LandmarkRxR_{split}.json';official=ce/split/f'{split}_guide.json.gz';rows=json.loads(source.read_text());episodes=json.load(gzip.open(official,'rt'))['episodes'];epmap={str(e['instruction']['instruction_id']):e for e in episodes};assert len(epmap)==len(episodes);counts=collections.Counter()
 report['sources']+= [{'path':str(p),'sha256':digest(p)} for p in (source,official)]
 for row in rows:
  key=str(row['instruction_id']);record={'split':split,'instruction_id':key,'path_id':str(row['path_id']),'scene':row['scan']};counts['total']+=1;e=epmap.get(key)
  if e is None:counts['not_in_official_ce']+=1;record['mapping_status']='NO_OFFICIAL_CE_EPISODE';report['records'].append(record);continue
  counts['matched']+=1;issues=[];expected_scene=f"mp3d/{row['scan']}/{row['scan']}.glb"
  if e['scene_id']!=expected_scene:issues.append('scene_mismatch')
  if str(e['trajectory_id'])!=str(row['path_id']):issues.append('path_id_mismatch')
  if e['instruction']['instruction_text']!=row['instruction']:issues.append('instruction_text_mismatch')
  if len(e['reference_path'])!=len(row['path']):issues.append('reference_count_mismatch')
  if issues:record['mapping_status']='IDENTITY_MISMATCH';record['issues']=issues;counts['identity_mismatch']+=1;report['records'].append(record);continue
  positions=e['reference_path'];segments=[]
  for i,sub in enumerate(row['sub_paths']):
   bounds=[j for j in range(len(row['path'])-len(sub)+1) if row['path'][j:j+len(sub)]==sub]
   if len(bounds)!=1:issues.append('ambiguous_subpath_'+str(i));continue
   start=bounds[0];end=start+len(sub)-1;segments.append({'segment_index':i,'start_index':start,'end_index':end,'start_position':positions[start],'end_position':positions[end]})
  pf=finder(e['scene_id']);bad_nodes=[i for i,pos in enumerate(positions) if not pf.is_navigable(pos)];bad_edges=[i for i,(a,b) in enumerate(zip(positions,positions[1:])) if not connected(pf,a,b)];bad_segments=[s['segment_index'] for s in segments if not connected(pf,s['start_position'],s['end_position'])]
  counts['matched_with_offmesh_reference']+=bool(bad_nodes);counts['matched_with_unreachable_reference']+=bool(bad_edges or bad_segments);counts['matched_with_offmesh_endpoints']+=not(pf.is_navigable(e['start_position']) and all(pf.is_navigable(g['position']) for g in e['goals']))
  record.update(mapping_status='EXACT_IDENTITY_AND_SUBPATH_MAPPING' if not issues else 'AMBIGUOUS_SUBPATH',ce_episode_id=str(e['episode_id']),segments=segments,issues=issues,offmesh_reference_indices=bad_nodes,unreachable_edges=bad_edges,unreachable_segments=bad_segments)
  report['records'].append(record)
 report['splits'][split]=dict(counts);print(split,dict(counts),flush=True)
report['auditor_sha256']=digest(__file__);report['profile_sha256']=digest('data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json');report['time']=datetime.datetime.now(datetime.timezone.utc).isoformat();report['limits']='Original official RxR-CE reference positions used verbatim; no endpoint9 correction, nearest-point relocation, dropped source rows, or geometry edits. Matched identities are not a whole-dataset navigation PASS.'
atomic_json(ROOT/'outputs/landmark-connectivity/official-correspondence.json',report)
