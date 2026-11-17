"""Isolated official626-only D7 fine-build comparison, then full bounded source recheck."""
import os,sys,json,subprocess,shutil,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OMP_NUM_THREADS"]="1";os.environ["OPENBLAS_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
import psutil
u=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<20 and i not in [22,24,27,30]];assert idle;cpu=min(idle,key=lambda i:u[i]);os.sched_setaffinity(0,[cpu])
B=R/"outputs/landmark-connectivity";O=B/"d7-fine-recast626-v1";O.mkdir(exist_ok=False);C=R/".cache/d7-fine-recast626-v1";C.mkdir(exist_ok=False);atomic_json(O/"process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19],"cpu":cpu})
try:
 old_control=B/"d7-fine-stage-v1/native-control.json";control=json.loads(old_control.read_text());assert control["status"]=="PASS_BYTE_CONTROL" and digest(B/"d7-fine-stage-v1/control.navmesh")==control["mesh_sha256"]
 receipt=B/"recast626-isolated-binding-v1/validation.json";r=json.loads(receipt.read_text());cached=R/".cache/recast626-isolated-binding-v1";patched_binding=next((cached/"patched/habitat_sim/_ext").glob("*.so"));assert digest(patched_binding)==r["patched_binding_sha256"]
 original_filter=R/"upstream/habitat-sim/src/deps/recastnavigation/Recast/Source/RecastFilter.cpp";patched_filter=cached/"RecastFilter.cpp";text=original_filter.read_text();old="if ((top - bot) <= walkableHeight)";new="if ((top - bot) < walkableHeight)";assert text.count(old)==1 and patched_filter.read_text()==text.replace(old,new)
 original_archive=R/"upstream/habitat-sim/build/deps/recastnavigation/Recast/libRecast.a";private_archive=cached/"libRecast.a";names=subprocess.check_output(["/usr/bin/ar","t",str(original_archive)],text=True).splitlines();assert names==subprocess.check_output(["/usr/bin/ar","t",str(private_archive)],text=True).splitlines();changed=[]
 for name in names:
  if subprocess.check_output(["/usr/bin/ar","p",str(original_archive),name])!=subprocess.check_output(["/usr/bin/ar","p",str(private_archive),name]):changed.append(name)
 assert changed==["RecastFilter.cpp.o"]
 originals={str(p):digest(p) for p in [original_filter,original_archive,patched_binding,R/".cache/native-cpu-stage-v1/build_native"]}
 commands=json.loads((B/"v2x-fine-stage-graphs-cpu-v1/commands.json").read_text());link=list(commands["link"]);link[link.index("-o")+1]=str(C/"build_native");assert link.count(str(original_archive))==1;link=[str(private_archive) if x==str(original_archive) else x for x in link]
 atomic_json(O/"commands.json",{"link":link,"originals_before":originals,"private_archive_sha256":digest(private_archive),"patched_filter_sha256":digest(patched_filter),"changed_archive_members":changed,"parent_binding_receipt_sha256":digest(receipt),"original_scene_control_sha256":digest(old_control),"script_sha256":digest(__file__)})
 atomic_json(O/"state.json",{"status":"LINKING_ISOLATED_CPU_DRIVER"})
 with (O/"link.log").open("xb") as log:subprocess.run(link,cwd=R,stdout=log,stderr=subprocess.STDOUT,check=True)
 source=next(row for row in json.loads((B/"native-source-catalog-v1/catalog.json").read_text())["scenes"] if row["scene"]=="D7N2EKCX4Sj");assert digest(source["native_geometry_path"])==source["native_geometry_sha256"]
 env=dict(os.environ);env.pop("CASE1_NAV_TRACE_PREFIX",None);env.pop("CASE1_NAV_TRACE_WATCH",None)
 atomic_json(O/"state.json",{"status":"BUILDING_PATCHED_MESH"})
 with (O/"build.log").open("xb") as log:subprocess.run([str(C/"build_native"),source["native_geometry_path"],str(O/"patched.navmesh")],cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
 assert all(digest(path)==sha for path,sha in originals.items());mesh_sha=digest(O/"patched.navmesh");changed_mesh=mesh_sha!=control["mesh_sha256"]
 atomic_json(O/"build-validation.json",{"status":"PASS_CONTROL_AND_ISOLATED_SINGLE_OBJECT_PATCH","source_scene":"D7N2EKCX4Sj","source_geometry_sha256":source["native_geometry_sha256"],"control_mesh_sha256":control["mesh_sha256"],"patched_mesh_sha256":mesh_sha,"mesh_changed":changed_mesh,"native_build_config":control["config"],"official_recast_commit":"9432fd6381d5b7c0567b06e6baff3783e80a3eb1","changed_archive_members":changed,"originals_unchanged":True,"private_executable_sha256":digest(C/"build_native"),"private_archive_sha256":digest(private_archive),"limits":"Knownfine05recipe with officiallow-height equality fix only. Originalscenes, body, slope,climb,region,sourcebounds,installedruntime andformalrun unchanged. Noadoption ormotionacceptance."})
 if not changed_mesh:
  atomic_json(O/"state.json",{"status":"COMPLETE_IDENTICAL_MESH_NO_RETEST"});sys.exit(0)
 parent=R/"data/derived/navmeshes/landmark-d7-fine05-grounded-v25/profile.json";profile=json.loads(parent.read_text());folder=R/"data/derived/navmeshes/landmark-d7-fine626-grounded-v26";folder.mkdir(exist_ok=False);profile["profile_id"]=folder.name;profile["status"]="OFFICIAL626_FINE_CANDIDATE_PENDING_SOURCE_VALIDATION_NOT_ADOPTED";profile["parent_profile_sha256"]=digest(parent);asset=profile["assets"]["mp3d/D7N2EKCX4Sj/D7N2EKCX4Sj.glb"];asset["navmesh_path"]=str(O/"patched.navmesh");asset["navmesh_sha256"]=mesh_sha;asset["recast_patch"]={"commit":"9432fd6381d5b7c0567b06e6baff3783e80a3eb1","build_receipt":str(O/"build-validation.json"),"build_receipt_sha256":digest(O/"build-validation.json")};profile["selection"]={"reason":"15blockedrouteslosecommoncomponentatlowheight;7207exactHclearancespans. Testofficial626onexistingfinecandidate,distinctfrompreviouscoarsepatch. All786requiredfornonregression.","adopted":False};atomic_json(folder/"profile.json",profile)
 run="D7-grounded-fine626-v1";pipeline=[[sys.executable,"-B","tests/landmark_diagnostics/probe_source_bounded_scene_profile_v3.py","--scene","D7N2EKCX4Sj","--profile",str(folder/"profile.json"),"--geometry-receipt",source["receipt_path"],"--run",run],[sys.executable,"-B","tests/landmark_diagnostics/audit_source_bounded_scene_candidates_v3.py","--run",run]];atomic_json(O/"validation-commands.json",pipeline)
 for i,cmd in enumerate(pipeline):
  with (O/("validation-"+str(i)+".log")).open("xb") as log:
   child=subprocess.Popen(cmd,cwd=R,stdout=log,stderr=subprocess.STDOUT);atomic_json(O/"state.json",{"status":"RUNNING_FULL_SOURCE_VALIDATION","stage":i,"child_pid":child.pid});code=child.wait()
  assert code==0,(i,code)
 result=json.loads((B/run/"static-transition-audit.json").read_text());assert result["scene_tasks"]==786;atomic_json(O/"state.json",{"status":"COMPLETE_NOT_ADOPTED","candidate_status":result["status"],"tasks":786,"recovered":len(result["recovered"]),"regressed":len(result["regressed"]),"time":datetime.datetime.now().isoformat()})
except Exception as e:atomic_json(O/"state.json",{"status":"FAILED","error":repr(e)});raise
