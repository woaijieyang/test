"""Verify actual native modules and runtime link resolution in the protected environment."""
import importlib,json,os,subprocess,sys
from pathlib import Path
from workspace import ROOT,atomic_json,digest
if not os.environ.get('CASE1_PROTECTION'):raise RuntimeError('Use protected runtime')
os.environ['CUDA_VISIBLE_DEVICES']=''
for name in ('habitat_sim','magnum','corrade','flash_attn'):importlib.import_module(name)
maps=Path('/proc/self/maps').read_text();reports=[]
for name in ('_corrade','_magnum','flash_attn_2_cuda','habitat_sim._ext.habitat_sim_bindings'):
 module=sys.modules[name];path=Path(module.__file__).resolve()
 if ROOT/'runtime/awarevln' not in path.parents:raise RuntimeError('Native module outside independent environment')
 result=subprocess.run(['ldd',str(path)],capture_output=True,text=True,check=True)
 missing=[line.strip().split()[0] for line in result.stdout.splitlines() if 'not found' in line]
 resolved={lib:sorted(set(line.split()[-1] for line in maps.splitlines() if line.split()[-1].endswith('/'+lib))) for lib in missing}
 if any(not values for values in resolved.values()):raise RuntimeError('Runtime native dependency unresolved: '+name)
 if any(not str(p).startswith(str(ROOT/'runtime/awarevln')+'/') for values in resolved.values() for p in values):raise RuntimeError('Preloaded framework dependency came from another environment')
 reports.append({'module':name,'path':str(path),'sha256':digest(path),'ldd':result.stdout,'resolved_by_actual_loaded_framework':resolved})
atomic_json(ROOT/'outputs/setup/native-linkage-verified.json',{'status':'PASS','modules':reports,'scope':'Native link resolution, not navigation performance'})
print({'status':'PASS','native_modules':len(reports)})
