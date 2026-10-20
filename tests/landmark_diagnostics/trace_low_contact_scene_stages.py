"""Known-recipe native stage attribution for the two corrected low-contact scenes."""
import os,sys,json,ast,struct,collections,argparse,subprocess,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OMP_NUM_THREADS"]="1";os.environ["OPENBLAS_NUM_THREADS"]="1";os.nice(15)
P=argparse.ArgumentParser();P.add_argument("--scene",choices=["2azQ1b91cZZ","ac26ZMwG7aT"],required=True);P.add_argument("--cpu",type=int,required=True);args=P.parse_args();assert args.cpu in os.sched_getaffinity(0);os.sched_setaffinity(0,[args.cpu])
R=Path.cwd();sys.path[:0]=[str(R/"scripts"),str(R/".cache/geometry-tools")]
from workspace import atomic_json,digest
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
B=R/"outputs/landmark-connectivity";scene=args.scene;O=B/"low-contact-stage-v1"/scene;O.mkdir(exist_ok=False)
atomic_json(O/"process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19],"cpu":args.cpu})
try:
 parent=B/"full-native-v11/manifest.json";m=json.loads(parent.read_text());tasks=[t for t in m["tasks"] if t["scene"]==scene];history=B/"static-scene-search-v1"/(scene+".json");hist=json.loads(history.read_text());variant=next(r for r in hist["variants"] if r["variant"]=="fine05_climb03");assert len(tasks)==hist["records"];positives={r["task_key"] for r in variant["results"] if r["pass"]};assert set(r["task_key"] for r in variant["results"])=={t["task_key"] for t in tasks}
 source=next(r for r in json.loads((B/"native-source-catalog-v1/catalog.json").read_text())["scenes"] if r["scene"]==scene);assert digest(source["native_geometry_path"])==source["native_geometry_sha256"]
 reference=json.loads((B/"v2x-fine-stage-graphs-cpu-v1/validation.json").read_text());exe=R/".cache/native-cpu-stage-v1/build_native";assert digest(exe)==reference["executable_sha256"];assert variant["settings"]=={"cell_size":.025,"cell_height":.05,"agent_max_climb":.3,"region_min_size":40,"region_merge_size":40,"agent_height":1.5,"agent_radius":.1}
 env={**os.environ,"CASE1_NAV_TRACE_PREFIX":str(O/"native"),"CASE1_NAV_TRACE_WATCH":"0 0 0"};cmd=[str(exe),source["native_geometry_path"],str(O/"control.navmesh")];atomic_json(O/"commands.json",{"native_command":cmd,"script_sha256":digest(__file__),"native_executable_sha256":digest(exe),"history_sha256":digest(history)})
 with (O/"native.log").open("xb") as log:subprocess.run(cmd,env=env,cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True)
 assert digest(O/"control.navmesh")==variant["mesh_sha256"] and digest(O/"native-1.bin")==source["native_geometry_sha256"],"Byte control mismatch"
 cfg=[float(x) for x in (O/"native-1-config.txt").read_text().split()];cs,ch,H,climb,radius,region,bx,by,bz=cfg;H=int(H);climb=int(climb);directions=[(-1,0),(0,1),(1,0),(0,-1)]
 atomic_json(O/"native-control.json",{"status":"PASS_BYTE_CONTROL","mesh_sha256":variant["mesh_sha256"],"config":cfg,"source_sha256":source["native_geometry_sha256"],"limits":"Known fine05 historical diagnostic recipe, not guessed originalmesh settings; no new parameter candidate."})
 helper=R/"tests/landmark_diagnostics/analyze_native_stage_graphs.py";ns={"np":np,"collections":collections,"O":O,"H":H,"climb":climb,"directions":directions,"struct":struct};tree=ast.parse(helper.read_text());exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ["read","reconstruct","adjacency"]],type_ignores=[]),str(helper),"exec"),ns)
 atomic_json(O/"state.json",{"status":"RECONSTRUCTING_NATIVE_STAGES"})
 compact=ns["read"]("native-1-compacted-graph.bin",11);assert np.array_equal(ns["reconstruct"](ns["read"]("native-1-low_height-raw.bin",5)),compact)
 atomic_json(O/"reconstruction.json",{"status":"PASS_EXACT_ARRAY_RECONSTRUCTION","rows":len(compact),"helper_sha256":digest(helper),"raw_sha256":digest(O/"native-1-low_height-raw.bin"),"compact_sha256":digest(O/"native-1-compacted-graph.bin")})
 native={(r["scene"],r["node"]):r["native_candidates"][0] for r in json.loads((B/"native-mapping.json").read_text())["nodes"]};identity={(r["scene"],r["node"]):r for r in json.loads((B/"published-identity-nodes.json").read_text())["nodes"]};results={}
 stages=[("before_ledge",ns["reconstruct"](ns["read"]("native-1-low_hanging-raw.bin",5)),False),("after_ledge",ns["reconstruct"](ns["read"]("native-1-ledge-raw.bin",5)),False),("after_low_height",compact,False),("after_erosion",ns["read"]("native-1-eroded-graph.bin",11),False),("after_region_removal",ns["read"]("native-1-regions-graph.bin",11),True)]
 for stage,g,retain in stages:
  atomic_json(O/"state.json",{"status":"RUNNING","stage":stage});adj=ns["adjacency"](g);mask=(g[:,5]!=0)&((g[:,6]!=0) if retain else True);valid=np.flatnonzero(mask);dense=np.full(len(g),-1,dtype=np.int32);dense[valid]=np.arange(len(valid));start=np.repeat(valid,4);end=adj[valid].reshape(-1);ok=end>=0;start,end=start[ok],end[ok];ok=mask[end];start,end=dense[start[ok]],dense[end[ok]];matrix=csr_matrix((np.ones(len(start),dtype=np.uint8),(start,end)),shape=(len(valid),len(valid)));count,labels=connected_components(matrix,directed=True,connection="weak");positions=np.column_stack((bx+(g[valid,1]+.5)*cs,by+g[valid,3]*ch,bz+(g[valid,2]+.5)*cs));pad=np.array([3*cs,2*ch,3*cs]);cache={}
  def envelope(node):
   if node in cache:return cache[node]
   key=(scene,node);info=identity[key]
   if key in native:anchor=np.array(native[key]);camera=False
   elif info["method"]!="UNRESOLVED_no_direct_identity":anchor=np.array(info["position"]);camera=False
   else:anchor=np.array(info["camera_position"]);camera=True
   if camera:
    delta=np.maximum(abs(positions[:,[0,2]]-anchor[[0,2]])-pad[[0,2]],0);selected=(np.sum(delta*delta,axis=1)<.25)&(positions[:,1]+pad[1]>=anchor[1]-2)&(positions[:,1]-pad[1]<=anchor[1])
   else:delta=np.maximum(abs(positions-anchor)-pad,0);selected=np.sum(delta*delta,axis=1)<=.25
   cache[node]=set(labels[selected].tolist());return cache[node]
  rows=[]
  for task in tasks:
   sets=[envelope(node) for node in task["original_viewpoint_path"]];common=set.intersection(*sets);rows.append({"task_key":task["task_key"],"common_weak_components":sorted(common),"per_node_components":[sorted(s) for s in sets] if task["task_key"] not in positives else None,"known_static_positive":task["task_key"] in positives})
  misses=[r["task_key"] for r in rows if r["known_static_positive"] and not r["common_weak_components"]];atomic_json(O/(stage+".json"),{"rows":rows,"valid_spans":len(valid),"weak_components":int(count),"positive_control_misses":misses,"padding_for_diagnosis_only":pad.tolist()});results[stage]=rows
 names=[s[0] for s in stages];counts=collections.Counter();records=[];lookup={s:{r["task_key"]:r for r in rows} for s,rows in results.items()}
 for t in tasks:
  if t["task_key"] in positives:continue
  flags=[bool(lookup[s][t["task_key"]]["common_weak_components"]) for s in names]
  if all(flags):label="COMMON_WEAK_GRAPH_PROXY_REMAINS"
  elif not any(flags):label="NO_COMMON_COUNTERFACTUAL_GRAPH_BEFORE_LEDGE"
  elif all(flags[:flags.index(False)]) and not any(flags[flags.index(False):]):label="LOST_AT_"+names[flags.index(False)].upper()
  else:label="NON_MONOTONE_NEEDS_REVIEW"
  counts[label]+=1;records.append({"task_key":t["task_key"],"flags":dict(zip(names,flags)),"classification":label})
 misses={s:[r["task_key"] for r in results[s] if r["known_static_positive"] and not r["common_weak_components"]] for s in names};assert not any(misses.values()),misses
 atomic_json(O/"validation.json",{"status":"COMPLETE_STAGE_DIAGNOSIS_NOT_REPAIR","scene":scene,"tasks":len(tasks),"positive_controls":len(positives),"focused_tasks":len(records),"counts":dict(counts),"records":records,"positive_control_misses":misses,"stage_sha256":{s:digest(O/(s+".json")) for s in names},"parent_manifest_sha256":digest(parent),"historical_receipt_sha256":digest(history),"native_control_sha256":digest(O/"native-control.json"),"script_sha256":digest(__file__),"limits":"Generous necessary-condition source envelopes and weak graphs, not source-body/real-motion acceptance. Original tasks/failures preserved; no new mesh adopted or thresholds changed.","time":datetime.datetime.now().isoformat()});atomic_json(O/"state.json",{"status":"COMPLETE","counts":dict(counts)})
except Exception as e:atomic_json(O/"state.json",{"status":"FAILED","error":repr(e)});raise
