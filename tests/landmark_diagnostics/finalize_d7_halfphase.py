"""Validate completed half-phase builds by named fields and continue without rebuilding."""
import os,sys,json,subprocess,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
import psutil
u=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<20 and i not in [22,24,27,30]];assert idle;os.sched_setaffinity(0,[min(idle,key=lambda i:u[i])])
B=R/"outputs/landmark-connectivity";O=B/"d7-halfphase-v1";C=R/".cache/d7-halfphase-v1";assert not (O/"postbuild-process.json").exists();atomic_json(O/"postbuild-process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19]})
try:
 commands=json.loads((O/"commands.json").read_text());assert digest(O/"failed-controller-v1.py")==commands["controller_sha256"];source=R/"tests/landmark_diagnostics/build_native_halfphase.cpp";assert digest(source)==commands["source_sha256"]
 original=commands["originals_before"];assert all(digest(p)==sha for p,sha in original.items());native=next(r for r in json.loads((B/"native-source-catalog-v1/catalog.json").read_text())["scenes"] if r["scene"]=="D7N2EKCX4Sj")
 expected=json.loads((B/"d7-fine-stage-v1/native-control.json").read_text());assert digest(O/"control.navmesh")==expected["mesh_sha256"]
 configs={name:[float(x) for x in (O/(name+"-1-config.txt")).read_text().split()] for name in ["control","candidate"]};assert configs["control"]==expected["config"]
 keys=("cell_size","cell_height","height_voxels","climb_voxels","radius_voxels","region_area","bmin_x","bmin_y","bmin_z");assert all(len(c)==9 for c in configs.values());named={k:dict(zip(keys,c)) for k,c in configs.items()}
 for key in (*keys[:6],"bmin_y"):assert named["candidate"][key]==named["control"][key]
 for key in ["bmin_x","bmin_z"]:assert abs(named["candidate"][key]-named["control"][key]+.0125)<2e-6
 for name in configs:assert digest(O/(name+"-1.bin"))==native["native_geometry_sha256"]
 receipt={"status":"PASS_ZERO_PHASE_BYTE_CONTROL_AND_UNCHANGED_SOURCE","control_mesh_sha256":digest(O/"control.navmesh"),"candidate_mesh_sha256":digest(O/"candidate.navmesh"),"native_input_sha256":native["native_geometry_sha256"],"actual_configs":named,"physical_parameters_unchanged":True,"original_build_and_install_hashes_unchanged":True,"private_executable_sha256":digest(C/"build_native"),"source_sha256":digest(source),"postbuild_validation_sha256":digest(__file__),"previous_failure":"failure-explanation.json","limits":"Reuses completed builds after correcting9field receipt interpretation. HalfcellXZbounds padding only; sourcegeometry andphysicalparameters unchanged. No acceptance/motion claim."};assert not (O/"build-validation.json").exists();atomic_json(O/"build-validation.json",receipt)
 parent=R/"data/derived/navmeshes/landmark-d7-fine05-grounded-v25/profile.json";profile=json.loads(parent.read_text());folder=R/"data/derived/navmeshes/landmark-d7-halfphase-grounded-v27";folder.mkdir(exist_ok=False);profile["profile_id"]=folder.name;profile["status"]="DIAGNOSTIC_HALF_CELL_ALIGNMENT_PENDING_VALIDATION";profile["parent_profile_sha256"]=digest(parent);asset=profile["assets"]["mp3d/D7N2EKCX4Sj/D7N2EKCX4Sj.glb"];asset["navmesh_path"]=str(O/"candidate.navmesh");asset["navmesh_sha256"]=receipt["candidate_mesh_sha256"];asset["rasterization_bounds_padding_m"]={"x":.0125,"z":.0125,"y":0};asset["build_receipt"]={"path":str(O/"build-validation.json"),"sha256":digest(O/"build-validation.json")};profile["selection"]={"reason":"Singlehalfcellhorizontalphase with unchangedphysicalparameters;5existingactualsourceclearpassages. Full786nonregression/motionrequired.","adopted":False};atomic_json(folder/"profile.json",profile)
 run="D7-grounded-halfphase-v1";pipeline=[[sys.executable,"-B","tests/landmark_diagnostics/probe_source_bounded_scene_profile_v3.py","--scene","D7N2EKCX4Sj","--profile",str(folder/"profile.json"),"--geometry-receipt",native["receipt_path"],"--run",run],[sys.executable,"-B","tests/landmark_diagnostics/audit_source_bounded_scene_candidates_v3.py","--run",run]];atomic_json(O/"validation-commands.json",pipeline)
 for i,cmd in enumerate(pipeline):
  with (O/("validation-"+str(i)+".log")).open("xb") as f:
   child=subprocess.Popen(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT);atomic_json(O/"state.json",{"status":"VALIDATING","stage":i,"child_pid":child.pid});code=child.wait()
  assert code==0,(i,code)
 r=json.loads((B/run/"static-transition-audit.json").read_text());atomic_json(O/"state.json",{"status":"COMPLETE_NOT_ADOPTED","tasks":r["scene_tasks"],"recovered":len(r["recovered"]),"regressed":len(r["regressed"]),"candidate_status":r["status"],"time":datetime.datetime.now().isoformat()})
except Exception as e:atomic_json(O/"state.json",{"status":"FAILED_POSTBUILD_FINALIZER","error":repr(e)});raise
