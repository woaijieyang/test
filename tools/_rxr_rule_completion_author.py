"""One-time rule authoring from the immutable reviewed literal specification.

Only final rule/document/test artifacts are published to the target; this tool is removed.
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BASE='48c61ee80330fe9ce12bd529fbec95a22f0b3c2c'
SPEC='7ae6672b32c2c1e11feb1146a38d3c3a68d54cec'

def read_at(ref,path):
 return subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT).decode()

def sha(value):
 return hashlib.sha256(value if isinstance(value,bytes) else value.encode()).hexdigest()

def sections(text):
 matches=list(re.finditer(r'^#{2,3} .+$',text,re.M));out={}
 for i,m in enumerate(matches):
  end=matches[i+1].start() if i+1<len(matches) else len(text)
  out[m.group()]=text[m.start():end]
 return out

def write(path,data):
 (ROOT/path).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def main():
 if os.environ.get('GITHUB_REF_NAME')!='rxr-rule-completion-work':
  raise RuntimeError('Isolated work branch required')
 # Parse data only, never execute code fetched from Git history.
 specification=ast.parse(read_at(SPEC,'tools/_rxr_rule_completion_author.py'))
 values={}
 for node in specification.body:
  if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
   name=node.targets[0].id
   if name in ('ADDITIONS','INVARIANTS'):values[name]=ast.literal_eval(node.value)
 if set(values)!={'ADDITIONS','INVARIANTS'}:raise ValueError('Reviewed specification incomplete')
 roles={r:f'{r}/dataset_rules/rxr_en_us.md' for r in ('generator','reviewer')}
 baseline={r:read_at(BASE,p) for r,p in roles.items()};current=dict(baseline);changes=[]
 for r,p in roles.items():
  if (ROOT/p).read_text()!=baseline[r]:raise ValueError('Refuse changed role source: '+p)
 for r,heading,paragraph,cases in values['ADDITIONS']:
  text=current[r];start=text.index('### '+heading+'\n')
  m=re.search(r'^#{2,3} ',text[start+4:],re.M)
  end=start+4+m.start() if m else len(text)
  # Retain the existing single terminal newline; no added blank line at EOF.
  insertion=('' if text[:end].endswith('\n\n') else '\n')+paragraph+('\n' if end==len(text) else '\n\n')
  current[r]=text[:end]+insertion+text[end:]
  changes.append(dict(role=r,path=roles[r],heading=heading,inserted_text=insertion,
    status='locked_pending_validation',evidence_cases=cases,
    scope='Existing role-local P1/P2 operation; no new schema or runtime gate'))
 for r,p in roles.items():(ROOT/p).write_text(current[r],encoding='utf8')
 locks={r:dict(path=roles[r],baseline_sha256=sha(baseline[r]),sha256=sha(current[r]),
   utf8_bytes=len(current[r].encode()),sections={h:sha(s) for h,s in sections(current[r]).items()}) for r in roles}
 protected=[]
 for key,r,clause,scope,cases in values['INVARIANTS']:
  if clause not in baseline[r] or clause not in current[r]:raise ValueError('Missing invariant '+key)
  protected.append(dict(id=key,role=r,clause=clause,sha256=sha(clause),status='frozen_contract',
    scope=scope,evidence_cases=cases,
    evidence_level='Source-grounded semantic contract; historical observations are not a causal gain estimate',
    navigation_gain_proven=False))
 report=dict(baseline_commit=BASE,reviewed_spec_commit=SPEC,profile='rxr-en-us',content_status='locked',
  meaning='Content lock prevents unreviewed edits; it is not evidence of universal model effectiveness.',
  gain_frozen_rules=[],live_model_evaluated=False,navigation_evaluated=False,semantic_equivalence_certified=False,
  sources=[dict(filename='v6.6.3_5.6sol-high_ALL_EPISODES.md',sha256='42c3346fe89cdc05bd0e4bc6284f52f956ea88ada453860a708c05bb106a0229',evaluated_commit='081db4b9ea0712ff720c137fe96c240c26f7b15c'),
           dict(filename='RxR_逐项增强方案.md',sha256='429256075f262ae6f2dc73d7fba612372b56605769f6e77812e7f6c9b6605c04')],
  roles=locks,changes=changes,protected_invariants=protected,
  unchanged=['P0','P1/P2 heading structure','L0-L6 framework','common contracts','runtime and CLI','all templates','selection','complete Dynamic input','output and rendering format','R2R'],
  reentry_policy='Change only for a reproducible source/candidate counterexample or controlled regression evidence; preserve a lawful counterexample and review the exact diff. Never reseal automatically to silence a failed test.')
 write('provenance/rxr_rule_lock.json',report)
 conversion=json.loads((ROOT/'provenance/rxr_role_conversion.json').read_text())
 for r,spec in conversion['roles'].items():
  spec.setdefault('before_rule_completion',dict(new_sha256=spec['new_sha256'],new_bytes=spec['new_bytes']))
  spec['new_sha256']=locks[r]['sha256'];spec['new_bytes']=locks[r]['utf8_bytes']
 write('provenance/rxr_role_conversion.json',conversion)
 from host.compile import compile_prompt
 from shared.identity import canonical,text_hash
 pins=json.loads((ROOT/'tests/fixtures/rxr_prompt_pins.json').read_text());measurements={}
 for role,phase in [('generator','initial'),('generator','repair'),('reviewer','review'),('reviewer','recheck')]:
  prompt,schema=compile_prompt(role,phase,profile='rxr-en-us',original_instruction=pins['query'],selected_ids=pins['selected_ids'][role])
  measurements[role+'/'+phase]=dict(sha256=text_hash(prompt),schema_sha256=text_hash(canonical(schema)),utf8_bytes=len(prompt.encode()))
 write('provenance/rxr_rule_measurements.json',dict(measured_commit=os.environ.get('GITHUB_SHA'),
  workflow_run=os.environ.get('GITHUB_RUN_ID'),measurements=measurements,prompt_fixture_updated=False,
  rule_additions=len(changes),frozen_contracts=len(protected),navigation_evaluated=False))
 print(json.dumps({'roles':locks,'measurements':measurements},indent=2))

if __name__=='__main__':main()
