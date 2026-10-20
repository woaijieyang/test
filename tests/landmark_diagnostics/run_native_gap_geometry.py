"""Bounded four-CPU diagnostic controller, original data and formal run unchanged."""
import os,sys,json,subprocess,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OMP_NUM_THREADS"]="1";os.environ["OPENBLAS_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
import psutil
O=R/"outputs/landmark-connectivity/native-gap-geometry-v1";assert not (O/"process.json").exists();atomic_json(O/"process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19]})
children=[];logs=[]
try:
 usage=psutil.cpu_percent(interval=2,percpu=True);eligible=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<20];assert len(eligible)>=4,"Insufficient idleCPU; no workers started";cpus=sorted(eligible,key=lambda i:usage[i])[:4]
 (O/"scenes").mkdir(exist_ok=False);atomic_json(O/"execution.json",{"cpus":cpus,"cpu_sample":{str(i):usage[i] for i in cpus},"controller_sha256":digest(__file__),"worker_sha256":digest(R/"tests/landmark_diagnostics/audit_native_gap_geometry.py"),"input_sha256":digest(O/"input.json"),"formal_run_modified":False})
 for i,cpu in enumerate(cpus):
  log=(O/("worker-"+str(i)+".log")).open("xb");logs.append(log);cmd=[sys.executable,"-B","tests/landmark_diagnostics/audit_native_gap_geometry.py","--shard",str(i),"--shards","4","--cpu",str(cpu)];children.append(subprocess.Popen(cmd,cwd=R,stdout=log,stderr=subprocess.STDOUT))
 atomic_json(O/"state.json",{"status":"RUNNING","worker_pids":[p.pid for p in children],"cpus":cpus})
 codes=[p.wait() for p in children];assert not any(codes),codes
 m=json.loads((O/"input.json").read_text());reports=[];pairs=points=edges=0
 for row in m["scenes"]:
  f=O/"scenes"/(row["scene"]+".json");d=json.loads(f.read_text());assert d["scene"]==row["scene"] and d["input_sha256"]==row["input_sha256"] and d["native_geometry_sha256"]==row["native_geometry"]["native_geometry_sha256"];assert len(d["pairs"])==row["pairs"]
  assert sum(len(p["samples"]) for p in d["pairs"])==row["points"]
  pairs+=len(d["pairs"]);points+=sum(len(p["samples"]) for p in d["pairs"]);edges+=sum(len(p["edges"]) for p in d["pairs"])
  reports.append({"scene":row["scene"],"pairs":len(d["pairs"]),"point_contact_pairs":sum(p["contact_samples"]>0 for p in d["pairs"]),"continuous_contact_pairs":sum(p["contact_edges"]>0 for p in d["pairs"]),"high_point_contact_pairs":sum(p["point_contact_over_0point3m"] for p in d["pairs"]),"legacy_high_pairs":sum(p["legacy_samples_with_high_contact"]>0 for p in d["pairs"]),"report_sha256":digest(f)})
 assert len(reports)==39 and pairs==86 and points==1645
 atomic_json(O/"validation.json",{"status":"COMPLETE_NATIVE_GAP_DIAGNOSIS_NOT_REPAIR","scenes":reports,"scene_count":39,"pairs":pairs,"point_occurrences":points,"edge_occurrences":edges,"original_tasks_retained":33954,"held_retained":114,"input_sha256":digest(O/"input.json"),"controller_sha256":digest(__file__),"independent_audit_pending":True,"limits":"Complete existing86pair diagnostic coverage; not full33954native rerun, no routes adopted or collision thresholds relaxed.","time":datetime.datetime.now().isoformat()});atomic_json(O/"state.json",{"status":"COMPLETE_DIAGNOSTIC_PENDING_INDEPENDENT_AUDIT"})
except Exception as e:atomic_json(O/"state.json",{"status":"FAILED","error":repr(e),"worker_pids":[p.pid for p in children]});raise
finally:
 for f in logs:f.close()
