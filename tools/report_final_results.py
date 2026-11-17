"""Regenerate the published final table only from verified full audit snapshots."""
from pathlib import Path
import hashlib,importlib.util,json
ROOT=Path(__file__).resolve().parents[1]
receipt=json.loads((ROOT/'outputs/publication/full-audits-verified.json').read_text())
if receipt['status']!='PASS':raise RuntimeError('Final audits not accepted')
for dataset,item in receipt['receipts'].items():
    path=Path(item['snapshot'])/'validation.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=item['validation_sha256']:raise RuntimeError('Final validation receipt drift')
    validation=json.loads(path.read_text())
    if validation['status']!='PASS':raise RuntimeError('Final validation failed')
    for name,sha in validation['receipts'].items():
        if hashlib.sha256((path.parent/name).read_bytes()).hexdigest()!=sha:raise RuntimeError('Final result evidence drift')
spec=importlib.util.spec_from_file_location('verified_final_report',ROOT/'tools/report_hamlet_abc.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.SUITE=Path(receipt['report_view']);module.main()
