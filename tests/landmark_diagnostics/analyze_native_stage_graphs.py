"""Reconstruct raw-stage graphs, validate against native compact data, and locate erased bridges."""
import os,sys,json,struct,collections,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
import numpy as np,psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])])
O=ROOT/'outputs/landmark-connectivity/native-stage-trace-xc-v3';v=json.loads((O/'validation.json').read_text());assert v['native_byte_control_match'];cs,ch,H,climb,radius,region,bx,by,bz=v['native_build_config'];H=int(H);climb=int(climb)
def read(name,cols):
 raw=(O/name).read_bytes();n=struct.unpack('<i',raw[:4])[0];assert len(raw)==4+n*cols*4;return np.frombuffer(raw,dtype='<i4',offset=4).reshape(n,cols).copy()
pre=read('native-1-compacted-graph.bin',11);post=read('native-1-eroded-graph.bin',11);final=read('native-1-regions-graph.bin',11);assert np.array_equal(pre[:,[0,1,2,3,4,7,8,9,10]],post[:,[0,1,2,3,4,7,8,9,10]]);assert np.array_equal(pre[:,[0,1,2,3,4,7,8,9,10]],final[:,[0,1,2,3,4,7,8,9,10]])
directions=[(-1,0),(0,1),(1,0),(0,-1)]
def adjacency(g):
 cells=collections.defaultdict(list)
 for i,row in enumerate(g):assert int(row[0])==i;cells[(int(row[1]),int(row[2]))].append(i)
 adj=np.full((len(g),4),-1,dtype=np.int32)
 for i,row in enumerate(g):
  for d,(dx,dz) in enumerate(directions):
   off=int(row[7+d])
   if off==63:continue
   neighbors=cells[(int(row[1])+dx,int(row[2])+dz)];assert 0<=off<len(neighbors);adj[i,d]=neighbors[off]
 return adj
def reconstruct(raw):
 ceil=np.full(len(raw),65535,dtype=np.int32);same=np.all(raw[:-1,:2]==raw[1:,:2],axis=1);ceil[:-1]=np.where(same,raw[1:,2],65535);sel=np.flatnonzero(raw[:,4]!=0);g=np.zeros((len(sel),11),dtype=np.int32);g[:,0]=np.arange(len(sel));g[:,1:3]=raw[sel,:2];g[:,3]=np.clip(raw[sel,3],0,65535);g[:,4]=np.clip(ceil[sel]-raw[sel,3],0,255);g[:,5]=raw[sel,4];g[:,7:]=63
 cells=collections.defaultdict(list)
 for i,row in enumerate(g):cells[(int(row[1]),int(row[2]))].append(i)
 for i,row in enumerate(g):
  x,z,y,h=map(int,row[[1,2,3,4]])
  for d,(dx,dz) in enumerate(directions):
   for layer,j in enumerate(cells.get((x+dx,z+dz),[])):
    ny,nh=map(int,g[j,[3,4]])
    if min(y+h,ny+nh)-max(y,ny)>=H and abs(y-ny)<=climb and layer<=62:g[i,7+d]=layer;break
 return g
low=read('native-1-low_height-raw.bin',5);recreated=reconstruct(low);assert np.array_equal(recreated,pre),'Independent raw-to-compact reconstruction differs from actual native arrays'
def key(row):return tuple(map(int,row[[1,2,3]]))
final_good={key(row) for row in final if row[5]!=0 and row[6]!=0}
post_valid={key(row) for row in post if row[5]!=0}
reachfile=ROOT/'outputs/landmark-connectivity/native-stage-trace-xc-v2/native-1-reachability.csv'
import csv
seedkeys={key(pre[int(r[0])]) for r in csv.reader(reachfile.open())};assert len(seedkeys)==53
def audit_graph(name,g,mask=None):
 adj=adjacency(g);ids={key(r):i for i,r in enumerate(g)};seeds=[ids[k] for k in seedkeys];valid=g[:,5]!=0 if mask is None else mask;seen=set(seeds);queue=collections.deque(seeds)
 while queue:
  i=queue.popleft()
  for j in adj[i]:
   if j>=0 and valid[j] and int(j)not in seen:seen.add(int(j));queue.append(int(j))
 goals={i for i in seen if key(g[i]) in final_good};answer={'stage':name,'spans':len(g),'reachable_from_53':len(seen),'reachable_final_region_spans':len(goals)}
 if goals:
  dist={i:0 for i in seeds};parent={};queue=collections.deque(seeds);end=None
  while queue:
   i=queue.popleft()
   if i in goals:end=i;break
   for j in adj[i]:
    j=int(j)
    if j<0 or not valid[j]:continue
    cost=int(key(g[j])not in post_valid);newcost=dist[i]+cost
    if newcost>=dist.get(j,10**9):continue
    dist[j]=newcost;parent[j]=i
    if cost:queue.append(j)
    else:queue.appendleft(j)
  assert end is not None;path=[end]
  while path[-1] in parent:path.append(parent[path[-1]])
  path.reverse();assert sum(key(g[i])not in post_valid for i in path)==dist[end]
  answer['minimum_removed_spans_on_exit_path']=dist[end];answer['path']=[{'span_key':list(key(g[i])),'world_center':[bx+(int(g[i,1])+.5)*cs,by+int(g[i,3])*ch,bz+(int(g[i,2])+.5)*cs],'survives_radius_erosion':key(g[i]) in post_valid,'final_region':key(g[i]) in final_good} for i in path]
 return answer
reports=[audit_graph('post_erosion',post)]
assert reports[0]['reachable_from_53']==53 and reports[0]['reachable_final_region_spans']==0
reports.append(audit_graph('pre_erosion',pre))
for name in ['ledge','low_hanging']:
 reports.append(audit_graph('after_'+name,reconstruct(read('native-1-'+name+'-raw.bin',5))))
atomic_json(O/'graph-cause-analysis.json',{'status':'NATIVE_GRAPH_DIAGNOSIS_NOT_ACCEPTANCE','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'native_byte_control_match':True,'raw_to_native_compact_exact_match':True,'native_validation_sha256':digest(O/'validation.json'),'script_sha256':digest(__file__),'reports':reports,'limits':'Graph paths locate filtered cells, not executable robot trajectories or geometric clearance proofs. No filters, dimensions or budgets modified.'});print([{k:v for k,v in r.items() if k!='path'} for r in reports])
