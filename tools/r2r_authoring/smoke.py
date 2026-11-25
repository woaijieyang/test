"""Record offline pipeline checks; bytes are not provider token measurements."""
from collections import Counter
from pathlib import Path
import hashlib,json,subprocess
from host.compile import ROOT,build
from host.template_selector import library
from host.r2r.selection import select_bundle
from evaluation.smoke24 import smoke
from examples.demo import main as demo
PARENT='081db4b9ea0712ff720c137fe96c240c26f7b15c'
EVALUATED='9dd24a655a845d59698e835c0326fbf73db5fbb8'

def main():
    historical=ROOT/'evaluation/renderer_smoke24.json';prior=historical.read_bytes()
    results=smoke()
    if len(results)!=24 or historical.read_bytes()!=prior:raise AssertionError('Unexpected Renderer smoke or historical rewrite')
    result=demo()
    if result['disposition']!='accepted_candidate':raise AssertionError('Demo failed')
    a=build();b=build()
    if a!=b:raise AssertionError('Compiler build is not idempotent')
    for name,item in a.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=item['compiled_sha256']:raise AssertionError('Compiled bytes do not match manifest')
    counts=Counter();ds=Counter()
    for row in library('generator','r2r-en'):
        plan=select_bundle(row['input']['original_instruction'])
        counts[len(plan['generator'])]+=1;ds[len(plan['reviewer'])-len(plan['generator'])]+=1
    comparisons={}
    for path in ('generator/compiled_r2r-en.txt','reviewer/compiled_r2r-en.txt','generator/compiled_repair_r2r-en.txt'):
        comparisons[path]={'current_utf8_bytes':len((ROOT/path).read_bytes()),'parent_utf8_bytes':len(subprocess.check_output(['git','show',PARENT+':'+path],cwd=ROOT)),'evaluated_utf8_bytes':len(subprocess.check_output(['git','show',EVALUATED+':'+path],cwd=ROOT))}
    report=dict(renderer_smoke_cases=24,historical_renderer_record_unchanged=True,offline_demo_four_phases=True,build_idempotent=True,compiled_files=len(a),r2r_library_source_queries=len(library('generator','r2r-en')),generator_dynamic_count_distribution=dict(sorted(counts.items())),reviewer_diagnostic_count_distribution=dict(sorted(ds.items())),canonical_build_sizes=comparisons,size_comparison_limit='Canonical committed empty-input builds may use different selected examples. Bytes do not establish provider tokens or truncation.',semantic_model_evaluated=False,navigation_evaluated=False)
    (ROOT/'provenance/r2r_smoke_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('SMOKE_RESULT '+json.dumps(report))
if __name__=='__main__':main()
