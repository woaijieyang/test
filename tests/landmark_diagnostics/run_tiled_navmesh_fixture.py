"""Build fixture against original archives only; original installation is read-only."""
import os,sys,json,subprocess,datetime
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION");os.environ["CUDA_VISIBLE_DEVICES"]="";os.environ["OMP_NUM_THREADS"]="1";os.environ["OPENBLAS_NUM_THREADS"]="1";os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
B=R/"outputs/landmark-connectivity";O=B/"tiled-navmesh-fixture-v1";O.mkdir(exist_ok=False);C=R/".cache/tiled-navmesh-fixture-v1";C.mkdir(exist_ok=False)
try:
 src=R/"upstream/habitat-sim/src/deps/recastnavigation";build=R/"upstream/habitat-sim/build/deps/recastnavigation";archives=[build/"Recast/libRecast.a",build/"Detour/libDetour.a"];before={str(p):digest(p) for p in archives};source=R/"tests/landmark_diagnostics/tiled_navmesh_fixture.cpp";exe=C/"fixture";cmd=["/usr/bin/c++","-std=c++14","-O2","-I"+str(src/"Recast/Include"),"-I"+str(src/"Detour/Include"),str(source),*(str(p) for p in archives),"-o",str(exe)];atomic_json(O/"commands.json",{"compile":cmd,"source_sha256":digest(source),"archives_before":before,"controller_sha256":digest(__file__)})
 with (O/"compile.log").open("xb") as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
 with (O/"native.log").open("xb") as f:subprocess.run([str(exe),str(O)],stdout=f,stderr=subprocess.STDOUT,check=True)
 assert all(digest(p)==sha for p,sha in before.items());rows=[json.loads(s) for s in (O/"native-results.jsonl").read_text().splitlines()];assert len(rows)==6;atomic_json(O/"native-validation.json",{"status":"PASS_NATIVE_FIXTURES_PENDING_HABITAT_LOAD","cases":rows,"original_archives_unchanged":True,"executable_sha256":digest(exe),"source_sha256":digest(source),"limits":"Sixownedplane/wall/gap fixtures only, notMP3D orproductionprofile. No installedlibrary/scene modifications."});atomic_json(O/"state.json",{"status":"NATIVE_COMPLETE_PENDING_HABITAT_CHECK"})
except Exception as e:atomic_json(O/"state.json",{"status":"FAILED","error":repr(e)});raise
