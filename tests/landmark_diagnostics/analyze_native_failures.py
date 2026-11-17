import json,gzip,sys,os,math,collections
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json
os.environ['CUDA_VISIBLE_DEVICES']=''
import habitat_sim
run=ROOT/'outputs/landmark-connectivity/full-native-v1';m=json.loads((run/'manifest.json').read_text());profile=json.loads(Path(m['profile_path']).read_text());tasks={t['task_key']:t for t in m['tasks']};finders={};records=[];scenes=collections.Counter();types=collections.Counter()
for p in run.glob('shard-*/*.result.json'):
 row=json.loads(p.read_text())
 if row['status']!='FAIL':continue
 t=json.load(gzip.open(run/row['trace_path'],'rt'));sc=row['scene'];error=t['errors'][0];kind=error.get('error',error['kind']);scenes[(sc,kind)]+=1;types[kind]+=1
 if sc not in finders:
  pf=habitat_sim.PathFinder();assert pf.load_nav_mesh(profile['assets'][f'mp3d/{sc}/{sc}.glb']['navmesh_path']);finders[sc]=pf
 pf=finders[sc];last=t['positions'][-1];snap=list(pf.snap_point(last));before=t['positions'][-2] if len(t['positions'])>1 else last;index=error.get('reference_index');target=t['targets'][index] if index is not None else None;q=habitat_sim.ShortestPath();q.requested_start=last;q.requested_end=target or t['targets'][-1];ok=pf.find_path(q)
 records.append({'task_key':row['task_key'],'scene':sc,'kind':kind,'last_position':last,'previous_position':before,'last_action':t['actions'][-1] if t['actions'] else None,'snap':snap,'snap_horizontal':math.hypot(snap[0]-last[0],snap[2]-last[2]),'snap_vertical':abs(snap[1]-last[1]),'step_horizontal':math.hypot(last[0]-before[0],last[2]-before[2]),'step_vertical':abs(last[1]-before[1]),'target':target,'geodesic':float(q.geodesic_distance) if ok else None,'steps':len(t['actions']),'trace_path':row['trace_path']})
r={'failure_types':dict(types),'by_scene':[{'scene':k[0],'kind':k[1],'count':v} for k,v in scenes.most_common()],'records':records};atomic_json(ROOT/'outputs/landmark-connectivity/native-failure-analysis.json',r);print(json.dumps({'failure_types':r['failure_types'],'by_scene':r['by_scene'][:15]}));print('offmesh_examples',json.dumps([x for x in records if 'offmesh' in x['kind']][:5]))
