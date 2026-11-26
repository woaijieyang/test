"""Rule-only content/scope locks. These tests do not certify model semantics."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
BASE='48c61ee80330fe9ce12bd529fbec95a22f0b3c2c'
LOCK=ROOT/'provenance/rxr_rule_lock.json'
PHASES=[('generator','initial'),('reviewer','review'),('generator','repair'),('reviewer','recheck')]


def sha(value):
 return hashlib.sha256(value if isinstance(value,bytes) else value.encode()).hexdigest()


def source(path):
 return subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT)


def sections(text):
 matches=list(re.finditer(r'^#{2,3} .+$',text,re.M));out={}
 for i,m in enumerate(matches):
  end=matches[i+1].start() if i+1<len(matches) else len(text)
  out[m.group()]=text[m.start():end]
 return out


SNAPSHOT=r'''
import json,sys
from host.compile import compile_prompt
from host.template_selector import select_examples
queries=json.load(sys.stdin);out=[]
for profile in ('r2r-en','rxr-en-us'):
 for query in queries:
  ids={r:select_examples(r,profile,query) for r in ('generator','reviewer')}
  for role,phase in [('generator','initial'),('reviewer','review'),('generator','repair'),('reviewer','recheck')]:
   text,schema=compile_prompt(role,phase,profile=profile,original_instruction=query,selected_ids=ids[role])
   out.append(dict(profile=profile,query=query,role=role,phase=phase,ids=ids[role],prompt=text,schema=schema))
print(json.dumps(out))
'''

class RuleLockTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.original=LOCK.read_bytes();cls.data=json.loads(cls.original)

 def test_content_and_every_section_match_explicit_lock(self):
  self.assertEqual(self.data['baseline_commit'],BASE)
  for role,spec in self.data['roles'].items():
   raw=(ROOT/spec['path']).read_bytes()
   self.assertEqual(sha(raw),spec['sha256'])
   self.assertEqual(len(raw),spec['utf8_bytes'])
   self.assertEqual(sha(source(spec['path'])),spec['baseline_sha256'])
   self.assertEqual({h:sha(s) for h,s in sections(raw.decode()).items()},spec['sections'])

 def test_additions_are_reversible_without_old_rule_deletion(self):
  self.assertEqual(len(self.data['changes']),16)
  for role,spec in self.data['roles'].items():
   text=(ROOT/spec['path']).read_text();restored=text
   for row in reversed([r for r in self.data['changes'] if r['role']==role]):
    block=sections(text)['### '+row['heading']]
    self.assertIn(row['inserted_text'].strip(),block)
    self.assertEqual(restored.count(row['inserted_text']),1)
    restored=restored.replace(row['inserted_text'],'',1)
   self.assertEqual(restored.encode(),source(spec['path']))

 def test_role_identity_heading_layout_and_layer_order_unchanged(self):
  for role,spec in self.data['roles'].items():
   old=source(spec['path']).decode();new=(ROOT/spec['path']).read_text()
   self.assertEqual(old.split('## P1',1)[0],new.split('## P1',1)[0])
   self.assertEqual(list(sections(old)),list(sections(new)))
   self.assertNotRegex(new,r'(?i)\b(?:frozen_contract|frozen_gain|locked_pending_validation)\b')
   self.assertNotRegex(new,r'(?i)(?<![a-z0-9])v\d+(?:[._]\d+)*')
   if role=='reviewer':
    self.assertEqual(re.findall(r'^L[0-6]:.*$',old,re.M),re.findall(r'^L[0-6]:.*$',new,re.M))
    self.assertLess(new.index('### Ordered review framework: L0–L6'),new.index('## P2'))

 def test_existing_contracts_are_protected_without_false_gain_claims(self):
  self.assertEqual(self.data['gain_frozen_rules'],[])
  self.assertFalse(self.data['navigation_evaluated'])
  self.assertFalse(self.data['live_model_evaluated'])
  self.assertEqual(len(self.data['protected_invariants']),9)
  for row in self.data['protected_invariants']:
   text=(ROOT/self.data['roles'][row['role']]['path']).read_text()
   self.assertIn(row['clause'],text)
   self.assertIn(row['clause'],source(self.data['roles'][row['role']]['path']).decode())
   self.assertEqual(sha(row['clause']),row['sha256'])
   self.assertEqual(row['status'],'frozen_contract')
   self.assertFalse(row['navigation_gain_proven'])
   self.assertTrue(row['scope']);self.assertTrue(row['evidence_cases'])
  for row in self.data['changes']:
   self.assertEqual(row['status'],'locked_pending_validation')
   self.assertTrue(row['evidence_cases'])

 def test_runtime_format_all_templates_and_other_profile_bytes_are_unchanged(self):
  exact=('requirements.txt','generator/prompt.md','generator/repair.md','generator/repair_examples.json',
    'generator/acceptance.md','reviewer/prompt.md','reviewer/checklist.md',
    'generator/templates_manifest.json','reviewer/templates_manifest.json',
    '.github/workflows/profile-integration.yml','.github/workflows/rxr-development.yml',
    '.github/workflows/r2r-development.yml')
  prefixes=('host/','adapter/','renderer/','shared/','generator/templates/','reviewer/templates/',
    'tools/r2r_authoring/','generator/dataset_rules/r2r','reviewer/dataset_rules/r2r')
  raw=subprocess.check_output(['git','ls-tree','-rz',BASE],cwd=ROOT)
  for line in raw.split(b'\0'):
   if not line:continue
   meta,name=line.split(b'\t',1);name=name.decode()
   if name in exact or name.startswith(prefixes) or name.endswith('.schema.json'):
    value=(ROOT/name).read_bytes();blob=hashlib.sha1(b'blob '+str(len(value)).encode()+b'\0'+value).hexdigest()
    self.assertEqual(blob,meta.decode().split()[2],name)

 def test_each_new_check_includes_positive_boundary_not_automatic_prohibition(self):
  # Textual contract regression only, not an automated entailment classifier.
  g=(ROOT/self.data['roles']['generator']['path']).read_text()
  r=(ROOT/self.data['roles']['reviewer']['path']).read_text()
  for phrase in ['retain that useful separation','no word-copy rate','Retain a source-supported arrival',
    'Later wording that genuinely continues or requires a turn','Preserve genuinely prescribed sustained relations',
    'Conversely, retain an actual do-not-enter command','independently commands that later entry']:
   self.assertIn(phrase,g)
  for phrase in ['A faithful synonym','Preserve a valid useful split','do not remove a valid turn',
    'preserve genuine keep/stay','full-context evidence can legitimately support','Missing low-level motion details alone']:
   self.assertIn(phrase.casefold(),r.casefold())

 def test_independent_four_phase_inputs_change_only_in_own_rxr_rule_block(self):
  queries=['Walk through the doorway and stop by the window.',
           'At the landing turn right, then return through the same door.']
  def snapshot(path):
   return json.loads(subprocess.check_output([sys.executable,'-B','-c',SNAPSHOT],cwd=path,
      input=json.dumps(queries).encode(),timeout=180))
  now=snapshot(ROOT)
  with tempfile.TemporaryDirectory(prefix='rxr-rule-baseline-') as d:
   path=Path(d)/'baseline'
   subprocess.run(['git','worktree','add','--detach',str(path),BASE],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
   try:before=snapshot(path)
   finally:subprocess.run(['git','worktree','remove','--force',str(path)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
  self.assertEqual(len(now),len(before))
  sentinel='RXR_MAINTENANCE_ONLY_DO_NOT_INJECT'
  for a,b in zip(before,now):
   self.assertEqual({k:v for k,v in a.items() if k!='prompt'},{k:v for k,v in b.items() if k!='prompt'})
   self.assertNotIn(sentinel,b['prompt'])
   self.assertNotIn('locked_pending_validation',b['prompt'])
   if b['profile']=='r2r-en':self.assertEqual(a['prompt'],b['prompt'])
   else:
    name=self.data['roles'][b['role']]['path'];old=source(name).decode().strip();new=(ROOT/name).read_text().strip()
    self.assertEqual(a['prompt'].count(old),1);self.assertEqual(b['prompt'].count(new),1)
    self.assertEqual(b['prompt'].replace(new,old,1),a['prompt'])

 def test_validation_never_reseals_its_own_lock(self):
  self.assertEqual(LOCK.read_bytes(),self.original)

if __name__=='__main__':unittest.main()
