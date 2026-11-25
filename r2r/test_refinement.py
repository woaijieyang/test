"""Detailed R2R evidence and request tests; not navigation performance claims."""
import copy,json,re,subprocess,unittest
from unittest.mock import patch
from host.compile import ROOT,compile_prompt,core_library
from host.template_selector import library
from host import protocol
from r2r.selection import select_bundle,teaching_index,_choose
from r2r.teaching import card,dynamic_is_detailed
from shared.identity import canonical,text_hash
EVIDENCE='9dd24a655a845d59698e835c0326fbf73db5fbb8'


def bank(role):
    return {r['template_id']:r for r in core_library(role,'r2r-en')+library(role,'r2r-en')}


def parsed_cards(prompt):
    out=[]
    for line in prompt.splitlines():
        if line.startswith('{'):
            try: obj=json.loads(line)
            except json.JSONDecodeError: continue
            if isinstance(obj,dict) and 'template_id' in obj and 'format' in obj:out.append(obj)
    return out


class DetailedRequests(unittest.TestCase):
    def test_fixed_core_always_shows_complete_active_output(self):
        for role in ('generator','reviewer'):
            schema='generator/output.schema.json' if role=='generator' else 'reviewer/output.schema.json'
            for row in core_library(role,'r2r-en'):
                with self.subTest(template=row['template_id']):
                    projected=card(row,role,True)
                    self.assertIn('expected_output',projected)
                    protocol.validate(schema,projected['expected_output'])
                    self.assertEqual(projected['expected_output'],row['output'] if role=='generator' else row['expected_review'])
                    compact=card(row,role,False)
                    self.assertNotIn('expected_output',compact)
                    self.assertEqual(compact['format'],'lesson_summary')

    def test_two_complete_dynamic_pairs_and_first_diagnostic_in_all_phases(self):
        source='Exit the bedroom and take the first door on your right, then stop by the chair.'
        bundle=select_bundle(source)
        for role,phases in [('generator',('initial','repair')),('reviewer',('review','recheck'))]:
            ids=bundle[role];by=bank(role)
            for phase in phases:
                prompt,_=compile_prompt(role,phase,profile='r2r-en',original_instruction=source,selected_ids=ids)
                cards=parsed_cards(prompt)
                self.assertEqual([c['template_id'] for c in cards],[r['template_id'] for r in core_library(role,'r2r-en')]+ids)
                for pos,shown in enumerate(cards):
                    self.assertEqual(shown['source'],(by[shown['template_id']].get('input') or by[shown['template_id']]['review_input'])['original_instruction'])
                    expected_detail=pos<10 or dynamic_is_detailed(role,ids,pos-10)
                    self.assertEqual('expected_output' in shown,expected_detail)
                self.assertGreaterEqual(sum('expected_output' in c for c in cards[10:]),2)
                if role=='reviewer':
                    first_diag=next(i for i in ids if not by[i].get('pair_id'))
                    self.assertIn('expected_output',next(c for c in cards if c['template_id']==first_diag))

    def test_projection_receipts_match_actual_compiled_dynamic_cards(self):
        source='Walk to the end of the hallway, turn left and stop in the first doorway.'
        bundle=select_bundle(source)
        for role,phase in [('generator','initial'),('reviewer','review')]:
            prompt,_=compile_prompt(role,phase,profile='r2r-en',selected_ids=bundle[role],original_instruction=source)
            cards={r['template_id']:r for r in parsed_cards(prompt)}
            for receipt in bundle['evidence'][role]['projection']:
                payload=canonical(cards[receipt['template_id']])
                self.assertEqual(receipt['projection_sha256'],text_hash(payload))
                self.assertEqual(receipt['projection_utf8_bytes'],len(payload.encode()))
                self.assertEqual(receipt['detailed'],'expected_output' in cards[receipt['template_id']])

    def test_disabling_optional_examples_does_not_remove_detailed_core(self):
        for role,phase in [('generator','initial'),('reviewer','recheck')]:
            text,_=compile_prompt(role,phase,profile='r2r-en',examples=False,original_instruction='Go to the doorway.')
            cards=parsed_cards(text)
            self.assertEqual(len(cards),10)
            self.assertTrue(all('expected_output' in c for c in cards))

    def test_complete_examples_are_defensive_copies(self):
        row=core_library('generator','r2r-en')[0];before=copy.deepcopy(row)
        shown=card(row,'generator',True);shown['expected_output']['subtasks'][0]='corrupted test text'
        self.assertEqual(row,before)


class EvidencePreservation(unittest.TestCase):
    def test_unchanged_positive_candidates_retain_evaluated_text(self):
        for row in bank('generator').values():
            tid=row['template_id']
            number=int(row['provenance']['core_curated_from'][-3:]) if '-CORE-' in tid else int(tid[-3:])
            if number in (20,23,30,35):continue
            path=next(i['path'] for i in teaching_index()[0].values() if i['template_id']==tid)
            old=json.loads(subprocess.check_output(['git','show',EVIDENCE+':'+path],cwd=ROOT))
            with self.subTest(template=tid):self.assertEqual(row['output']['subtasks'],old['output']['subtasks'])

    def test_explicit_exit_anchor_is_not_uniformly_labeled_inherited_pose(self):
        row=bank('generator')['R2R-GEN-015'];stage=row['output']['stage_audit'][1]
        self.assertEqual(stage['entry']['mode'],'explicit_context')
        self.assertTrue(stage['entry']['candidate_quotes'])
        self.assertIn('After exiting the bedroom',row['output']['subtasks'][1])
        self.assertTrue(row['output']['stage_audit'][0]['carryover'])
        self.assertTrue(row['output']['handoffs'][0]['shared_context'])
        for q in stage['entry']['candidate_quotes']:self.assertIn(q,row['output']['subtasks'][1])

    def test_stage_local_source_evidence_not_whole_route_broadcast(self):
        row=bank('generator')['R2R-CORE-G02'];source=row['input']['original_instruction'].strip()
        audits=row['output']['stage_audit']
        self.assertEqual(len(audits),3)
        self.assertTrue(all(source not in a['source_quotes'] for a in audits))
        self.assertNotEqual(audits[0]['source_quotes'],audits[1]['source_quotes'])
        self.assertTrue(all(row['output']['handoffs'][i]['shared_context'] for i in range(2)))

    def test_destination_and_selection_condition_are_not_lost(self):
        row=bank('generator')['R2R-GEN-028'];a=row['output']['stage_audit'][0]
        self.assertEqual(a['ending']['kind'],'explicit_event')
        self.assertEqual(a['ending']['stop_scope'],'none')
        self.assertIn('center door on right',a['conditions']['candidate_quotes'])
        self.assertTrue(row['teaching_notes']['reusable_rule'])

    def test_known_reference_and_attachment_repairs_remain(self):
        b=bank('generator')
        self.assertIn('first room to the left of the staircase',b['R2R-GEN-030']['output']['subtasks'][1])
        self.assertIn('enter the hallway to the slight right past the chair',b['R2R-GEN-035']['output']['subtasks'][0])
        self.assertNotIn('After passing the chair',b['R2R-GEN-035']['output']['subtasks'][1])

    def test_every_active_positive_has_a_transfer_rule_and_exact_fields(self):
        for tid,row in bank('generator').items():
            with self.subTest(template=tid):
                self.assertTrue(row['teaching_notes']['reusable_rule'])
                protocol.generator(row['input']['original_instruction'],row['output'])
                for audit,stage in zip(row['output']['stage_audit'],row['output']['subtasks']):
                    for name in ('entry','target','process','ending','conditions'):
                        for quote in audit[name]['candidate_quotes']:self.assertIn(quote,stage)

    def test_full_authoring_deterministically_checks_without_writing(self):
        from r2r_authoring.build import materialize
        outputs=materialize()
        for rel,content in outputs.items():self.assertEqual((ROOT/rel).read_bytes(),content,rel)


class WorkflowRules(unittest.TestCase):
    def test_named_hierarchy_and_five_element_workflow(self):
        registry=json.loads((ROOT/'provenance/r2r_rule_links.json').read_bytes())['nodes']
        index={r['id']:r for r in registry};self.assertEqual(len(index),len(registry))
        for role in ('generator','reviewer'):
            text=(ROOT/role/'dataset_rules/r2r_en.md').read_text()
            for term in ('Entry','Target','Process','Ending','Conditions','G0' if role=='generator' else 'R0','G1' if role=='generator' else 'R1'):
                self.assertIn(term,text)
            self.assertNotRegex(text,r'LLM-decompose-v|\bv6\.6')
        for node in registry:
            self.assertTrue(node['title'])
            if node['parent']:
                self.assertEqual(index[node['parent']]['level'],node['level']-1)
                self.assertEqual(index[node['parent']]['role'],node['role'])

    def test_critical_failure_and_success_boundaries_are_named(self):
        text=(ROOT/'generator/dataset_rules/r2r_en.md').read_text()
        for title in ('Grounded language repair','Sustained constraints','Same-event refinement','Coupled transit','Minimal sufficient entry','Destination strength','Selective acceptance'):
            self.assertIn(title,text)
        self.assertIn('short stair-plus-room',text)
        self.assertIn('separate placement/wait stage',text)
        self.assertIn('count origin',text)


class ComplementaryRanking(unittest.TestCase):
    def test_new_skill_beats_a_redundant_broad_case(self):
        def row(tid,skills):return {'template_id':tid,'input':{'original_instruction':tid},'skills':skills}
        rows=[row('a',['entry','terminal']),row('b',['entry','terminal']),row('c',['ordinal']),row('d',['frame']),row('e',['entry'])]
        index={r['template_id']:{'status':'dynamic','skills':r['skills'],'content_sha256':r['template_id']} for r in rows}
        with patch('r2r.selection._verify'),patch('r2r.selection.signals',return_value={k:[] for k in ('entry','terminal','ordinal','frame')}):
            chosen,trace=_choose(rows,'query',index,[],4,6)
        ids=[r['template_id'] for r in chosen]
        self.assertEqual(set(ids[:3]),{'a','c','d'})
        self.assertEqual(trace['eligible_pool'],['a','b','c','d','e'])
        self.assertTrue(all('incremental_score' in x for step in trace['ranking'] for x in step['ordered_candidates']))

    def test_actual_source_slices_and_count_pair_bounds(self):
        rev=bank('reviewer')
        queries=['','Exit the room and turn left down the hallway.','Go halfway down the second flight of stairs and wait.','Enter the first room to the left of the staircase.','Walk on the carpet toward the table and stop before it.']
        for q in queries:
            bundle=select_bundle(q);g=bundle['generator'];r=bundle['reviewer']
            self.assertTrue(4<=len(g)<=6);self.assertTrue(2<=len(r)-len(g)<=3)
            self.assertEqual([rev[i]['pair_id'] for i in r[:len(g)]],g)
            self.assertEqual(bundle,select_bundle(q))
            for item in bundle['evidence']['generator']['selected']:
                for spans in item['matched_source_spans'].values():
                    for span in spans:self.assertEqual(q[span['start']:span['end']],span['quote'])


if __name__=='__main__':unittest.main()
