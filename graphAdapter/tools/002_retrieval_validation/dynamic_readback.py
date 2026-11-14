"""Operator entry point for dynamic-field evidence readback."""
import json,sys
from pathlib import Path
from graphAdapter.evaluation.dynamic_material_audit import audit_episode
if __name__=='__main__':
    run=Path(sys.argv[1])
    entries=json.loads((run/'retention_plan.json').read_bytes())['entries']
    for entry in entries:
        report=audit_episode(run/'results'/entry['key']/'shadow/attempt0',entry)
        target=run/'control'/('dynamic-independent-review.json' if len(entries)==1 else 'dynamic-review-'+entry['key']+'.json')
        if not target.exists():target.write_text(json.dumps(report,indent=2))
        print({k:v for k,v in report.items() if k!='examples'})
