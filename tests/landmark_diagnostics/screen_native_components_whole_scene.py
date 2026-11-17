"""Whole-scene necessary-condition screen on the frozen native eroded graph."""
import os,sys,json,struct,collections,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
sys.path[:0]=[str(Path.cwd()/'scripts'),str(Path.cwd()/'.cache/geometry-tools')]
from workspace import ROOT,atomic_json,digest
import numpy as np,psutil
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])])
B=ROOT/'outputs/landmark-connectivity';O=B/'native-stage-trace-xc-v3';v=json.loads((O/'validation.json').read_text());assert v['native_byte_control_match'];sc=v['scene'];cs,ch,H,climb,radius,region,bx,by,bz=v['native_build_config'];raw=(O/'native-1-regions-graph.bin').read_bytes();n=struct.unpack('<i',raw[:4])[0];g=np.frombuffer(raw,dtype='<i4',offset=4).reshape(n,11);cells=collections.defaultdict(list)
for i,r in enumerate(g):assert r[0]==i;cells[(int(r[1]),int(r[2]))].append(i)
valid=np.flatnonzero(g[:,5]!=0);dense=np.full(n,-1,dtype=np.int32);dense[valid]=np.arange(len(valid));edges=[]
for i in valid:
 row=g[i]
 for d,(dx,dz) in enumerate([(-1,0),(0,1),(1,0),(0,-1)]):
  off=int(row[7+d])
  if off==63:continue
  j=cells[(int(row[1])+dx,int(row[2])+dz)][off]
  if dense[j]>=0:edges.append((int(dense[i]),int(dense[j])))
er=np.array(edges,dtype=np.int64);matrix=csr_matrix((np.ones(len(er),dtype=np.uint8),(er[:,0],er[:,1])),shape=(len(valid),len(valid)));count,labels=connected_components(matrix,directed=True,connection='weak');full=np.full(n,-1,dtype=np.int32);full[valid]=labels;codes=er[:,0]*len(valid)+er[:,1];reverse=er[:,1]*len(valid)+er[:,0];asymmetric=int(np.sum(~np.isin(reverse,codes)));sizes=np.bincount(labels);region_components=set(full[(g[:,5]!=0)&(g[:,6]!=0)].tolist());positions=np.column_stack((bx+(g[valid,1]+.5)*cs,by+g[valid,3]*ch,bz+(g[valid,2]+.5)*cs))
m=json.loads((B/'full-native-v11/manifest.json').read_text());native={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads((B/'native-mapping.json').read_text())['nodes']};identity={(r['scene'],r['node']):r for r in json.loads((B/'published-identity-nodes.json').read_text())['nodes']};held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);cache={};xy_pad=3*cs;y_pad=2*ch;pad=np.array([xy_pad,y_pad,xy_pad])
def options(node):
 if node in cache:return cache[node]
 info=identity[(sc,node)]
 if (sc,node) in native:anchor=native[(sc,node)];kind='official_reference'
 elif info['method']!='UNRESOLVED_no_direct_identity':anchor=info['position'];kind='published_identity'
 else:anchor=info['camera_position'];kind='camera_bounds'
 a=np.array(anchor)
 if kind=='camera_bounds':
  delta=np.maximum(abs(positions[:,[0,2]]-a[[0,2]])-xy_pad,0);mask=(np.sum(delta*delta,axis=1)<.25)&(positions[:,1]+y_pad>=a[1]-2)&(positions[:,1]-y_pad<=a[1])
 else:
  delta=np.maximum(abs(positions-a)-pad,0);mask=np.sum(delta*delta,axis=1)<=.25
 result=set(labels[mask].tolist());cache[node]={'kind':kind,'anchor':anchor,'components':sorted(result),'cell_volume_hits':int(mask.sum())};return cache[node]
rows=[];counts=collections.Counter();old_pass_missing=[]
for t in [t for t in m['tasks'] if t['scene']==sc]:
 opt=[options(node) for node in t['original_viewpoint_path']];sets=[set(x['components']) for x in opt];common=set.intersection(*sets) if sets else set();prior=t['status']=='READY_FOR_NATIVE_MOTION';retained=common&region_components;dropped=common-region_components
 if prior and not common:old_pass_missing.append(t['task_key'])
 label='PRIOR_NATIVE_PASS_CONTROL' if prior else 'NO_COMMON_COMPONENT_EVEN_WITH_EXPANDED_SOURCE_ENVELOPES' if not common else 'POTENTIAL_RETAINED_REGION_MAPPING' if retained else 'POTENTIAL_DROPPED_COMPONENT_ONLY'
 counts[label]+=1;rows.append({'task_key':t['task_key'],'prior_native_ready':prior,'held114':t['task_key'] in held,'classification':label,'common_components':sorted(common),'retained_components':sorted(retained),'dropped_components':sorted(dropped),'component_sizes':{str(c):int(sizes[c]) for c in common},'missing_candidate_nodes':[n for n,o in zip(t['original_viewpoint_path'],opt) if not o['components']]})
assert len(rows)==663
atomic_json(O/'whole-scene-component-screen.json',{'status':'NECESSARY_CONDITION_SCREEN_ONLY' if not old_pass_missing else 'CONTROL_INCONSISTENCY_REQUIRES_REVIEW','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scene':sc,'tasks':663,'counts':dict(counts),'old_pass_control_misses':old_pass_missing,'eroded_graph_spans':len(valid),'weak_components':count,'nonreciprocal_edges':asymmetric,'proxy_cell_expansion':{'horizontal':xy_pad,'vertical':y_pad,'purpose':'Generous analytical overapproximation for a necessary condition only; original0.5m source bounds are NOT changed for accepted poses.'},'nodes':cache,'tasks_results':rows,'native_validation_sha256':digest(O/'validation.json'),'graph_sha256':digest(O/'native-1-regions-graph.bin'),'manifest_sha256':digest(B/'full-native-v11/manifest.json'),'script_sha256':digest(__file__),'limits':'A common weak component is not a valid pose, whole path or native-motion proof. Missing common component only concerns this fixed eroded graph and these conservative envelopes, not source-geometry physical impossibility.'});print(dict(counts),'control misses',len(old_pass_missing),'asymmetric',asymmetric)
