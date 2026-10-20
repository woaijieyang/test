"""Single half-cell horizontal alignment trial with exact zero-phase control, no scene edits."""
import os,sys,json,subprocess,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OPENBLAS_NUM_THREADS"]="1";os.environ["OMP_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
import psutil
u=psutil.cpu_percent(interval=1,percpu=True);idle=[i for i in sorted(os.sched_getaffinity(0))[:64] if u[i]<20 and i not in [22,24,27,30]];assert idle;cpu=min(idle,key=lambda i:u[i]);os.sched_setaffinity(0,[cpu])
B=R/"outputs/landmark-connectivity";O=B/"d7-coarse-halfphase-v1";O.mkdir(exist_ok=False);C=R/".cache/d7-coarse-halfphase-v1";C.mkdir(exist_ok=False);atomic_json(O/"process.json",{"pid":os.getpid(),"start_ticks":Path("/proc/self/stat").read_text().rsplit(")",1)[1].split()[19],"cpu":cpu})
try:
 old_commands=json.loads((B/"v2x-fine-stage-graphs-cpu-v1/commands.json").read_text());source=R/"tests/landmark_diagnostics/build_native_coarse_halfphase.cpp";obj=C/"driver.o";exe=C/"build_native";compile_command=list(old_commands["compile"]);old_obj=compile_command[compile_command.index("-o")+1];compile_command[compile_command.index("-o")+1]=str(obj);compile_command[compile_command.index("-c")+1]=str(source);link=list(old_commands["link"]);assert link.count(old_obj)==1;link=[str(obj) if a==old_obj else a for a in link];link[link.index("-o")+1]=str(exe)
 receipt=json.loads((B/"recast626-isolated-binding-v1/validation.json").read_text());originals=receipt["originals_before"];assert all(digest(p)==sha for p,sha in originals.items());native=next(r for r in json.loads((B/"native-source-catalog-v1/catalog.json").read_text())["scenes"] if r["scene"]=="D7N2EKCX4Sj");assert digest(native["native_geometry_path"])==native["native_geometry_sha256"]
 atomic_json(O/"commands.json",{"compile":compile_command,"link":link,"source_sha256":digest(source),"originals_before":originals,"controller_sha256":digest(__file__)})
 for name,cmd in [("compile",compile_command),("link",link)]:
  atomic_json(O/"state.json",{"status":name.upper()})
  with (O/(name+".log")).open("xb") as f:subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT,check=True)
 fine=json.loads((B/"d7-fine-stage-v1/native-control.json").read_text());parent_profile=R/"data/derived/navmeshes/landmark-recast626-mjx-v12/profile.json";base_asset=json.loads(parent_profile.read_text())["assets"]["mp3d/D7N2EKCX4Sj/D7N2EKCX4Sj.glb"];assert base_asset["build_settings"]=={"cell_size":.05,"cell_height":.05,"agent_max_climb":.3,"region_min_size":20,"region_merge_size":20,"agent_height":1.5,"agent_radius":.1};f=fine["config"];expected={"mesh_sha256":base_asset["navmesh_sha256"],"config":[f[1],f[1],f[2],f[3],2.0,400.0,*f[6:]]};configs={}
 for name,phase in [("control","zero"),("candidate","half-xz")]:
  atomic_json(O/"state.json",{"status":"BUILDING_"+name.upper()});env={**os.environ,"CASE1_NAV_TRACE_PREFIX":str(O/name),"CASE1_NAV_TRACE_WATCH":"-5.53 0.01 9.5"}
  with (O/(name+".log")).open("xb") as f:subprocess.run([str(exe),native["native_geometry_path"],str(O/(name+".navmesh")),phase],env=env,cwd=R,stdout=f,stderr=subprocess.STDOUT,check=True)
  assert digest(O/(name+"-1.bin"))==native["native_geometry_sha256"]
  configs[name]=[float(x) for x in (O/(name+"-1-config.txt")).read_text().split()]
  if name=="control":assert digest(O/"control.navmesh")==expected["mesh_sha256"] and configs[name]==expected["config"],"Zero-phase control mismatch"
 keys=("cell_size","cell_height","height_voxels","climb_voxels","radius_voxels","region_area","bmin_x","bmin_y","bmin_z")
 assert all(len(c)==len(keys) for c in configs.values());named={k:dict(zip(keys,c)) for k,c in configs.items()}
 for key in (*keys[:6],"bmin_y"):assert named["candidate"][key]==named["control"][key]
 for key in ["bmin_x","bmin_z"]:assert abs((named["candidate"][key]-named["control"][key])+.025)<2e-6
 assert all(digest(p)==sha for p,sha in originals.items())
 mesh_sha=digest(O/"candidate.navmesh");atomic_json(O/"build-validation.json",{"status":"PASS_ZERO_PHASE_BYTE_CONTROL_AND_UNCHANGED_SOURCE","control_mesh_sha256":digest(O/"control.navmesh"),"candidate_mesh_sha256":mesh_sha,"native_input_sha256":native["native_geometry_sha256"],"actual_configs":configs,"grid_bound_change":"Extendxmin/zmin by-negativehalfcell,xmax/zmax bypositivehalfcell toshiftgridwithoutclippingoriginaltriangles","physical_parameters_unchanged":True,"original_build_and_install_hashes_unchanged":True,"private_executable_sha256":digest(exe),"source_sha256":digest(source),"limits":"Singlegridalignmenthypothesis motivated by5existing source-clear actual localpassages. No radius/height/slope/climb/resolution/region change, no scenevertex/index modification, no adoption ornewmotionproof."})
 parent=R/"data/derived/navmeshes/landmark-recast626-mjx-v12/profile.json";profile=json.loads(parent.read_text());folder=R/"data/derived/navmeshes/landmark-d7-coarsehalf-grounded-v29";folder.mkdir(exist_ok=False);profile["profile_id"]=folder.name;profile["status"]="DIAGNOSTIC_COARSE_HALF_CELL_ALIGNMENT_PENDING_VALIDATION";profile["parent_profile_sha256"]=digest(parent);asset=profile["assets"]["mp3d/D7N2EKCX4Sj/D7N2EKCX4Sj.glb"];asset["navmesh_path"]=str(O/"candidate.navmesh");asset["navmesh_sha256"]=mesh_sha;asset["rasterization_bounds_padding_m"]={"x":.025,"z":.025,"y":0};asset["build_receipt"]={"path":str(O/"build-validation.json"),"sha256":digest(O/"build-validation.json")};profile["selection"]={"reason":"Singlehalfcellalignmentofexistingcoarserecipe;controlmustmatchcurrent75dmesh. Body/resolution/settingsfixedwithinfamily;full786validationrequired.","adopted":False};atomic_json(folder/"profile.json",profile)
 run="D7-grounded-coarsehalf-v1";commands=[[sys.executable,"-B","tests/landmark_diagnostics/probe_source_bounded_scene_profile_v3.py","--scene","D7N2EKCX4Sj","--profile",str(folder/"profile.json"),"--geometry-receipt",native["receipt_path"],"--run",run],[sys.executable,"-B","tests/landmark_diagnostics/audit_source_bounded_scene_candidates_v3.py","--run",run]];atomic_json(O/"validation-commands.json",commands)
 for i,cmd in enumerate(commands):
  with (O/("validation-"+str(i)+".log")).open("xb") as f:
   child=subprocess.Popen(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT);atomic_json(O/"state.json",{"status":"VALIDATING","stage":i,"child_pid":child.pid});code=child.wait()
  assert code==0,(i,code)
 r=json.loads((B/run/"static-transition-audit.json").read_text());atomic_json(O/"state.json",{"status":"COMPLETE_NOT_ADOPTED","tasks":r["scene_tasks"],"recovered":len(r["recovered"]),"regressed":len(r["regressed"]),"candidate_status":r["status"],"time":datetime.datetime.now().isoformat()})
except Exception as e:atomic_json(O/"state.json",{"status":"FAILED","error":repr(e)});raise
