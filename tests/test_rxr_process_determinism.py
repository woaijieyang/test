"""Selection and complete role prompts must survive fresh process hash seeds."""
import json
import os
import subprocess
import sys
import unittest

from host.compile import ROOT

PROGRAM = r'''
import hashlib
import json
from host.compile import compile_prompt
from host.template_selector import select_examples
from tools.rxr_lesson_specs import LESSONS
texts=[row['source'] for row in LESSONS]+[
    'If we turn around, we will see two doors. Choose the rightmost doorway.',
    'Walk straight down the hallway. Walk straight down the hallway until you see the sign.',
    'Turn left, sorry, turn right and go through the first doorway. Return through the same door.',
]
results=[]
for text in texts:
    for count in (None,2,4):
        ids={role:select_examples(role,'rxr-en-us',text,count=count) for role in ('generator','reviewer')}
        messages={}
        for role,phase in [('generator','initial'),('generator','repair'),('reviewer','review'),('reviewer','recheck')]:
            prompt=compile_prompt(role,phase,profile='rxr-en-us',selected_ids=ids[role],original_instruction=text)
            messages[role+'/'+phase]=hashlib.sha256(prompt.encode()).hexdigest()
        results.append({'ids':ids,'prompt_hashes':messages})
print(json.dumps(results,sort_keys=True))
'''


class RxRProcessDeterminismTests(unittest.TestCase):
    def test_selection_and_four_phase_prompts_across_hash_seeds(self):
        runs=[]
        for seed in ('1','23'):
            env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE='1')
            output=subprocess.check_output([sys.executable,'-B','-c',PROGRAM],cwd=ROOT,env=env,text=True,timeout=90)
            runs.append(json.loads(output))
        self.assertEqual(len(runs[0]),33)
        self.assertEqual(runs[0],runs[1])


if __name__=='__main__':
    unittest.main()
