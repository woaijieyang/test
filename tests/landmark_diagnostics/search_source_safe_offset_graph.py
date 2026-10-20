"""Search the fixed pre-erosion graph with an independent source-cylinder predicate; diagnostic only."""
import os,sys,json,math,struct,collections,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
sys.path[:0]=[str(Path.cwd()/'scripts'),str(Path.cwd()/'tests/landmark_diagnostics')]
from workspace import ROOT,atomic_json,digest
from projected_distance_reference import projected_distance
import numpy as np,psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])])
O=ROOT/'outputs/landmark-connectivity/native-stage-trace-xc-v3';out=O/'source-safe-grid-offset-search.json';assert not out.exists();atomic_json(O/'source-safe-offset-search-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
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
offset_receipt=O/'frontier-subcell-analysis.json';offsets=json.loads(offset_receipt.read_text());changed=[]
for r in offsets['records']:
 if not r['candidate']:continue
 i=r['span_id'];q=np.array(r['candidate']['position']);assert abs(q[0]-points[i,0])<=cs/2+1e-12 and abs(q[2]-points[i,2])<=cs/2+1e-12 and q[1]==points[i,1];points[i]=q;changed.append(i)
assert len(changed)==8

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
seeds=[int(r[0]) for r in csv.reader(next(O.glob('*-reachability.csv')).open())];assert len(seeds)==53;valid_seeds=[i for i in seeds if safe(points[i])];goals=(post[:,5]!=0)&(post[:,6]!=0);queue=collections.deque(valid_seeds);visited=set(valid_seeds);parent={};end=None;blocked_edges=0
while queue:
 i=queue.popleft()
 if goals[i]:end=i;break
 for j in adj[i]:
  j=int(j)
  if j<0 or j in visited:continue
  if not safe(points[j]):continue
  count=max(1,math.ceil(math.dist(points[i],points[j])/.025))
  if not all(safe(points[i]+(points[j]-points[i])*k/count) for k in range(1,count)):blocked_edges+=1;continue
  parent[j]=i;visited.add(j);queue.append(j)
path=[]
if end is not None:
 path=[end]
 while path[-1] in parent:path.append(parent[path[-1]])
 path.reverse()
atomic_json(out,{'status':'SOURCE_CLEAR_GRID_PATH_FOUND_NOT_NATIVE_MOTION' if path else 'NO_SOURCE_CLEAR_PATH_IN_FIXED_PRE_EROSION_GRAPH','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'offset_candidate_sha256':digest(offset_receipt),'offset_span_ids':changed,'seed_count':len(seeds),'source_clear_seeds':len(valid_seeds),'visited_nodes':len(visited),'source_poses_checked':checked,'source_poses_rejected':rejected,'source_blocked_edges':blocked_edges,'path':[{'span_id':i,'world_center':points[i].tolist(),'survives_erosion':bool(post[i,5]),'region':int(post[i,6])} for i in path],'visited_span_ids':sorted(visited),'body':{'height':1.5,'radius':.1},'sample_interval_max_m':.025,'native_validation_sha256':digest(O/'validation.json'),'native_geometry_sha256':digest(O/'native-1.bin'),'graph_sha256':digest(O/'native-1-compacted-graph.bin'),'reference_geometry_sha256':digest(ROOT/'tests/landmark_diagnostics/projected_distance_reference.py'),'script_sha256':digest(__file__),'limits':'A graph-center path, if found, is a necessary-condition diagnostic; it does not change navmesh/profile, prove all foot support or execute native0.25m/15degree actions. A failed finite grid graph does not prove source geometry physically unreachable.'});print('result',bool(path),len(visited),checked,rejected)
