"""Read-only behavioral isolation checks plus explicit generated hash refresh.

Parent and candidate run in separate interpreters. RxR is compared to the actual
parent, not the older evaluated R2R branch. No LLM or navigation claim is made.
"""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[2]
PARENT='081db4b9ea0712ff720c137fe96c240c26f7b15c'
EVALUATED='9dd24a655a845d59698e835c0326fbf73db5fbb8'
CAPTURE=r'''
import hashlib,json,os
from pathlib import Path
from host.compile import compile_prompt
from host.template_selector import library,select_examples,source
from shared.identity import canonical,text_hash
queries=['','Turn left and go through the doorway.','If the door is closed, return to the same door and wait.','Go down halfway and stop before the last step.']
queries += [source(r) for r in library('generator','rxr-en-us')]
cases=[]
for q in dict.fromkeys(queries):
 for role,phases in [('generator',['initial','repair']),('reviewer',['review','recheck'])]:
  before=select_examples(role,'rxr-en-us',q)
  if os.environ.get('MIXED_PROFILE_CHECK'):
   from host.r2r.selection import select_bundle
   select_bundle('Enter the hallway and stop near the first door to the left of the stairs.')
  ids=select_examples(role,'rxr-en-us',q)
  assert ids==before
  for phase in phases:
   p,s=compile_prompt(role,phase,profile='rxr-en-us',selected_ids=ids,original_instruction=q)
   cases.append(dict(source=q,role=role,phase=phase,ids=ids,prompt_sha256=text_hash(p),schema_sha256=text_hash(canonical(s))))
protected={}
for p in Path('.').rglob('*'):
 if not p.is_file() or '.git' in p.parts or '__pycache__' in p.parts:continue
 n=p.as_posix()
 if n.startswith(('renderer/','adapter/')) or '/RxR/' in n or 'rxr_en_us' in n or n.endswith('.schema.json') or n in ('shared/semantic_contract.md','generator/prompt.md','reviewer/prompt.md','generator/repair.md','generator/repair_examples.json','reviewer/checklist.md','host/protocol.py','host/rxr_assets.py','host/rxr_retrieval.py','shared/identity.py'):
  protected[n]=hashlib.sha256(p.read_bytes()).hexdigest()
print(json.dumps(dict(cases=cases,protected=protected),sort_keys=True))
'''

def cmd(args,cwd=ROOT,env=None):return subprocess.check_output(args,cwd=cwd,env=env)
def blob(path):
    b=path.read_bytes();return hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
def encode(x):return (json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode()

def refresh():
    p=ROOT/'provenance/r2r_profile_integrity.json';m=json.loads(p.read_bytes());names={r['path'] for r in m['files']}
    for prefix in ('host/r2r','tools/r2r_authoring','tests/r2r','generator/templates/R2R','reviewer/templates/R2R'):
        names.update(x.relative_to(ROOT).as_posix() for x in (ROOT/prefix).rglob('*') if x.is_file() and '__pycache__' not in x.parts and x.suffix!='.pyc')
    names.update(['generator/dataset_rules/r2r_repair_examples.json','reviewer/dataset_rules/r2r_recheck_examples.json','host/r2r/teaching_index.json','provenance/r2r_rule_links.json','provenance/r2r_teaching_changes.json'])
    m['files']=[dict(path=n,git_blob_sha1=blob(ROOT/n)) for n in sorted(names) if (ROOT/n).is_file()];m['file_count']=len(m['files']);p.write_bytes(encode(m))
    p=ROOT/'FILE_HASHES.json';old=json.loads(p.read_bytes());files={x.relative_to(ROOT).as_posix():x for x in ROOT.rglob('*') if x.is_file() and '.git' not in x.parts and '__pycache__' not in x.parts and x.suffix!='.pyc' and x.relative_to(ROOT).as_posix()!='FILE_HASHES.json'}
    out={}
    # Canonical ordering must not depend on the number of earlier refreshes.
    for n in sorted(files):
        v=old.get(n,'gitblob-sha1:')
        out[n]='gitblob-sha1:'+blob(files[n]) if v.startswith('gitblob-sha1:') else ('sha256:' if v.startswith('sha256:') else '')+hashlib.sha256(files[n].read_bytes()).hexdigest()
    p.write_bytes(encode(out))

def isolation():
    parent=Path(tempfile.mkdtemp(prefix='r2r-parent-'))
    cmd(['git','worktree','add','--detach',str(parent),PARENT])
    try:
        before=json.loads(cmd([sys.executable,'-B','-c',CAPTURE],parent))
        env=dict(os.environ,MIXED_PROFILE_CHECK='1',PYTHONDONTWRITEBYTECODE='1')
        after=json.loads(cmd([sys.executable,'-B','-c',CAPTURE],ROOT,env))
        if before!=after:
            changed=[k for k,v in before['protected'].items() if after['protected'].get(k)!=v]
            drift=[(a['role'],a['phase'],a['source'][:70]) for a,b in zip(before['cases'],after['cases']) if a!=b]
            raise AssertionError(json.dumps({'protected_drift':changed,'prompt_drift':drift}))
        for role in ('generator','reviewer'):
            old=json.loads((parent/role/'templates_manifest.json').read_bytes());new=json.loads((ROOT/role/'templates_manifest.json').read_bytes())
            for group in ('dataset_profiles','runtime_policy'):
                assert old[group]['rxr-en-us']==new[group]['rxr-en-us']
        compiled=['generator/compiled_rxr-en-us.txt','generator/compiled_repair_rxr-en-us.txt','reviewer/compiled_rxr-en-us.txt']
        assert all((parent/p).read_bytes()==(ROOT/p).read_bytes() for p in compiled)
        diff=cmd(['git','diff','--name-status',EVALUATED,PARENT]).decode().splitlines()
        report=dict(parent_commit=PARENT,evaluated_commit=EVALUATED,direct_parent_comparison=diff,protected_files=len(before['protected']),rxr_queries=len(before['cases'])//4,rxr_phase_cases=len(before['cases']),rxr_prompt_schema_ids_equal=True,rxr_compiled_bytes_equal=True,mixed_profile_equal=True,semantic_correctness_verified=False,navigation_evaluated=False)
        (ROOT/'provenance/r2r_parent_isolation.json').write_bytes(encode(report))
        print('ISOLATION '+json.dumps({k:v for k,v in report.items() if k!='direct_parent_comparison'}))
    finally:cmd(['git','worktree','remove','--force',str(parent)])

def main():
    p=argparse.ArgumentParser();p.add_argument('--refresh',action='store_true');p.add_argument('--isolation',action='store_true');args=p.parse_args()
    if args.isolation:isolation()
    if args.refresh:refresh()
if __name__=='__main__':main()
