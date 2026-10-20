"""Sequential protected full-scene proposal and independent audit; no candidate adoption."""
import os,sys,subprocess,json,datetime,hashlib
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION")
os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1"
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
B=R/"outputs/landmark-connectivity";D=B/"1LX-grounded-fine05-v1-control";D.mkdir(exist_ok=False)
atomic_json(D/"process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19]})
commands=[
 [sys.executable,"-B","tests/landmark_diagnostics/probe_source_bounded_scene_profile_v3.py","--scene","1LXtFkjw3qL","--profile","data/derived/navmeshes/landmark-1lx-fine05-grounded-v22/profile.json","--geometry-receipt","outputs/landmark-connectivity/native-source-catalog-v1/scenes/1LXtFkjw3qL/validation.json","--run","1LX-grounded-fine05-v1"],
 [sys.executable,"-B","tests/landmark_diagnostics/audit_source_bounded_scene_candidates_v3.py","--run","1LX-grounded-fine05-v1"]]
atomic_json(D/"commands.json",{"commands":commands,"controller_sha256":digest(__file__),"sources":[{"path":c[2],"sha256":digest(c[2])} for c in commands],"limits":"Existing mesh reused; no formal source/config changes, no model or movement run, no adoption."})
try:
 for i,cmd in enumerate(commands):
  with (D/(str(i)+".log")).open("xb") as log:
   child=subprocess.Popen(cmd,cwd=R,stdout=log,stderr=subprocess.STDOUT)
   atomic_json(D/"state.json",{"status":"RUNNING","stage":i,"child_pid":child.pid,"command":cmd,"time":datetime.datetime.now().isoformat()})
   code=child.wait()
  if code:raise RuntimeError("Stage "+str(i)+" exit "+str(code))
 receipt=json.loads((B/"1LX-grounded-fine05-v1/static-transition-audit.json").read_text())
 atomic_json(D/"state.json",{"status":"COMPLETE_NOT_ADOPTED","candidate_status":receipt["status"],"tasks":receipt["scene_tasks"],"recovered":len(receipt["recovered"]),"regressed":len(receipt["regressed"]),"time":datetime.datetime.now().isoformat()})
except Exception as e:atomic_json(D/"state.json",{"status":"FAILED","error":repr(e)});raise
