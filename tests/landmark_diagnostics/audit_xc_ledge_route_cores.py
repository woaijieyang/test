"""Independently check every core and saved bridge against frozen native inputs."""
import os,sys,json,struct,collections,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
import numpy as np
O=R/'outputs/landmark-connectivity/native-stage-trace-xc-v3';D=O/'ledge-bridges-v2';v=json.loads((D/'validation.json').read_text());stage=json.loads((O/'stage-loss-v2/validation.json').read_text());after=json.loads((O/'stage-loss-v2/after_ledge.json').read_text());before=json.loads((O/'stage-loss-v2/before_ledge.json').read_text());m=json.loads((R/'outputs/landmark-connectivity/full-native-v11/manifest.json').read_text());tasks={t['task_key']:t for t in m['tasks']};wanted={r['task_key'] for r in stage['rows'] if r['classification']=='LOST_AT_LEDGE_FILTER'};assert {r['task_key'] for r in v['tasks']}==wanted and len(wanted)==42
cores=json.loads((O/'ledge-bridges-v1/route-obstruction-cores.json').read_text());assert len(cores['tasks'])==42
for r in cores['tasks']:
 nodes=list(dict.fromkeys(tasks[r['task_key']]['original_viewpoint_path']));core=nodes.copy()
 for node in nodes:
  remainder=[set(after['nodes'][n]['components']) for n in core if n!=node]
  if remainder and not set.intersection(*remainder):core.remove(node)
 assert core==r['irreducible_node_core'] and len(core)==2
 assert set.intersection(*(set(before['nodes'][n]['components']) for n in core))
 assert not set.intersection(*(set(after['nodes'][n]['components']) for n in core))
 assert all(after['nodes'][n]['components'] for n in core)
raw=(O/'native-1-low_hanging-raw.bin').read_bytes();n=struct.unpack('<i',raw[:4])[0];g=np.frombuffer(raw,dtype='<i4',offset=4).reshape(n,5);raw2=(O/'native-1-ledge-raw.bin').read_bytes();post=np.frombuffer(raw2,dtype='<i4',offset=4).reshape(n,5);assert np.array_equal(g[:,:4],post[:,:4]);ceil=np.full(n,65535,dtype=int);same=np.all(g[:-1,:2]==g[1:,:2],axis=1);ceil[:-1]=np.where(same,g[1:,2],65535)
cs,ch,H,climb,_,_,bx,by,bz=json.loads((O/'validation.json').read_text())['native_build_config']
def in_envelope(p,info):
 a=np.array(info['anchor']);p=np.array(p);delta=np.maximum(abs(p-a)-np.array([3*cs,2*ch,3*cs]),0)
 return (sum(delta[[0,2]]**2)<.25 and p[1]+2*ch>=a[1]-2 and p[1]-2*ch<=a[1]) if info['kind']=='camera_bounds' else sum(delta**2)<=.25
pairs={tuple(r['nodes']):r for r in v['pairs']};edges=0
for row in v['tasks']:assert len(row['disjoint_route_core_pairs'])==1 and tuple(row['disjoint_route_core_pairs'][0]) in pairs
for (a,b),r in pairs.items():
 assert r['status']=='PREFILTER_BRIDGE_ONLY';path=r['path'];assert in_envelope(path[0]['world_center'],before['nodes'][a]) and in_envelope(path[-1]['world_center'],before['nodes'][b]);removed=[]
 for k,node in enumerate(path):
  i=node['raw_index'];x,z,_,floor,area=map(int,g[i]);assert area!=0;expected=[bx+(x+.5)*cs,by+floor*ch,bz+(z+.5)*cs];assert np.allclose(node['world_center'],expected,atol=1e-12,rtol=0);assert node['removed_at_ledge']==bool(post[i,4]==0)
  if post[i,4]==0:removed.append(i)
  if k:
   j=path[k-1]['raw_index'];assert abs(int(g[i,0])-int(g[j,0]))+abs(int(g[i,1])-int(g[j,1]))==1;assert abs(int(g[i,3])-int(g[j,3]))<=climb;assert min(int(ceil[i]),int(ceil[j]))-max(int(g[i,3]),int(g[j,3]))>=H;edges+=1
 assert removed==r['removed_raw_indices'];assert sum(x['removed_at_ledge'] for x in path[1:])==r['minimum_removed_cost_excluding_seed']
atomic_json(D/'independent-path-audit.json',{'status':'PASS_CORE_COVERAGE_AND_NATIVE_GRAPH_PATHS','tasks':42,'unique_pairs':len(pairs),'graph_edges_checked':edges,'producer_sha256':digest(D/'validation.json'),'script_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Validates coverage, necessary-condition cores, native graph adjacency, span identities and cost accounting. Does not independently prove cost optimality or physical/navmesh traversability; acceptance remains unchanged.'});print('PASS',42,len(pairs),edges)
