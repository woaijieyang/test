from host.template_selector import library, source, PROFILES, select_examples
from test_runtime_contract_v2 import SOURCE, generator_candidate, reviewer_output
def combo(repaired=True,r1=False):
 g=generator_candidate(repaired)
 return g,reviewer_output(g,repaired=repaired,r1=r1)
def turn(g,r,decision='accept'):
 return dict(candidate=g,responses=[dict(finding_index=i,decision=decision,source_quotes=[SOURCE],reason='Check against full source.') for i in range(len(r['findings']))])
from host import protocol
"""Offline contract regressions; fixtures are not LLM or navigation results."""
import copy
import json
import unittest
import subprocess
import sys
import tempfile
from unittest.mock import patch

from adapter.source import Source, from_record
from host import protocol
from host.compile import ROOT, compile_prompt
from host.run import run_record
from host.template_selector import PROFILES, library
from shared.identity import ContractError, canonical

PINS = {role: {'model': 'offline-fixture', 'effort': 'not-a-model-run'}
        for role in ('generator', 'reviewer')}


def gen(index=1):
    return copy.deepcopy(library('generator', 'r2r-en')[index])


def rev(index=1):
    return copy.deepcopy(library('reviewer', 'r2r-en')[index])


def replay(outputs, sink):
    def send(request):
        sink.append(copy.deepcopy(request))
        return {'output': copy.deepcopy(outputs[len(sink)-1]),
                'receipt': {'model': request['model'], 'effort': request['effort'],
                            'request_id': f'offline-{len(sink)}'}}
    return send


class EntryDiagnostics(unittest.TestCase):
    def diagnostic(self, fn, code, path):
        with self.assertRaises(ContractError) as caught:
            fn()
        d = caught.exception.to_dict()
        self.assertEqual(d['code'], code)
        self.assertEqual(d['path'], path)
        return d

    def test_legacy_exception_compatible(self):
        e = ContractError('old message')
        self.assertIsInstance(e, ValueError)
        self.assertEqual(str(e), 'old message')
        self.assertEqual(e.to_dict()['message'], 'old message')

    def test_first_stage_mode_localized_without_mutation(self):
        r = gen(); c = r['output']; c['stage_audit'][0]['entry']['mode'] = 'inherited_pose'
        before = canonical(c)
        d = self.diagnostic(lambda: protocol.generator(r['input']['original_instruction'], c),
                            'ENTRY_MODE_INVALID_FOR_STAGE', '/stage_audit/0/entry/mode')
        self.assertEqual((d['actual'], d['stage_number']), ('inherited_pose', 1))
        self.assertEqual(canonical(c), before)

    def test_explicit_context_requires_explanation(self):
        r = gen(); a = r['output']['stage_audit'][0]
        a['entry'].update(mode='explicit_context', text=' ',
                          candidate_quotes=[r['output']['subtasks'][0]])
        self.diagnostic(lambda: protocol.generator(r['input']['original_instruction'], r['output']),
                        'EXPLICIT_CONTEXT_EVIDENCE_MISSING', '/stage_audit/0/entry')

    def test_reviewer_pass_first_mode_parity(self):
        g,r=combo();r['stage_checks'][0]['entry']['mode']='inherited_entity'
        self.diagnostic(lambda:protocol.reviewer(SOURCE,g,r),'ENTRY_MODE_INVALID_FOR_STAGE','/stage_checks/0/entry/mode')

    def test_reviewer_revise_can_describe_bad_entry(self):
        g,r=combo(False);r['stage_checks'][0]['entry']['mode']='inherited_pose'
        protocol.reviewer(SOURCE,g,r)

    def test_missing_field_pointer(self):
        r = gen(); del r['output']['stage_audit'][0]['entry']['mode']
        d = self.diagnostic(lambda: protocol.generator(r['input']['original_instruction'], r['output']),
                            'SCHEMA_VALIDATION_FAILED', '/stage_audit/0/entry/mode')
        self.assertEqual(d['validator'], 'required')

    def test_quote_pointer_and_stage(self):
        r = gen(); r['output']['stage_audit'][0]['process']['candidate_quotes'] = ['NOT IN THE CANDIDATE']
        d = self.diagnostic(lambda: protocol.generator(r['input']['original_instruction'], r['output']),
                            'EXACT_QUOTE_NOT_FOUND', '/stage_audit/0/process/candidate_quotes/0')
        self.assertEqual(d['target'], 'candidate_stage')
        self.assertEqual(d['stage_index'], 0)

    def test_repair_pointer_prefix(self):
        ex = json.loads((ROOT/'generator/repair_examples.json').read_bytes())[0]
        out = copy.deepcopy(ex['output']); out['candidate']['stage_audit'][0]['entry']['mode'] = 'inherited_pose'
        self.diagnostic(lambda: protocol.feedback(ex['input']['original_instruction'], ex['input']['review'], out),
                        'ENTRY_MODE_INVALID_FOR_STAGE', '/candidate/stage_audit/0/entry/mode')

    def test_adapter_conflict_details(self):
        row = {'dataset': 'r2r', 'episode_id': 1, 'instruction_text': 'Go.', 'original_instruction': 'Wait.'}
        before = canonical(row)
        d = self.diagnostic(lambda: from_record(row), 'SOURCE_FIELDS_CONFLICT', '/instruction_text')
        self.assertEqual(d['reference_path'], '/original_instruction')
        self.assertEqual(canonical(row), before)

    def test_adapter_missing_hash_language_type(self):
        cases = [({'dataset':'r2r','episode_id':1}, 'SOURCE_INSTRUCTION_MISSING', '/instruction'),
                 ({'dataset':'r2r','episode_id':1,'instruction_text':['Go.']}, 'SOURCE_TEXT_INVALID', '/instruction_text'),
                 ({'dataset':'r2r','episode_id':1,'instruction_text':'Go.','source_sha256':'bad'}, 'SOURCE_HASH_MISMATCH','/source_sha256'),
                 ({'dataset':'rxr','instruction_id':1,'language':'en-GB','instruction':'Go.'},'SOURCE_LANGUAGE_UNSUPPORTED','/language')]
        for row, code, path in cases:
            with self.subTest(code=code): self.diagnostic(lambda: from_record(row), code, path)

    def test_full_role_contract_present_once(self):
        contract = (ROOT/'shared/semantic_contract.md').read_text(encoding='utf-8')
        self.assertIn('## Entry context: meaning, evidence, and audit representation', contract)
        for role, phase in [('generator','initial'),('generator','repair'),('reviewer','review'),('reviewer','recheck')]:
            text, _ = compile_prompt(role, phase, profile='r2r-en')
            self.assertEqual(text.count(contract), 1)

    def test_fixture_libraries_preserved_and_valid(self):
        from jsonschema import Draft202012Validator
        from referencing import Registry,Resource
        schemas={f.name:json.loads(f.read_bytes()) for f in (ROOT/'shared/template_schemas_v1_5_2').glob('*.json')}
        registry=Registry().with_resources((name,Resource.from_contents(data)) for name,data in schemas.items())
        for role in ('generator','reviewer'):
            validator=Draft202012Validator(schemas[role+'_template.schema.json'],registry=registry)
            for profile in PROFILES:
                for row in library(role,profile):
                    validator.validate(row)

    def test_failure_before_reviewer(self):
        g = gen(); g['output']['stage_audit'][0]['entry']['mode']='inherited_pose'; sink=[]
        src=Source('offline-fixture','R2R','en',g['input']['original_instruction'])
        out=run_record(src,replay([g['output']],sink),pins=PINS)
        self.assertEqual(len(sink),1)
        self.assertEqual(out['instruction'],src.raw)
        self.assertEqual(out['diagnostic']['phase'],'initial')
        self.assertEqual(out['diagnostic']['step'],'generator_validation')
        self.assertEqual(out['diagnostic']['reviewer_status'],'not_requested')
        self.assertEqual(out['calls'][0]['call_state'],'receipt_verified')

    def test_timeout_no_retry_or_false_nonexecution(self):
        sink=[]; src=Source('offline-fixture','R2R','en','Go to the door.')
        def timeout(req): sink.append(req); raise TimeoutError('offline fixture timeout')
        out=run_record(src,timeout,pins=PINS)
        self.assertEqual(len(sink),1)
        self.assertEqual(out['calls'][0]['call_state'],'transport_failed_execution_unknown')
        self.assertEqual(out['diagnostic']['code'],'TRANSPORT_TIMEOUT')
        self.assertEqual(out['instruction'],src.raw)

    def test_success_snapshot_and_no_extra_call(self):
        g,r=combo()
        sink=[]
        out=run_record(Source('test','R2R','en',SOURCE),replay([g,r],sink),pins=PINS)
        self.assertEqual(out['disposition'],'accepted_candidate')
        self.assertEqual(len(sink),2)
        self.assertEqual(out['instruction'],json.loads(sink[-1]['messages'][1]['content'])['rendered_instruction'])
        self.assertIsNone(out['diagnostic'])

    def test_bad_pins_and_selector_failures_are_recorded(self):
        src=Source('offline-fixture','R2R','en','Go.'); sink=[]
        out=run_record(src,replay([],sink),pins={})
        self.assertEqual(out['diagnostic']['step'],'configuration_validation')
        self.assertEqual(sink,[])
        with patch('host.run.select_r2r_bundle',side_effect=ValueError('offline selection failure')):
            out=run_record(src,replay([],sink),pins=PINS)
        self.assertEqual(out['diagnostic']['step'],'example_selection')
        self.assertEqual(sink,[])

    def test_one_semantic_repair_four_calls_and_fresh_reviewer(self):
        g,r=combo(False); new,r1=combo(True,True);sink=[]
        out=run_record(Source('test','R2R','en',SOURCE),replay([g,r,turn(new,r,'partially_accept'),r1],sink),pins=PINS)
        self.assertEqual(out['disposition'],'accepted_candidate')
        self.assertEqual([req['phase'] for req in sink],['initial','review','repair','recheck'])
        ctx=json.loads(sink[-1]['messages'][1]['content'])
        self.assertEqual(ctx['prior_review'],r)
        self.assertEqual(ctx['prior_rendered_instruction'],out['snapshots'][0]['rendered_instruction'])
        self.assertNotEqual(out['snapshots'][0]['bound_candidate'],out['snapshots'][1]['bound_candidate'])

    def test_mismatched_receipt_not_called_success(self):
        g=gen();sink=[]
        def bad(req):
            sink.append(req)
            return {'output':g['output'],'receipt':{'model':'wrong','effort':req['effort'],'request_id':'fixture'}}
        out=run_record(Source('fixture','R2R','en',g['input']['original_instruction']),bad,pins=PINS)
        self.assertEqual(out['diagnostic']['code'],'MODEL_RECEIPT_MISMATCH')
        self.assertEqual(out['calls'][0]['call_state'],'receipt_invalid')
        self.assertEqual(len(sink),1)

    def test_renderer_four_modes_and_outer_bytes_unchanged(self):
        from renderer.freeze import freeze
        cases=[(' \tGo.\r\nWait.  ',['Go.\r\nWait.'],'SOURCE_EXACT',' \tGo.\r\nWait.  '),
               (' \tGo.  Wait.  ',['Go. ',' Wait. '],'BOUNDARY_ONLY',' \tGo.\nWait.  '),
               (' Walk.  ',['Move. '],'ASSEMBLED_SINGLE',' Move.  '),
               (' Walk.  ',['Move. ','Wait. '],'ASSEMBLED_MULTI',' Move.\nWait.  ')]
        for raw,parts,mode,expected in cases:
            with self.subTest(mode=mode):
                before=copy.deepcopy(parts);view=freeze(Source('fixture','R2R','en',raw),parts)
                self.assertEqual((view.mode,view.rendered),(mode,expected))
                self.assertEqual(parts,before)

    def test_source_load_cli_writes_input_failure_without_transport(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as temp:
            d=__import__('pathlib').Path(temp);record=d/'record.json';pins=d/'pins.json';out=d/'result.json'
            record.write_text('{bad JSON',encoding='utf-8');pins.write_text(json.dumps(PINS),encoding='utf-8')
            cmd=[sys.executable,'-B','-m','host.run','--record',str(record),'--pins',str(pins),
                 '--output',str(out),'--transport','MUST_NOT_EXECUTE']
            proc=subprocess.run(cmd,cwd=ROOT,capture_output=True)
            result=json.loads(out.read_bytes());self.assertEqual(proc.returncode,2)
            self.assertEqual(result['disposition'],'input_failed')
            self.assertEqual(result['diagnostic']['code'],'SOURCE_LOAD_FAILED')
            self.assertNotIn('instruction',result)
            self.assertEqual(result['calls'],[])
            old=out.read_bytes();proc=subprocess.run(cmd,cwd=ROOT,capture_output=True)
            self.assertNotEqual(proc.returncode,0);self.assertEqual(out.read_bytes(),old)

    def test_json_pointer_escapes_special_keys(self):
        self.assertEqual(protocol.pointer(['a/b','c~d',0]),'/a~1b/c~0d/0')

    def test_later_entry_cannot_reset_and_return_is_not_rewritten(self):
        g=next(copy.deepcopy(x) for x in library('generator','r2r-en') if len(x['output']['subtasks'])>1)
        g['output']['stage_audit'][1]['entry']['mode']='episode_start'
        text=list(g['output']['subtasks'])
        self.diagnostic(lambda:protocol.generator(g['input']['original_instruction'],g['output']),
                        'ENTRY_MODE_INVALID_FOR_STAGE','/stage_audit/1/entry/mode')
        self.assertEqual(g['output']['subtasks'],text)


if __name__=='__main__': unittest.main()
