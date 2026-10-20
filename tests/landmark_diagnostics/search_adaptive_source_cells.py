"""Search the fixed pre-erosion graph with an independent source-cylinder predicate; diagnostic only."""
import os,sys,json,math,struct,collections,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
sys.path[:0]=[str(Path.cwd()/'scripts'),str(Path.cwd()/'tests/landmark_diagnostics')]
from workspace import ROOT,atomic_json,digest
from projected_distance_reference import projected_distance
import numpy as np,psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])])
O=ROOT/'outputs/landmark-connectivity/native-stage-trace-xc-v3';out=O/'source-safe-adaptive-cell-search.json';assert not out.exists();atomic_json(O/'source-safe-adaptive-cell-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
v=json.loads((O/'validation.json').read_text());assert v['native_byte_control_match'];cs,ch,H,climb,radius,region,bx,by,bz=v['native_build_config']
def read(name):
 b=(O/name).read_bytes();n=struct.unpack('<i',b[:4])[0];assert len(b)==4+n*44;return np.frombuffer(b,dtype='<i4',offset=4).reshape(n,11)
pre=read('native-1-compacted-graph.bin');post=read('native-1-regions-graph.bin');cells=collections.defaultdict(list)
for i,row in enumerate(pre):assert row[0]==i;cells[(int(row[1]),int(row[2]))].append(i)
adj=np.full((len(pre),4),-1,dtype=np.int32)
for i,row in enumerate(pre):
 for d,(dx,dz) in enumerate([(-1,0),(0,1),(1,0),(0,-1)]):
  off=int(row[7+d])
  if off!=63:adj[i,d]=cells[(int(row[1])+dx,int(row[2])+dz)][off]
points=np.column_stack((bx+(pre[:,1]+.5)*cs,by+pre[:,3]*ch,bz+(pre[:,2]+.5)*cs))
b=(O/'native-1.bin').read_bytes();nv,nt=struct.unpack('<ii',b[:8]);verts=np.frombuffer(b,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);idx=np.frombuffer(b,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=verts[idx].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1)
helper=ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';s=helper.read_text();exec(s[s.index('def clip('):s.index('records=[]')]);regioncache={};posecache={};checked=0;rejected=0
def safe(p):
 global checked,rejected
 key=tuple(float(x) for x in p)
 if key in posecache:return posecache[key]
 p=np.asarray(p);cell=tuple(math.floor(float(x)/.5) for x in p)
 if cell not in regioncache:
  low=np.array(cell)*.5;high=low+.5;regioncache[cell]=np.flatnonzero((lo[:,0]<high[0]+.1)&(hi[:,0]>low[0]-.1)&(lo[:,2]<high[2]+.1)&(hi[:,2]>low[2]-.1)&(lo[:,1]<high[1]+1.5)&(hi[:,1]>low[1]))
 checked+=1;ok=True
 for j in regioncache[cell]:
  if lo[j,0]>=p[0]+.1 or hi[j,0]<=p[0]-.1 or lo[j,2]>=p[2]+.1 or hi[j,2]<=p[2]-.1 or lo[j,1]>=p[1]+1.5 or hi[j,1]<=p[1]+1e-5:continue
  poly=clip(list(tri[j]),p[1]+1e-5,True)
  if len(poly)<3:continue
  poly=clip(poly,p[1]+1.5,False)
  if len(poly)>=3 and projected_distance(poly,p)<.1-1e-6:ok=False;rejected+=1;break
 posecache[key]=ok;return ok

import csv
from adaptive_source_cell import solve_cell
normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);length=np.linalg.norm(normal,axis=1);ny=np.divide(abs(normal[:,1]),length,out=np.zeros(len(tri)),where=length>1e-12);centers=points.copy()
initial_path=O/'frontier-subcell-analysis.json';initial=json.loads(initial_path.read_text());verification=json.loads((O/'frontier-subcell-independent-audit.json').read_text());assert verification['input_sha256']==digest(initial_path)
solved={r['span_id']:r for r in initial['records']}
for i,r in solved.items():
 if r['candidate']:points[i]=r['candidate']['position']
seeds=[int(r[0]) for r in csv.reader(next(O.glob('*-reachability.csv')).open())];assert len(seeds)==53;goals=(post[:,5]!=0)&(post[:,6]!=0);rounds=[];added=[];end=None;parent={};iteration=0
while True:
 iteration+=1;valid_seeds=[i for i in seeds if safe(points[i])];queue=collections.deque(valid_seeds);visited=set(valid_seeds);parent={};end=None;edge_blocks=0
 while queue:
  i=queue.popleft()
  if goals[i]:end=i;break
  for j in adj[i]:
   j=int(j)
   if j<0 or j in visited:continue
   if not safe(points[j]):continue
   count=max(1,math.ceil(math.dist(points[i],points[j])/.025))
   if not all(safe(points[i]+(points[j]-points[i])*k/count) for k in range(1,count)):edge_blocks+=1;continue
   parent[j]=i;visited.add(j);queue.append(j)
 if end is not None:break
 frontier={int(j) for i in visited for j in adj[i] if j>=0 and int(j) not in visited};todo=sorted(frontier-set(solved))
 rounds.append({'round':iteration,'reachable':len(visited),'frontier':len(frontier),'new_cells_to_query':len(todo),'edge_blocks':edge_blocks})
 atomic_json(O/'source-safe-adaptive-cell-state.json',{'status':'RUNNING','round':iteration,'reachable':len(visited),'new_cells_to_query':len(todo),'solved_cells':len(solved)})
 if not todo:break
 for i in todo:
  result=solve_cell(centers[i],cs,ch,tri,lo,hi,ny,clip,excluded=[points[i]])
  solved[i]={**result,'span_id':i,'span_key':pre[i,[1,2,3]].tolist(),'center':centers[i].tolist()};added.append(i)
  if result['candidate']:points[i]=result['candidate']['position']
 assert len(solved)<=len(pre)
path=[]
if end is not None:
 path=[end]
 while path[-1] in parent:path.append(parent[path[-1]])
 path.reverse()
result={'status':'SOURCE_CLEAR_ADAPTIVE_GRID_PATH_FOUND_NOT_NATIVE_MOTION' if path else 'NO_EXIT_WITH_FIXED_IN_CELL_REPRESENTATIVES','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rounds':rounds,'visited_nodes':len(visited),'source_poses_checked':checked,'source_poses_rejected':rejected,'solved_cells':len(solved),'newly_solved_cells':len(added),'source_clear_offset_cells':sum(bool(r['candidate']) for r in solved.values()),'path':[{'span_id':i,'position':points[i].tolist(),'center':centers[i].tolist(),'region':int(post[i,6])} for i in path],'cell_results':list(solved.values()),'visited_span_ids':sorted(visited),'initial_evidence_sha256':digest(initial_path),'native_geometry_sha256':digest(O/'native-1.bin'),'graph_sha256':digest(O/'native-1-compacted-graph.bin'),'cell_solver_sha256':digest(ROOT/'tests/landmark_diagnostics/adaptive_source_cell.py'),'script_sha256':digest(__file__),'limits':'One fixed representative per cell; negatives do not exhaust all continuous paths or heights. Same body, original span heights and source predicate; new points are diagnostic path positions, not changed landmarks. No mesh/profile/actions changed or task accepted.'}
atomic_json(out,result);atomic_json(O/'source-safe-adaptive-cell-state.json',{'status':result['status'],'rounds':iteration,'visited':len(visited),'solved_cells':len(solved)});print(result['status'],len(visited),len(solved))
