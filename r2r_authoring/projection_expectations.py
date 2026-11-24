"""Explicit test migration for approved R2R card and evidence representation."""
import re

def method(text,name,body):
    pattern=r'    def '+re.escape(name)+r'\(self\):[\s\S]*?(?=\n    def |\nif __name__|\n\nif __name__|\Z)'
    result,n=re.subn(pattern,lambda _:body.rstrip()+'\n',text)
    if n!=1:raise ValueError('Expected one named test: '+name)
    return result

INJECTION='''    def test_cards_preserve_decision_and_keep_diagnostic_evidence(self):
        from host.compile import core_library
        for profile in PROFILES:
            for role,phase in [('generator','initial'),('reviewer','recheck')]:
                source='Stop in the room. Stop beside the bed.'
                ids=select_examples(role,profile,source)
                text,schema=compile_prompt(role,phase,profile=profile,selected_ids=ids,original_instruction=source)
                cards=[json.loads(line) for line in text.splitlines() if line.startswith('{') and '"template_id"' in line and ('"applicable_lesson"' in line or '"format"' in line)]
                fixed=core_library(role,profile)
                self.assertEqual([c['template_id'] for c in cards],[r['template_id'] for r in fixed]+ids)
                originals={r['template_id']:r for r in [*fixed,*library(role,profile)]}
                for c in cards:
                    e=originals[c['template_id']]
                    if profile=='r2r-en':
                        self.assertTrue(c['lesson']);self.assertTrue(c['counter_boundary'])
                        self.assertEqual(c['source'],(e.get('input') or e['review_input'])['original_instruction'])
                        if 'expected_output' in c:
                            expected=e['output'] if role=='generator' else e['expected_review']
                            self.assertEqual(c['expected_output'],expected)
                        elif role=='generator':
                            self.assertEqual(c['stages'],e['output']['subtasks'])
                            self.assertEqual(c['decision']['status'],e['output']['status'])
                            self.assertEqual(c['boundary_evidence'],[dict(after_stage=h['from_subtask_index'],completed_event=h['preceding_exit']['candidate_quote'],next_action_context=h['next_entry']['candidate_quote']) for h in e['output']['handoffs']])
                        else:
                            self.assertEqual(c['candidate'],e['review_input']['candidate'])
                            self.assertEqual(c['verdict'],e['expected_review']['verdict'])
                            for shown,finding in zip(c['evidence_excerpt'],e['expected_review']['findings']):
                                self.assertEqual(shown['source'],finding['source_quote'])
                                self.assertEqual(shown['candidate'],finding['candidate_evidence'])
                            self.assertEqual(len(c['local_repair']),len(e['expected_review']['findings']))
                    else:
                        self.assertTrue(c['applicable_lesson']);t=c['teaching']
                        is_fixed=c['template_id'] in {x['template_id'] for x in fixed}
                        detail=is_fixed or c['template_id']==ids[0]
                        if role=='generator':
                            self.assertEqual(t['stages'],e['output']['subtasks'])
                            self.assertEqual(t['handoffs'],e['output']['handoffs'])
                            self.assertEqual('stage_evidence' in t,detail)
                        else:
                            self.assertEqual(t['findings'],runtime_review_output(e)['findings'])
                            self.assertEqual(t['review_case'],e['review_input'])
                            self.assertEqual('coverage_evidence' in t,detail)
                            if is_fixed:
                                self.assertEqual(len(t['stage_checks']),len(e['review_input']['candidate']['subtasks']))
                                self.assertEqual(len(t['layer_checks']),7)
                self.assertIn('two distinct stops',text)
                blank,other_schema=compile_prompt(role,phase,profile=profile,original_instruction=source,examples=False)
                self.assertEqual(other_schema,schema);self.assertNotIn('APPLY THE EXAMPLES',blank)
'''
CORE='''    def test_generator_core_cards_expose_primary_boundary_and_case_rationale(self):
        from host.compile import teaching_card
        from r2r.selection import teaching_index
        index,_=teaching_index()
        for row in core_library("generator","r2r-en"):
            card=teaching_card(row,"generator",detailed=True)
            self.assertEqual(card['lesson'],index[row['template_id']]['lesson'])
            self.assertEqual(card['skills'],index[row['template_id']]['skills'])
            self.assertTrue(card['counter_boundary'])
            self.assertEqual(card['source'],row['input']['original_instruction'])
            self.assertIn(card['format'],('lesson_summary','complete_initial_output_demonstration'))
'''
RXR='''    def test_common_contract_and_compiler_match_the_reviewed_measurement(self):
        # Prompt/schema golden expectations remain unchanged. Shared source
        # may differ only by the reviewed, exact R2R integration delta.
        from r2r_authoring.integrate import expected as integration, base
        protected=(
            'shared/semantic_contract.md','generator/prompt.md','reviewer/prompt.md',
            'generator/repair.md','generator/output.schema.json','generator/repair.schema.json',
            'reviewer/output.schema.json','host/compile.py','host/template_selector.py','host/rxr_retrieval.py',
        )
        commit=self.pins['measured_source_commit']
        reviewed=integration()
        for path in protected:
            with self.subTest(path=path):
                original=subprocess.check_output(['git','show',commit+':'+path],cwd=ROOT)
                if path in ('host/compile.py','host/template_selector.py'):
                    self.assertEqual(base(path).encode(),original)
                    self.assertEqual((ROOT/path).read_bytes(),reviewed[path].encode())
                else:
                    self.assertEqual((ROOT/path).read_bytes(),original)
'''

def apply(name,text):
    if name=='test_example_injection.py':text=method(text,'test_cards_preserve_decision_and_keep_diagnostic_evidence',INJECTION)
    elif name=='test_r2r_core.py':
        for q in ('In the hallway take a right and go down the hall, keeping straight.','the next door on your right','Stop in the room just past the door on the inside of the doorway.'):
            old='["'+q+'"]';new='[{"subtask_index": 0, "quote": "'+q+'"}]'
            if old not in text:raise ValueError('Missing exact R02 evidence expectation')
            text=text.replace(old,new)
        text=method(text,'test_generator_core_cards_expose_primary_boundary_and_case_rationale',CORE)
    elif name=='test_rxr_prompt_snapshots.py':text=method(text,'test_common_contract_and_compiler_match_the_reviewed_measurement',RXR)
    return text
