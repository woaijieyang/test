"""Read-only: compare an existing original v1.3 directory to historical component hashes."""
import argparse,json,hashlib
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();x=json.loads(Path(__file__).with_name('lineage.json').read_bytes());bad=[]
for role,info in x['bases'].items():
    for f,h in info['original_component_manifest'].items():
        path=a.directory/role/f;actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if h!=actual:bad.append({'role':role,'file':f,'expected':h,'actual':actual})
print(json.dumps({'all_historical_components_verified':not bad,'mismatches_or_missing':bad},indent=2));raise SystemExit(bool(bad))
