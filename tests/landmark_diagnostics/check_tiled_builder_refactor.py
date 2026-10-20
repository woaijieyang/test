import os,sys,json,subprocess
from pathlib import Path
assert os.environ.get("CASE1_PROTECTION")
R=Path.cwd();sys.path.insert(0,str(R/"scripts"))
from workspace import atomic_json,digest
old=R/"outputs/landmark-connectivity/tiled-navmesh-fixture-v3";O=R/"outputs/landmark-connectivity/tiled-navmesh-refactor-v1";O.mkdir(exist_ok=False);C=R/".cache/tiled-navmesh-refactor-v1";C.mkdir(exist_ok=False)
try:
 source=R/"tests/landmark_diagnostics/tiled_navmesh_fixture_shared.cpp";cmd=json.loads((old/"commands.json").read_text())["compile"];cmd=[str(source) if a.endswith("/tiled_navmesh_fixture.cpp") else a for a in cmd];cmd[cmd.index("-o")+1]=str(C/"fixture")
 with (O/"compile.log").open("xb") as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
 with (O/"native.log").open("xb") as f:subprocess.run([str(C/"fixture"),str(O)],stdout=f,stderr=subprocess.STDOUT,check=True)
 reports=[]
 for p in old.glob("*.navmesh"):
  equal=digest(p)==digest(O/p.name);reports.append({"file":p.name,"equal":equal,"sha256":digest(p)});assert equal,p.name
 assert len(reports)==6;atomic_json(O/"validation.json",{"status":"PASS_SIX_FIXTURE_BYTE_CONTROLS","files":reports,"shared_header_sha256":digest(R/"tests/landmark_diagnostics/tiled_recast_builder.h"),"source_sha256":digest(source),"limits":"Exactrefactorcontrol only; real scene notyetvalidated."})
except Exception as e:atomic_json(O/"failure.json",{"error":repr(e)});raise
