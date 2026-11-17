"""Determine whether eligible Follower seeds add a component beyond unchanged original proposals."""
import os,sys,json,math,collections,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
import habitat_sim
B=R/'outputs/landmark-connectivity';O=B/'follower-seed-existing-bounds-v1';source=O/'validation.json';d=json.loads(source.read_text());parent=json.loads((B/'full-native-v11/manifest.json').read_text());assert digest(B/'full-native-v11/manifest.json')==d['parent_manifest_sha256'];profile=json.loads(Path(parent['profile_path']).read_text());identity={(r['scene'],r['node']):r for r in json.loads((B/'published-identity-nodes.json').read_text())['nodes']};finders={};rows=[];rings=[(r*math.cos(i*2*math.pi/n),r*math.sin(i*2*math.pi/n)) for r,n in ((.1,18),(.15,30),(.2,36),(.25,48),(.3,60),(.35,72)) for i in range(n)]
for row in d['records']:
 if row['reasons']:continue
 scene=row['scene'];node=row['node'];anchor=row['existing_anchor'];kind=row['existing_anchor_kind'];assert anchor is not None
 if scene not in finders:
  asset=profile['assets'][f'mp3d/{scene}/{scene}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(asset['navmesh_path']);finders[scene]=pf
 pf=finders[scene];q=row['projected_candidate'];seeds=[]
 if row['previous'] is not None:seeds.append((0,row['previous']))
 if row['current'] is not None:seeds.append((1,row['current']))
 seeds.append((2,anchor));seeds.extend((3,[anchor[0]+dx,anchor[1],anchor[2]+dz]) for dx,dz in rings);seen=set();witness=None;tested=0
 for rank,seed in seeds:
  p=list(pf.snap_point(seed));key=tuple(p)
  if key in seen:continue
  seen.add(key)
  if not all(math.isfinite(x) for x in p) or not pf.is_navigable(p) or math.dist(p,list(pf.snap_point(p)))>1e-5:continue
  if math.dist(p,anchor)>.5 or (rank==3 and math.hypot(p[0]-anchor[0],p[2]-anchor[2])>.350001):continue
  if kind=='bounded_camera_projection':
   camera=identity[(scene,node)]['camera_position']
   if math.hypot(p[0]-camera[0],p[2]-camera[2])>=.5 or not 0<=camera[1]-p[1]<=2:continue
  tested+=1;path=habitat_sim.ShortestPath();path.requested_start=p;path.requested_end=q
  if pf.find_path(path) and math.isfinite(path.geodesic_distance):witness={'rank':rank,'seed':seed,'actual_projected_point':p,'finite_geodesic_to_follower_seed':float(path.geodesic_distance)};break
 rows.append({'scene':scene,'node':node,'status':'COMPONENT_ALREADY_REPRESENTED_BY_EXISTING_BOUNDED_PROPOSALS' if witness else 'POTENTIAL_NEW_COMPONENT_REQUIRES_JOINT_AUDIT','existing_component_witness':witness,'tested_valid_existing_proposals':tested,'task_occurrences':row['task_occurrences']})
assert len(rows)==d['eligible_contexts'];new=[r for r in rows if r['existing_component_witness'] is None];p=O/'component-novelty.json';assert not p.exists();atomic_json(p,{'status':'COMPLETE_NATIVE_COMPONENT_NOVELTY_AUDIT_NOT_REPAIR','eligible_contexts':len(rows),'already_represented':len(rows)-len(new),'potential_new_components':len(new),'potentially_affected_tasks':len({t['task_key'] for r in new for t in r['task_occurrences']}),'records':rows,'eligibility_sha256':digest(source),'parent_manifest_sha256':d['parent_manifest_sha256'],'script_sha256':digest(__file__),'limits':'Original frozen mapper was native membership/source bounds, not full source-body certification. Existing witnesses use exactly those source bounds, without claiming body clearance. An extra point in an already available component cannot change the old component intersection; it may still be useful for separate source-body trajectory research. No target identity upgrade or record deletion.'});print('newcomponents',len(new),'of',len(rows))
