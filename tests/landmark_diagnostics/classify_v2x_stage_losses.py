"""Attribute V2X candidate connectivity losses through independently checked native stages."""
import os,sys,json,ast,struct,collections,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'.cache/geometry-tools')]
from workspace import atomic_json,digest
import numpy as np,psutil
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
u=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:u[i])]);B=R/'outputs/landmark-connectivity';O=B/'v2x-fine-stage-graphs-cpu-v1';out=O/'stage-attribution';out.mkdir(exist_ok=False);atomic_json(out/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});v=json.loads((O/'validation.json').read_text());assert v['native_byte_control_match'] and digest(O/'control.navmesh')==v['expected_mesh_sha256'];cs,ch,H,climb,radius,region,bx,by,bz=v['native_build_config'];H=int(H);climb=int(climb);directions=[(-1,0),(0,1),(1,0),(0,-1)];helper=R/'tests/landmark_diagnostics/analyze_native_stage_graphs.py';tree=ast.parse(helper.read_text());functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['read','reconstruct','adjacency']];ns={'np':np,'collections':collections,'O':O,'H':H,'climb':climb,'directions':directions,'struct':struct};exec(compile(ast.Module(body=functions,type_ignores=[]),str(helper),'exec'),ns)
parent_path=B/'full-native-v11/manifest.json';parent=json.loads(parent_path.read_text());tasks=[t for t in parent['tasks'] if t['scene']=='V2XKFyX4ASd'];assert len(tasks)==633;proposal_path=B/'V2X-grounded-fine05-supported-v1/validation.json';proposal=json.loads(proposal_path.read_text());positives={r['task_key'] for r in proposal['rows'] if r['status']=='SOURCE_CLEAR_TARGETS_COMMON_COMPONENT_PENDING_MOTION'};assert len(positives)==507;core_path=B/'V2X-grounded-fine05-supported-v1/component-conflict-cores.json';cores=json.loads(core_path.read_text());groups={r['group_id']:r for r in cores['groups']};native={(r['scene'],r['node']):r['native_candidates'][0] for r in json.loads((B/'native-mapping.json').read_text())['nodes']};identity={(r['scene'],r['node']):r for r in json.loads((B/'published-identity-nodes.json').read_text())['nodes']};results={}
try:
 atomic_json(out/'state.json',{'status':'VERIFYING_NATIVE_COMPACT_RECONSTRUCTION'})
 compact=ns['read']('native-1-compacted-graph.bin',11);assert np.array_equal(ns['reconstruct'](ns['read']('native-1-low_height-raw.bin',5)),compact),'Raw-to-compact reconstruction mismatch';eroded=ns['read']('native-1-eroded-graph.bin',11);final=ns['read']('native-1-regions-graph.bin',11);columns=[0,1,2,3,4,7,8,9,10];assert np.array_equal(compact[:,columns],eroded[:,columns]) and np.array_equal(compact[:,columns],final[:,columns]);atomic_json(out/'reconstruction.json',{'status':'PASS_ARRAY_EXACT_RECONSTRUCTION','compact_rows':len(compact),'helper_sha256':digest(helper),'raw_sha256':digest(O/'native-1-low_height-raw.bin'),'compact_sha256':digest(O/'native-1-compacted-graph.bin')})
 stages=[('before_ledge',ns['reconstruct'](ns['read']('native-1-low_hanging-raw.bin',5)),False),('after_ledge',ns['reconstruct'](ns['read']('native-1-ledge-raw.bin',5)),False),('after_low_height',compact,False),('after_erosion',eroded,False),('after_region_removal',final,True)]
 for stage,g,retain in stages:
  atomic_json(out/'state.json',{'status':'RUNNING','stage':stage});adj=ns['adjacency'](g);mask=(g[:,5]!=0)&((g[:,6]!=0) if retain else True);valid=np.flatnonzero(mask);dense=np.full(len(g),-1,dtype=np.int32);dense[valid]=np.arange(len(valid));start=np.repeat(valid,4);end=adj[valid].reshape(-1);ok=end>=0;start,end=start[ok],end[ok];ok=mask[end];start,end=dense[start[ok]],dense[end[ok]];matrix=csr_matrix((np.ones(len(start),dtype=np.uint8),(start,end)),shape=(len(valid),len(valid)));count,labels=connected_components(matrix,directed=True,connection='weak');positions=np.column_stack((bx+(g[valid,1]+.5)*cs,by+g[valid,3]*ch,bz+(g[valid,2]+.5)*cs));codes=start.astype(np.int64)*len(valid)+end;reverse=end.astype(np.int64)*len(valid)+start;asym=int(np.sum(~np.isin(reverse,codes)));pad=np.array([3*cs,2*ch,3*cs]);cache={}
  def envelope(node):
   if node in cache:return cache[node]
   key=('V2XKFyX4ASd',node);info=identity[key]
   if key in native:anchor=np.array(native[key]);camera=False
   elif info['method']!='UNRESOLVED_no_direct_identity':anchor=np.array(info['position']);camera=False
   else:anchor=np.array(info['camera_position']);camera=True
   if camera:
    delta=np.maximum(abs(positions[:,[0,2]]-anchor[[0,2]])-pad[[0,2]],0);selected=(np.sum(delta*delta,axis=1)<.25)&(positions[:,1]+pad[1]>=anchor[1]-2)&(positions[:,1]-pad[1]<=anchor[1])
   else:delta=np.maximum(abs(positions-anchor)-pad,0);selected=np.sum(delta*delta,axis=1)<=.25
   cache[node]=set(labels[selected].tolist());return cache[node]
  rows=[]
  for t in tasks:
   common=set.intersection(*(envelope(node) for node in t['original_viewpoint_path']));rows.append({'task_key':t['task_key'],'common_weak_components':sorted(common),'candidate_static_positive':t['task_key'] in positives})
  focused=[]
  for core in cores['records']:
   sets=[]
   for member in groups[core['group_id']]['members']:
    hit=np.zeros(len(positions),dtype=bool)
    for candidate in member['candidates'].values():hit|=np.all(abs(positions-np.array(candidate['position']))<=pad,axis=1)
    sets.append(set(labels[hit].tolist()))
   focused.append({'task_key':core['task_key'],'group_id':core['group_id'],'candidate_pose_common_weak_components':sorted(set.intersection(*sets)),'per_member_components':[sorted(x) for x in sets]})
  misses=[r['task_key'] for r in rows if r['candidate_static_positive'] and not r['common_weak_components']];report={'stage':stage,'valid_spans':len(valid),'weak_components':int(count),'nonreciprocal_edges':asym,'source_envelope_rows':rows,'candidate_pose_conflicts':focused,'positive507_control_misses':misses,'analytical_padding_only':pad.tolist(),'scope':'Generous necessary-condition graph proxies, not accepted pose-domain expansion or physical feasibility.'};atomic_json(out/(stage+'.json'),report);results[stage]=report
 assert not results['after_region_removal']['positive507_control_misses'],'Known candidate positives lost under final graph proxy; do not interpret'
 stage_names=[s[0] for s in stages];lookup={s:{r['task_key']:r for r in results[s]['candidate_pose_conflicts']} for s in stage_names};rows=[];counts=collections.Counter()
 for core in cores['records']:
  flags=[bool(lookup[s][core['task_key']]['candidate_pose_common_weak_components']) for s in stage_names]
  if all(flags):label='COMMON_WEAK_GRAPH_PROXY_REMAINS'
  elif not any(flags):label='NO_COMMON_COUNTERFACTUAL_GRAPH_BEFORE_LEDGE'
  elif all(flags[:flags.index(False)]) and not any(flags[flags.index(False):]):label='LOST_AT_'+stage_names[flags.index(False)].upper()
  else:label='NON_MONOTONE_NEEDS_REVIEW'
  counts[label]+=1;rows.append({'task_key':core['task_key'],'flags':dict(zip(stage_names,flags)),'classification':label})
 atomic_json(out/'validation.json',{'status':'COMPLETE_STAGE_ATTRIBUTION_NOT_PHYSICAL_ACCEPTANCE','scene_tasks':633,'focused_regressions':66,'counts':dict(counts),'records':rows,'control_misses_by_stage':{s:results[s]['positive507_control_misses'] for s in stage_names},'stage_receipts':{s:digest(out/(s+'.json')) for s in stage_names},'parent_manifest_sha256':digest(parent_path),'proposal_sha256':digest(proposal_path),'core_sha256':digest(core_path),'script_sha256':digest(__file__),'limits':'Raw reconstruction equals native compact arrays. Weak graph connection and padded voxel proxies are not real-motion proof; early counterfactual graphs may rewire when filters remove spans. Negative results apply to this mesh/graph/model only, no deletion or threshold relaxation.'});atomic_json(out/'state.json',{'status':'COMPLETE','counts':dict(counts)});print(dict(counts))
except Exception as e:atomic_json(out/'state.json',{'status':'FAILED','error':repr(e)});raise
