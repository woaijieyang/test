"""Independent native replay and native-input geometry audit for the full paired VFua cohort."""
import os,sys,json,math,struct,hashlib,argparse,datetime,re
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
P=argparse.ArgumentParser();P.add_argument('--run',required=True);P.add_argument('--scene',required=True);P.add_argument('--shard',type=int,default=0);P.add_argument('--shards',type=int,default=4);P.add_argument('--cpu',type=int,required=True);P.add_argument('--pilot',action='store_true');args=P.parse_args();assert re.fullmatch('[A-Za-z0-9]{11}',args.scene) and re.fullmatch('full-source-guard-[A-Za-z0-9-]+',args.run);os.sched_setaffinity(0,[args.cpu])
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics'),str(R/'.cache/geometry-tools')]
from workspace import atomic_json,digest
from projected_distance_reference import projected_distance
import numpy as np,habitat_sim
import habitat_sim._ext.habitat_sim_bindings as binding
from habitat_sim.utils.common import quat_from_coeffs
B=R/'outputs/landmark-connectivity';run=B/args.run;O=run/('independent-pilot' if args.pilot else 'independent');O.mkdir(exist_ok=True);out=O/f'shard-{args.shard:02}.json';assert not out.exists()
geo=json.loads((B/f'full-source-native-{args.scene}-v1/validation.json').read_text());assert geo['status']=='NATIVE_SOURCE_EXPORT_ONLY_NO_ORIGINAL_MESH_CONTROL' and geo['scene']==args.scene;gp=Path(geo['native_geometry_path']);assert digest(gp)==geo['native_geometry_sha256'];raw=gp.read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);assert len(raw)==8+nv*12+nt*12;verts=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);assert np.isfinite(verts).all() and indices.min()>=0 and indices.max()<nv;tri=verts[indices].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1)
helper=R/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';s=helper.read_text();exec(s[s.index('def clip('):s.index('records=[]')]);regions={};cache={}
def contact(p):
 key=tuple(float(x) for x in p)
 if key in cache:return cache[key]
 p=np.array(p);cell=tuple(math.floor(float(v)/.5) for v in p)
 if cell not in regions:
  low=np.array(cell)*.5;high=low+.5;regions[cell]=np.flatnonzero((lo[:,0]<high[0]+.1)&(hi[:,0]>low[0]-.1)&(lo[:,2]<high[2]+.1)&(hi[:,2]>low[2]-.1)&(lo[:,1]<high[1]+1.5)&(hi[:,1]>low[1]))
 hit=None
 for j in regions[cell]:
  if lo[j,0]>=p[0]+.1 or hi[j,0]<=p[0]-.1 or lo[j,2]>=p[2]+.1 or hi[j,2]<=p[2]-.1 or lo[j,1]>=p[1]+1.5 or hi[j,1]<=p[1]+1e-5:continue
  poly=clip(list(tri[j]),p[1]+1e-5,True)
  if len(poly)<3:continue
  poly=clip(poly,p[1]+1.5,False)
  if len(poly)>=3:
   dist=projected_distance(poly,p)
   if dist<.1-1e-6:hit={'position':p.tolist(),'triangle':int(j),'distance':dist,'maximum_height':float(max(x[1] for x in poly)-p[1])};break
 cache[key]=hit;return hit
def make(mesh):
 cfg=habitat_sim.SimulatorConfiguration();cfg.scene_id='NONE';cfg.create_renderer=False;cfg.enable_physics=False;a=habitat_sim.agent.AgentConfiguration();a.height=1.5;a.radius=.1;a.sensor_specifications=[];a.action_space={1:habitat_sim.agent.ActionSpec('move_forward',habitat_sim.agent.ActuationSpec(amount=.25)),2:habitat_sim.agent.ActionSpec('turn_left',habitat_sim.agent.ActuationSpec(amount=15)),3:habitat_sim.agent.ActionSpec('turn_right',habitat_sim.agent.ActuationSpec(amount=15))};sim=habitat_sim.Simulator(habitat_sim.Configuration(cfg,[a]));assert sim.pathfinder.load_nav_mesh(mesh);return sim
rows=[];cohort_receipts={}
for label in ['guarded']:
 cohort=run/label;m=json.loads((cohort/'manifest.json').read_text());parent_name='full-native-v11';parent_path=B/parent_name/'manifest.json';assert digest(parent_path)==m['parent_manifest_sha256'];parent=json.loads(parent_path.read_text());tasks={t['task_key']:t for t in parent['tasks'] if t['scene']==args.scene};assert len(tasks)==m['expected']
 source=cohort/('results-index.json' if args.pilot else 'validation.json');index=json.loads(source.read_text());source_rows=index if args.pilot else index['results']
 if not args.pilot:assert len(source_rows)==m['expected'] and {r['task_key'] for r in source_rows}==set(tasks);cohort_receipts[label]=digest(source)
 if args.pilot:
  chosen=[]
  for status in ['PASS_DIAGNOSTIC','FAILED_DIAGNOSTIC','STATIC_BLOCKED_PRESERVED']:
   candidates=sorted([r for r in source_rows if r['status']==status],key=lambda r:r['task_key'])
   assert candidates,('pilot class not available',label,status);chosen.append(candidates[0])
 else:chosen=[r for r in source_rows if int(hashlib.sha256(r['task_key'].encode()).hexdigest(),16)%args.shards==args.shard]
 profile=json.loads(Path(m['profile_path']).read_text());assert digest(m['profile_path'])==m['profile_sha256'];asset=profile['assets'][f'mp3d/{args.scene}/{args.scene}.glb'];assert digest(asset['navmesh_path'])==asset['navmesh_sha256'];sim=make(asset['navmesh_path'])
 for row in chosen:
  key=row['task_key'];t=tasks[key];rp=Path(row['result_path']);issues=[];observations=[];body_count=0;examples=[];maximum_replay_error=0.;actions_checked=0
  try:
   assert rp.resolve().is_relative_to(cohort.resolve());assert digest(rp)==row['sha256'];d=json.loads(rp.read_text());assert d['task_key']==key and d['source_record_sha256']==t['source_record_sha256'] and d['status']==row['status']
   if d['status']=='STATIC_BLOCKED_PRESERVED':
    assert t['status']=='STATIC_BLOCKED_PRESERVED' and d['parent_task']==t
   else:
    assert t['status']=='READY_FOR_NATIVE_MOTION' and d['status'] in ['PASS_DIAGNOSTIC','FAILED_DIAGNOSTIC'];assert d['guard_manifest_sha256']==digest(cohort/'manifest.json') and d['script_sha256']==m['worker_sha256'];assert d['native_geometry_sha256']==geo['native_geometry_sha256'];assert d['scene_sha256']==geo['scene_sha256'] and d['mesh_sha256']==asset['navmesh_sha256'];assert d['targets']==t['targets'];assert d['geometry_reference_sha256']==m['geometry_reference_sha256'];assert len(d['positions'])==len(d['actions'])+1 and len(d['actions'])<=10000 and all(a in (1,2,3) for a in d['actions']);assert np.isfinite(d['positions']).all()
    q=d['rotation'];expected=np.array([0,math.sin(-t['heading']/2),0,math.cos(-t['heading']/2)]);assert abs(abs(float(np.dot(q,expected)))-1)<1e-6
    initial=habitat_sim.AgentState();initial.position=t['targets'][0];initial.rotation=quat_from_coeffs(q);sim.initialize_agent(0,initial);actual=[sim.get_agent(0).get_state().position.tolist()];assert math.dist(actual[0],d['positions'][0])<=1e-5
    first=contact(actual[0])
    if first:body_count+=1;examples.append({'action_index':0,'fraction':0,**first})
    for i,a in enumerate(d['actions']):
     sim.step(a);p=sim.get_agent(0).get_state().position.tolist();assert all(math.isfinite(x) for x in p) and sim.pathfinder.is_navigable(p);assert abs(p[1]-actual[-1][1])<=.5;maximum_replay_error=max(maximum_replay_error,math.dist(p,d['positions'][i+1]));count=max(1,math.ceil(math.dist(actual[-1],p)/.05))
     for j in range(1,count+1):
      hit=contact(np.array(actual[-1])+(np.array(p)-actual[-1])*j/count)
      if hit:
       body_count+=1
       if len(examples)<32:examples.append({'action_index':i+1,'fraction':j/count,**hit})
     actual.append(p);actions_checked+=1
    assert maximum_replay_error<=1e-5
    prev=0;expected_indices=list(range(1,len(d['boundaries'])+1));assert [x['reference_index'] for x in d['boundaries']]==expected_indices
    for b in d['boundaries']:
     at=b['action_index'];ri=b['reference_index'];assert prev<=at<len(actual) and at-prev<=1500 and ri<len(t['targets']);prev=at;path=habitat_sim.ShortestPath();path.requested_start=actual[at];path.requested_end=t['targets'][ri];assert sim.pathfinder.find_path(path) and math.isfinite(path.geodesic_distance) and path.geodesic_distance<=.25
    assert len(d['actions'])-prev<=1500
    if d['status']=='PASS_DIAGNOSTIC':
     assert d['error'] is None and len(d['boundaries'])==len(t['targets'])-1
     if body_count:issues.append('PASS_ROW_HAS_NATIVE_SOURCE_BODY_CONTACT')
    else:
     assert d['error'];observations.append({'preserved_failure':d['error'],'recorded_prefix_only':True})
     if body_count:observations.append({'recorded_prefix_source_contacts':body_count})
  except Exception as e:issues.append(repr(e))
  rows.append({'cohort':label,'task_key':key,'producer_status':row['status'],'result_sha256':row['sha256'],'actions_replayed':actions_checked,'max_replay_error':maximum_replay_error,'source_contact_samples':body_count,'contact_examples':examples,'examples_truncated':body_count>len(examples),'audit_issues':issues,'failure_observations':observations})
  atomic_json(O/f'shard-{args.shard:02}-state.json',{'status':'RUNNING','completed_records':len(rows),'last_task':key,'cohort':label})
 sim.close()
report={'status':'AUDIT_ISSUES_FOUND' if any(r['audit_issues'] for r in rows) else 'INDEPENDENT_RECORDS_AUDITED','pilot':args.pilot,'shard':args.shard,'shards':args.shards,'rows':rows,'cohort_receipts':cohort_receipts,'native_geometry_receipt_sha256':digest(B/f'full-source-native-{args.scene}-v1/validation.json'),'native_geometry_sha256':digest(gp),'reference_geometry_sha256':digest(R/'tests/landmark_diagnostics/projected_distance_reference.py'),'script_sha256':digest(__file__),'actual_modules':{'python':sys.executable,'habitat_sim':habitat_sim.__file__,'binding':binding.__file__,'binding_sha256':digest(binding.__file__)},'limits':'Audits completed pass attempts and preserved failed prefixes independently; static/failed records remain in the denominator and none become PASS by audit. Pilot never substitutes for complete paired coverage.'};atomic_json(out,report);atomic_json(O/f'shard-{args.shard:02}-state.json',{'status':report['status'],'completed_records':len(rows),'audit_issue_rows':sum(bool(r['audit_issues']) for r in rows)});print(report['status'],len(rows),sum(bool(r['audit_issues']) for r in rows))
