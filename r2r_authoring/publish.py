"""Publish only the independently rechecked candidate tree on the current branch.

No force push, secret lookup or cross-branch write. Invoked by the authorized
repository workflow after successful build, isolation, regression and smoke.
"""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
PARENT='081db4b9ea0712ff720c137fe96c240c26f7b15c'
EXACT={
 'README.md','FILE_HASHES.json','host/compile.py','host/template_selector.py','host/run.py',
 'generator/templates_manifest.json','reviewer/templates_manifest.json',
 'generator/compiled_r2r-en.txt','generator/compiled_repair_r2r-en.txt','reviewer/compiled_r2r-en.txt',
 'generator/templates/INDEX.md','reviewer/templates/INDEX.md','provenance/build_manifest.json',
 'shared/dataset_rules/r2r_en.md','shared/dataset_rules/r2r_teaching_index.json',
 'generator/dataset_rules/r2r_en.md','reviewer/dataset_rules/r2r_en.md',
 '.github/workflows/r2r-development.yml','.github/workflows/rxr-development.yml',
 'tests/test_r2r_core.py','tests/test_r2r_specialization.py','tests/test_paired_selection.py',
 'tests/test_closed_loop_35.py','tests/test_roles_repair.py','tests/test_workflow_integration.py',
 'tests/test_host_dispatch_profiles.py','tests/test_rxr_profile.py','tests/test_entry_diagnostics.py',
 'tests/test_example_injection.py','tests/test_rxr_prompt_snapshots.py',
}
PREFIX=('r2r/','r2r_authoring/','generator/templates/R2R/','reviewer/templates/R2R/','docs/R2R_','provenance/r2r_')

def out(*args,cwd=ROOT):return subprocess.check_output(args,cwd=cwd,text=True).strip()
def call(*args,cwd=ROOT):subprocess.run(args,cwd=cwd,check=True)
def unchanged(path):
    old=subprocess.check_output(['git','show',PARENT+':'+path],cwd=ROOT)
    if (ROOT/path).read_bytes()!=old:raise ValueError('Protected asset changed: '+path)

def main():
    branch=os.environ['GITHUB_REF_NAME'];tested=os.environ['GITHUB_SHA']
    if not branch.startswith('LLM-decompose-') or out('git','rev-parse','HEAD')!=tested:raise ValueError('Unexpected publication target')
    call('git','merge-base','--is-ancestor',PARENT,'HEAD')
    report=json.loads((ROOT/'provenance/r2r_regression_results.json').read_bytes())
    if not report['success'] or report['failures'] or report['errors']:raise ValueError('Regression not successful')
    iso=json.loads((ROOT/'provenance/r2r_parent_isolation.json').read_bytes())
    if not all(iso[k] for k in ('rxr_prompt_schema_ids_equal','rxr_compiled_bytes_equal','mixed_profile_equal')):raise ValueError('RxR isolation not successful')
    for p in ('shared/semantic_contract.md','host/protocol.py','generator/prompt.md','reviewer/prompt.md','generator/repair_examples.json','tests/fixtures/rxr_prompt_pins.json','provenance/rxr_profile_integrity.json'):
        unchanged(p)
    names=set(out('git','diff','--name-only',PARENT).splitlines())|set(out('git','ls-files','--others','--exclude-standard').splitlines())
    invalid=[n for n in names if n and n not in EXACT and not n.startswith(PREFIX)]
    if invalid:raise ValueError('Out-of-scope change: '+repr(sorted(invalid)))
    call('git','diff','--check')
    remote=out('git','ls-remote','origin','refs/heads/'+branch).split()[0]
    if remote!=tested:raise ValueError('Branch moved; refuse stale publication')
    call('git','config','user.name','github-actions[bot]')
    call('git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
    call('git','add','--all')
    if subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode==0:
        print('PUBLISH_NOOP '+tested);return
    call('git','commit','-m','Materialize validated R2R teaching, isolated runtime and integrity records')
    final=out('git','rev-parse','HEAD')
    clean=Path(tempfile.mkdtemp(prefix='r2r-final-'))
    call('git','worktree','add','--detach',str(clean),final)
    try:
        for module in ('r2r_authoring.integrate','r2r_authoring.test_expectations'):
            call(sys.executable,'-B','-m',module,cwd=clean)
        call(sys.executable,'-B','-m','r2r_authoring.build','--check',cwd=clean)
        call(sys.executable,'-B','verify_package.py',cwd=clean)
        call(sys.executable,'-B','-m','host.compile',cwd=clean)
        call('git','diff','--exit-code',cwd=clean)
        call(sys.executable,'-B','-m','r2r_authoring.regression',cwd=clean)
        call('git','diff','--exit-code',cwd=clean)
        call(sys.executable,'-B','verify_package.py',cwd=clean)
    finally:call('git','worktree','remove','--force',str(clean))
    if out('git','ls-remote','origin','refs/heads/'+branch).split()[0]!=tested:raise ValueError('Branch advanced during final validation')
    call('git','push','origin','HEAD:refs/heads/'+branch)
    if out('git','ls-remote','origin','refs/heads/'+branch).split()[0]!=final:raise ValueError('Remote publication verification failed')
    print('PUBLISHED_VALIDATED_COMMIT '+final)
if __name__=='__main__':main()
