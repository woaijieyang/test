"""Locate minimal eroded-span connectors, then inspect their native source-body clearance."""
import os,sys,json,ast,struct,collections,heapq,math,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
from cylinder_contact_height import contact_height_range
import numpy as np,psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])]);B=R/'outputs/landmark-connectivity';O=B/'v2x-fine-stage-graphs-cpu-v1';D=O/'erosion-connectors';D.mkdir(exist_ok=False);atomic_json(D/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});validation=json.loads((O/'validation.json').read_text());assert validation['native_byte_control_match'];cs,ch,H,climb,radius,region,bx,by,bz=validation['native_build_config'];helper=R/'tests/landmark_diagnostics/analyze_native_stage_graphs.py';tree=ast.parse(helper.read_text());ns={'np':np,'collections':collections,'O':O,'H':int(H),'climb':int(climb),'directions':[(-1,0),(0,1),(1,0),(0,-1)],'struct':struct};exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['read','adjacency']],type_ignores=[]),str(helper),'exec'),ns);pre=ns['read']('native-1-compacted-graph.bin',11);post=ns['read']('native-1-eroded-graph.bin',11);final=ns['read']('native-1-regions-graph.bin',11);adj=ns['adjacency'](pre);valid=pre[:,5]!=0;removed=valid&(post[:,5]==0);retained=(final[:,5]!=0)&(final[:,6]!=0);positions=np.column_stack((bx+(pre[:,1]+.5)*cs,by+pre[:,3]*ch,bz+(pre[:,2]+.5)*cs));pad=np.array([3*cs,2*ch,3*cs]);core_path=B/'V2X-grounded-fine05-supported-v1/component-conflict-cores.json';cores=json.loads(core_path.read_text());groups=cores['groups'];assert len(groups)==4
raw=(O/'native-1.bin').read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);vv=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);ii=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=vv[ii].astype(float);lo=tri.min(axis=1);hi=tri.max(axis=1);body_cache={}
def body(i):
 if i in body_cache:return body_cache[i]
 p=positions[i];ids=np.flatnonzero((lo[:,0]<p[0]+.1)&(hi[:,0]>p[0]-.1)&(lo[:,2]<p[2]+.1)&(hi[:,2]>p[2]-.1)&(lo[:,1]<p[1]+1.5)&(hi[:,1]>p[1]+1e-5));hits=[]
 for j in ids:
  distance=triangle_linear_sweep_distance(tri[j],p,p)
  if distance<.1-1e-6:
   h=contact_height_range(tri[j],p);hits.append({'triangle':int(j),'distance':float(distance),'height':h})
 body_cache[i]={'span_id':int(i),'cell_xz':pre[i,1:3].tolist(),'position':p.tolist(),'clearance_voxels':int(pre[i,4]),'center_source_contact_count':len(hits),'center_contacts':hits};return body_cache[i]
reports=[]
try:
 for group in groups:
  masks=[]
  for member in group['members']:
   hit=np.zeros(len(pre),dtype=bool)
   for c in member['candidates'].values():hit|=np.all(abs(positions-np.array(c['position']))<=pad,axis=1)
   masks.append(hit&retained)
  seeds=np.flatnonzero(masks[0]);goals=masks[1];assert len(seeds) and goals.any();distance=np.full(len(pre),2**30,dtype=np.int32);length=np.full(len(pre),2**30,dtype=np.int32);parents=np.full(len(pre),-1,dtype=np.int32);queue=[]
  for i in seeds:distance[i]=0;length[i]=0;heapq.heappush(queue,(0,0,int(i)))
  finish=None;expanded=0
  while queue:
   cost,steps,i=heapq.heappop(queue)
   if cost!=distance[i] or steps!=length[i]:continue
   expanded+=1
   if goals[i]:finish=i;break
   for rawj in adj[i]:
    j=int(rawj)
    if j<0 or not valid[j]:continue
    new=(cost+int(removed[j]),steps+1)
    if new>=(int(distance[j]),int(length[j])):continue
    distance[j],length[j]=new;parents[j]=i;heapq.heappush(queue,(*new,j))
  assert finish is not None,'Weak pre-erosion connection was not directed-reachable';path=[finish]
  while parents[path[-1]]>=0:path.append(int(parents[path[-1]]))
  path.reverse();cut=[i for i in path if removed[i]];assert len(cut)==int(distance[finish]) and cut;report={'group_id':group['group_id'],'task_keys':group['task_keys'],'nodes':[r['node'] for r in group['members']],'minimum_removed_spans':len(cut),'path_spans':len(path),'expanded_graph_nodes':expanded,'path':[{'span_id':int(i),'position':positions[i].tolist(),'removed_by_erosion':bool(removed[i])} for i in path],'removed_span_source_checks':[body(i) for i in cut]};atomic_json(D/(group['group_id']+'.json'),report);reports.append({'group_id':group['group_id'],'tasks':len(group['task_keys']),'minimum_removed_spans':len(cut),'path_spans':len(path),'removed_centers_with_source_contact':sum(body(i)['center_source_contact_count']>0 for i in cut),'receipt_sha256':digest(D/(group['group_id']+'.json'))});atomic_json(D/'state.json',{'status':'RUNNING','groups':len(reports),'expected':4})
 atomic_json(D/'validation.json',{'status':'COMPLETE_MINIMAL_EROSION_CONNECTOR_DIAGNOSIS_NOT_REPAIR','tasks':sum(r['tasks'] for r in reports),'groups':reports,'unique_removed_centers':len(body_cache),'source_contact_free_removed_centers':sum(r['center_source_contact_count']==0 for r in body_cache.values()),'core_sha256':digest(core_path),'native_input_sha256':digest(O/'native-1.bin'),'pre_graph_sha256':digest(O/'native-1-compacted-graph.bin'),'post_graph_sha256':digest(O/'native-1-eroded-graph.bin'),'script_sha256':digest(__file__),'limits':'Lexicographic minimum removed spans then graph hops in unchanged pre-erosion directed graph. Cell-center source tests are diagnostic, not full-cell/support/actual-motion certificates. No erased cell restored or radius weakened.'});atomic_json(D/'state.json',{'status':'COMPLETE'});print(reports)
except Exception as e:atomic_json(D/'state.json',{'status':'FAILED','error':repr(e)});raise
