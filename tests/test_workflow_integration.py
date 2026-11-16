import json
import unittest
from jsonschema import Draft202012Validator
from host.compile import compile_prompt
from host import protocol
from host.template_selector import PROFILES, library, select_examples, source
from host.run import run_record
from adapter.source import Source
from test_runtime_contract_v2 import SOURCE, generator_candidate, reviewer_output

class Integration(unittest.TestCase):
    def test_generator_library_and_standalone_schema(self):
        for profile in PROFILES:
            _, spec = compile_prompt('generator', profile=profile, examples=False)
            validator = Draft202012Validator(spec)
            for row in library('generator', profile):
                with self.subTest(template=row['template_id']):
                    validator.validate(row['output'])
                    protocol.generator(source(row), row['output'])

    def test_repair_examples(self):
        rows = json.loads((protocol.ROOT/'generator/repair_examples.json').read_bytes())
        _, spec = compile_prompt('generator', 'repair', profile='rxr-en-us', examples=False)
        for row in rows:
            Draft202012Validator(spec).validate(row['output'])
            protocol.feedback(row['input']['original_instruction'], row['input']['review'], row['output'])

    def test_dataset_isolation_and_all_phases(self):
        for profile in PROFILES:
            for role, phases in [('generator', ('initial','repair')), ('reviewer', ('review','recheck'))]:
                bank = library(role,profile)
                text = source(bank[0])
                ids = select_examples(role, profile, text)
                self.assertNotIn(bank[0]['template_id'],ids)
                self.assertTrue((6 <= len(ids) <= 8) if role == "generator" else (8 <= len(ids) <= 12))
                self.assertEqual(ids,select_examples(role, profile, text))
                for phase in phases:
                    prompt,spec=compile_prompt(role,phase,profile=profile,selected_ids=ids)
                    self.assertNotIn('"$ref"',json.dumps(spec))
                    self.assertTrue(all(i in prompt for i in ids))
                    Draft202012Validator.check_schema(spec)

    def test_lookup_only_after_timeout(self):
        class Transport:
            def __init__(self):
                self.calls = []
                self.lookups = []
            def __call__(self,req):
                self.calls.append(req['phase'])
                if req['phase']=='initial':
                    raise TimeoutError('offline')
                return self.reply(req,reviewer_output(generator_candidate(True),repaired=True))
            def recover(self,req):
                self.lookups.append(req['phase'])
                return self.reply(req,generator_candidate(True))
            def reply(self,req,value):
                return dict(output=value,receipt=dict(request_id='test-'+req['phase'],model='fixture',effort='high'))
        t=Transport()
        result=run_record(Source('test','RxR','en-US',SOURCE),t,pins={r:dict(model='fixture',effort='high') for r in ('generator','reviewer')})
        self.assertEqual(t.calls,['initial','review'])
        self.assertEqual(t.lookups,['initial'])
        self.assertEqual(result['disposition'],'accepted_candidate')
