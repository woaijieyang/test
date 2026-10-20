"""Locate exact native ledge removals on pre-filter bridges; never changes a mesh."""
import os,sys,json,ast,collections,struct,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15);os.environ['CUDA_VISIBLE_DEVICES']=''
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'.cache/geometry-tools')]
import numpy as np,psutil
from workspace import atomic_json,digest
u=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:u[i])])
O=R/'outputs/landmark-connectivity/native-stage-trace-xc-v3';D=O/'ledge-bridges-v1';D.mkdir(exist_ok=False)
atomic_json(D/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
v=json.loads((O/'validation.json').read_text());assert v['native_byte_control_match'];cs,ch,H,climb,radius,region,bx,by,bz=v['native_build_config'];H=int(H);climb=int(climb)
dirs=[(-1,0),(0,1),(1,0),(0,-1)];helper=R/'tests/landmark_diagnostics/analyze_native_stage_graphs.py';tree=ast.parse(helper.read_text());ns={'O':O,'np':np,'struct':struct,'collections':collections,'H':H,'climb':climb,'directions':dirs};exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['read','reconstruct','adjacency']],type_ignores=[]),str(helper),'exec'),ns)
raw=ns['read']('native-1-low_hanging-raw.bin',5);after=ns['read']('native-1-ledge-raw.bin',5);assert np.array_equal(raw[:,:4],after[:,:4]);g=ns['reconstruct'](raw);adj=ns['adjacency'](g)
cells=collections.defaultdict(list)
for i,row in enumerate(raw):cells[tuple(map(int,row[:2]))].append(i)
width=int(raw[:,0].max())+1;depth=int(raw[:,1].max())+1
ceil=np.full(len(raw),65535,dtype=int);same=np.all(raw[:-1,:2]==raw[1:,:2],axis=1);ceil[:-1]=np.where(same,raw[1:,2],65535)
def ledge(i):
 x,z,smin,bot,area=map(int,raw[i]);top=int(ceil[i]);minh=65535;asmin=asmax=bot;witness=[]
 for d,(dx,dz) in enumerate(dirs):
  xx,zz=x+dx,z+dz
  if not(0<=xx<width and 0<=zz<depth):minh=min(minh,-climb-bot);witness.append({'dir':d,'outside':True,'drop':-climb-bot});continue
  neighbors=cells.get((xx,zz),[]);nbot=-climb;ntop=int(raw[neighbors[0],2]) if neighbors else 65535
  if min(top,ntop)-max(bot,nbot)>H:minh=min(minh,nbot-bot);witness.append({'dir':d,'under_first':True,'drop':nbot-bot})
  for j in neighbors:
   nbot=int(raw[j,3]);ntop=int(ceil[j]);gap=min(top,ntop)-max(bot,nbot)
   if gap>H:
    minh=min(minh,nbot-bot)
    if abs(nbot-bot)<=climb:asmin=min(asmin,nbot);asmax=max(asmax,nbot)
    if nbot-bot < -climb:witness.append({'dir':d,'neighbor_raw_index':j,'drop':nbot-bot,'clearance':gap})
 return {'reason':'DROP_EXCEEDS_CLIMB' if minh < -climb else 'ACCESSIBLE_NEIGHBOR_HEIGHT_RANGE' if asmax-asmin>climb else 'RETAIN','minimum_neighbor_delta':minh,'accessible_height_range':asmax-asmin,'witness':witness}
removed=np.flatnonzero((raw[:,4]!=0)&(after[:,4]==0));mismatch=[];counts=collections.Counter()
for i in np.flatnonzero(raw[:,4]!=0):
 info=ledge(int(i));expect=info['reason']!='RETAIN';actual=after[i,4]==0;counts[info['reason']]+=1
 if expect!=actual:mismatch.append(int(i))
assert not mismatch,('ledge reconstruction mismatch',mismatch[:20]);atomic_json(D/'filter-control.json',{'full_native_filter_matches':True,'walkable_spans_checked':int(np.sum(raw[:,4]!=0)),'removed':len(removed),'counts':dict(counts),'raw_sha256':digest(O/'native-1-low_hanging-raw.bin'),'after_sha256':digest(O/'native-1-ledge-raw.bin')})
keys={tuple(map(int,row[[0,1,3]])):i for i,row in enumerate(raw)};graw=np.array([keys[tuple(map(int,row[[1,2,3]]))] for row in g]);deleted=after[graw,4]==0
positions=np.column_stack((bx+(g[:,1]+.5)*cs,by+g[:,3]*ch,bz+(g[:,2]+.5)*cs))
before=json.loads((O/'stage-loss-v2/before_ledge.json').read_text());post=json.loads((O/'stage-loss-v2/after_ledge.json').read_text());classes=json.loads((O/'stage-loss-v2/validation.json').read_text());wanted={r['task_key'] for r in classes['rows'] if r['classification']=='LOST_AT_LEDGE_FILTER'};m=json.loads((R/'outputs/landmark-connectivity/full-native-v11/manifest.json').read_text());tasks=[t for t in m['tasks'] if t['task_key'] in wanted];assert len(tasks)==42
cache={}
def options(node):
 if node not in cache:
  info=before['nodes'][node];a=np.array(info['anchor']);delta=np.maximum(abs(positions-a)-np.array([3*cs,2*ch,3*cs]),0)
  if info['kind']=='camera_bounds':mask=(np.sum(delta[:,[0,2]]**2,axis=1)<.25)&(positions[:,1]+2*ch>=a[1]-2)&(positions[:,1]-2*ch<=a[1])
  else:mask=np.sum(delta**2,axis=1)<=.25
  cache[node]=np.flatnonzero(mask).tolist()
 return cache[node]
pair_results={};task_rows=[];all_deleted=set()
for t in tasks:
 nodes=t['original_viewpoint_path'];pairs=[]
 for a,b in zip(nodes,nodes[1:]):
  if set(post['nodes'][a]['components']) & set(post['nodes'][b]['components']):continue
  pair=(a,b)
  if pair not in pair_results:
   starts=options(a);goals=set(options(b));dist={i:0 for i in starts};parent={};q=collections.deque(starts);end=None
   while q:
    i=q.popleft()
    if i in goals:end=i;break
    for j in adj[i]:
     j=int(j)
     if j<0:continue
     weight=int(deleted[j]);nd=dist[i]+weight
     if nd>=dist.get(j,10**9):continue
     dist[j]=nd;parent[j]=i
     if weight:q.append(j)
     else:q.appendleft(j)
   if end is None:result={'status':'NO_DIRECTED_PREFILTER_PATH','visited':len(dist)}
   else:
    path=[end]
    while path[-1] in parent:path.append(parent[path[-1]])
    path.reverse();removed_ids=[int(graw[i]) for i in path if deleted[i]];all_deleted.update(removed_ids);result={'status':'PREFILTER_BRIDGE_ONLY','minimum_removed_cost_excluding_seed':dist[end],'path':[{'raw_index':int(graw[i]),'world_center':positions[i].tolist(),'removed_at_ledge':bool(deleted[i])} for i in path],'removed_raw_indices':removed_ids}
   pair_results[pair]=result
  pairs.append(list(pair))
 task_rows.append({'task_key':t['task_key'],'disjoint_adjacent_pairs':pairs,'limits':'If no adjacent pair is disjoint, whole-route common-component obstruction still stands.'})
 atomic_json(D/'state.json',{'status':'TRACING','tasks_done':len(task_rows),'pairs':len(pair_results)})
receipts=[]
for i in sorted(all_deleted):receipts.append({'raw_index':i,'span':raw[i].tolist(),'world_center':[bx+(raw[i,0]+.5)*cs,by+raw[i,3]*ch,bz+(raw[i,1]+.5)*cs],**ledge(i)})
atomic_json(D/'validation.json',{'status':'COMPLETE_LEDGE_CAUSE_DIAGNOSTIC_NOT_ACCEPTANCE','tasks':task_rows,'task_count':len(task_rows),'pairs':[{'nodes':list(k),**val} for k,val in pair_results.items()],'removed_bridge_spans':receipts,'filter_control_sha256':digest(D/'filter-control.json'),'script_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Only prefilter graph bridge and exact filter cause. Expanded proxy anchor envelopes are diagnosis only. No source coordinate, mesh, filter, body or acceptance change; paths not executable actions.'});atomic_json(D/'state.json',{'status':'COMPLETE','tasks':len(task_rows),'pairs':len(pair_results),'bridge_removed_spans':len(receipts)});print((D/'state.json').read_text())
