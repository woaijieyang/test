"""Observe existing known fine05 recipe on1LX, reproduce byte control before interpreting stages."""
import os,sys,json,subprocess,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OMP_NUM_THREADS"]="1";os.environ["OPENBLAS_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
import psutil
u=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:u[i])])
B=R/"outputs/landmark-connectivity";O=B/"1lx-fine-stage-graphs-cpu-v1";O.mkdir(exist_ok=False)
atomic_json(O/"process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19]})
try:
 reference=B/"v2x-fine-stage-graphs-cpu-v1/validation.json";ref=json.loads(reference.read_text());exe=R/".cache/native-cpu-stage-v1/build_native";assert digest(exe)==ref["executable_sha256"]
 catalog=B/"native-source-catalog-v1/catalog.json";n=next(r for r in json.loads(catalog.read_text())["scenes"] if r["scene"]=="1LXtFkjw3qL");assert digest(n["native_geometry_path"])==n["native_geometry_sha256"]
 history=B/"static-scene-search-v1/1LXtFkjw3qL.json";h=next(r for r in json.loads(history.read_text())["variants"] if r["variant"]=="fine05_climb03");assert digest(h["mesh_path"])==h["mesh_sha256"]
 expected={"cell_size":.025,"cell_height":.05,"agent_max_climb":.3,"region_min_size":40,"region_merge_size":40,"agent_height":1.5,"agent_radius":.1};assert h["settings"]==expected
 commands=[[sys.executable,"-B","tests/landmark_diagnostics/classify_1lx_regression_components.py"],[str(exe),n["native_geometry_path"],str(O/"control.navmesh")],[sys.executable,"-B","tests/landmark_diagnostics/classify_1lx_stage_losses.py"]]
 atomic_json(O/"commands.json",{"commands":commands,"executable_sha256":digest(exe),"historical_receipt_sha256":digest(history),"script_sha256":digest(__file__)})
 for i,cmd in enumerate(commands):
  atomic_json(O/"state.json",{"status":"RUNNING","stage":i})
  env={**os.environ,"CASE1_NAV_TRACE_PREFIX":str(O/"native"),"CASE1_NAV_TRACE_WATCH":"1.32 -0.23 2.875"}
  with (O/(str(i)+".log")).open("xb") as log:subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
  if i==1:
   match=digest(O/"control.navmesh")==h["mesh_sha256"];assert digest(O/"native-1.bin")==n["native_geometry_sha256"]
   atomic_json(O/"validation.json",{"status":"PASS_CPU_NATIVE_INPUT_BYTE_CONTROL" if match else "CONTROL_MISMATCH","scene":"1LXtFkjw3qL","native_byte_control_match":match,"expected_mesh_sha256":h["mesh_sha256"],"control_mesh_sha256":digest(O/"control.navmesh"),"native_build_config":[float(x) for x in (O/"native-1-config.txt").read_text().split()],"native_geometry_sha256":n["native_geometry_sha256"],"executable_sha256":digest(exe),"historical_receipt_sha256":digest(history),"source_receipt_sha256":digest(reference),"limits":"Reproduces known historical fine05 diagnostic recipe, not unknown original mesh settings; no parameter changes or candidate adoption."});assert match
 atomic_json(O/"state.json",{"status":"COMPLETE_NOT_REPAIR","time":datetime.datetime.now().isoformat()})
except Exception as e:atomic_json(O/"state.json",{"status":"FAILED","error":repr(e)});raise
