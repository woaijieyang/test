from pathlib import Path
import sys,json
from graphAdapter.evaluation.additive_material_audit import audit
if __name__=='__main__':
    root=Path(sys.argv[1])
    controls=json.loads(Path('outputs/graph_memory/candidate_detached_correction001-20261113/simulator-quality15-reuse-v3/control/REUSED_CONTROLS.json').read_bytes())
    vocab=list(dict.fromkeys(x.strip() for x in Path('vendor_sources/EvoMemNav/data/scannet200_classes.txt').read_text().splitlines()if x.strip() and x.strip()!='unknown'))
    for e in json.loads((root/'retention_plan.json').read_bytes())['entries']:
        d=root/'results'/e['key']/'shadow/attempt0';dest=root/'control'/('native-additive-audit-'+e['member'][0]+'.json')
        if (d/'retention.json').is_file() and not dest.exists():
            out=audit(d,Path(controls[e['key']]['result']),vocab);dest.write_text(json.dumps(out,indent=2));print(json.dumps(out))

