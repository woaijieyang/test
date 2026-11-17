import os,sys,json,time,subprocess,fcntl,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OMP_NUM_THREADS"]="1";os.environ["OPENBLAS_NUM_THREADS"]="1"
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
B=R/"outputs/landmark-connectivity";O=B/"full-source-guard-D7-tiled-mixed-v1";lock=(O/"independent-controller.lock").open("a");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);assert not (O/"independent-controller-process.json").exists();atomic_json(O/"independent-controller-process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19]})
try:
 atomic_json(O/"independent-controller-state.json",{"status":"WAITING_FOR_COMPLETE_SCENE"})
 while not (O/"validation.json").exists():
  p=json.loads((O/"process.json").read_text());q=Path("/proc")/str(p["pid"])/"stat";s=q.read_text().rsplit(")",1)[1].split() if q.exists() else [];assert s and s[0] not in "ZX" and s[19]==str(p["start_ticks"]),"Producerendedwithoutcompletevalidation";time.sleep(30)
 v=json.loads((O/"validation.json").read_text());assert v["expected_unique_tasks"]==786
 cmd=[sys.executable,"-B","tests/landmark_diagnostics/audit_tiled_source_guard.py","--source-run",O.name,"--scene","D7N2EKCX4Sj","--output-run","D7-tiled-mixed-source-independent-v1"]
 with (O/"independent-audit.log").open("xb") as f:
  p=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT);atomic_json(O/"independent-controller-state.json",{"status":"RUNNING_COMPLETE_INDEPENDENT_AUDIT","pid":p.pid,"command":cmd});code=p.wait()
 assert code==0,code
 result=B/"D7-tiled-mixed-source-independent-v1/validation.json";d=json.loads(result.read_text());assert d["full_scene_coverage"] and d["scope_tasks"]==786;contradictions=sum(bool(r.get("exact_guard_contradiction")) for r in d["records"]);atomic_json(O/"independent-controller-state.json",{"status":"COMPLETE_AUDIT_NOT_ACCEPTANCE" if not contradictions else "AUDIT_CONTRADICTIONS","counts":d["counts"],"contradictions":contradictions,"validation_sha256":digest(result),"time":datetime.datetime.now().isoformat()})
except Exception as e:atomic_json(O/"independent-controller-state.json",{"status":"FAILED","error":repr(e)});raise
