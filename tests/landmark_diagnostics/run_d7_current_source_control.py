"""Per-scene sequential proposal/audit for existing meshes, fixed inputs and no adoption."""
import os,sys,json,subprocess,argparse,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1";os.nice(15)
P=argparse.ArgumentParser();P.add_argument("--job",type=int,required=True);P.add_argument("--cpu",type=int,required=True);args=P.parse_args();assert args.cpu in os.sched_getaffinity(0);os.sched_setaffinity(0,[args.cpu])
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
B=R/"outputs/landmark-connectivity";O=B/"d7-current-source-control-v1";manifest=O/"jobs.json";jobs=json.loads(manifest.read_text());job=jobs["jobs"][args.job];D=O/job["scene"];D.mkdir(exist_ok=False);atomic_json(D/"process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19],"cpu":args.cpu})
commands=[[sys.executable,"-B","tests/landmark_diagnostics/probe_source_bounded_scene_profile_v3.py","--scene",job["scene"],"--profile",job["profile"],"--geometry-receipt",job["geometry_receipt"],"--run",job["run"]],[sys.executable,"-B","tests/landmark_diagnostics/audit_source_bounded_scene_candidates_v3.py","--run",job["run"]]]
atomic_json(D/"commands.json",{"commands":commands,"job_manifest_sha256":digest(manifest),"controller_sha256":digest(__file__),"helper_sha256":{c[2]:digest(c[2]) for c in commands}})
try:
 for i,cmd in enumerate(commands):
  assert digest(job["profile"])==job["profile_sha256"] and digest(job["geometry_receipt"])==job["geometry_receipt_sha256"] and digest(B/"full-native-v11/manifest.json")==jobs["parent_manifest_sha256"]
  with (D/(str(i)+".log")).open("xb") as f:
   child=subprocess.Popen(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT);atomic_json(D/"state.json",{"status":"RUNNING","stage":i,"child_pid":child.pid});code=child.wait()
  if code:raise RuntimeError("Stage "+str(i)+" exit "+str(code))
 r=json.loads((B/job["run"]/"static-transition-audit.json").read_text());assert r["scene_tasks"]==job["tasks"]
 atomic_json(D/"state.json",{"status":"COMPLETE_NOT_ADOPTED","tasks":r["scene_tasks"],"recovered":len(r["recovered"]),"regressed":len(r["regressed"]),"candidate_status":r["status"],"time":datetime.datetime.now().isoformat()})
except Exception as e:atomic_json(D/"state.json",{"status":"FAILED","error":repr(e)});raise
