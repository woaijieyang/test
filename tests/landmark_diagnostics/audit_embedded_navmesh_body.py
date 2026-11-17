"""Read embedded native agent dimensions without rebuilding or changing any asset."""
import os,sys,json,subprocess,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
C=ROOT/'.cache/navmesh-header-probe';C.mkdir(exist_ok=False);source=ROOT/'tests/landmark_diagnostics/navmesh_header_probe.cpp';exe=C/'probe';subprocess.run(['g++','-std=c++11','-O2','-I'+str(ROOT/'upstream/habitat-sim/src/deps/recastnavigation/Detour/Include'),str(source),'-o',str(exe)],check=True)
profiles={'formal':ROOT/'data/derived/navmeshes/awarevln-scene-minimal-endpoint9-v2/profile.json','landmark':Path(json.loads((ROOT/'outputs/landmark-connectivity/full-native-v11/manifest.json').read_text())['profile_path'])};cache={};reports={};errors=[]
for name,path in profiles.items():
 p=json.loads(path.read_text());rows=[]
 for scene,asset in p['assets'].items():
  mesh=Path(asset['navmesh_path'])
  if str(mesh) not in cache:cache[str(mesh)]=json.loads(subprocess.check_output([str(exe),str(mesh)],text=True))
  tiles=cache[str(mesh)];ok=all(abs(t['height']-1.5)<1e-6 and abs(t['radius']-.1)<1e-6 for t in tiles);rows.append({'scene':scene,'mesh_path':str(mesh),'manifest_mesh_sha256':asset['navmesh_sha256'],'tiles':tiles,'body_matches':ok,'build_settings_present':asset.get('build_settings') is not None})
  if not ok:errors.append({'profile':name,'scene':scene,'tiles':tiles})
 reports[name]={'profile_path':str(path),'profile_sha256':digest(path),'assets_checked':len(rows),'rows':rows}
out=ROOT/'outputs/verification/embedded-navmesh-body-audit.json';atomic_json(out,{'status':'PASS_EMBEDDED_BODY_IDENTITIES' if not errors else 'BODY_IDENTITY_MISMATCH','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reports':reports,'errors':errors,'unique_mesh_headers_read':len(cache),'probe_source_sha256':digest(source),'script_sha256':digest(__file__),'limits':'Reads embedded Detour agent height/radius/climb only. Does not recover missing historical build parameters or prove connectivity, geometry fidelity or navigation results.'});print({k:v['assets_checked'] for k,v in reports.items()},'unique',len(cache),'mismatches',errors)
