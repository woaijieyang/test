"""Regression checks for authored RxR calibration and actual teaching visibility.

These tests check explicit authored evidence and invariants, not navigation SR.
"""
import copy
import json
from pathlib import Path
import subprocess
import unittest

from host.compile import core_library, teaching_card, compile_prompt, runtime_review_output
from host.template_selector import library
from host import protocol
from tools.rxr_teaching_focus import COVERAGE, LESSONS, HANDOFF_REQUIREMENTS, refine_core

ROOT=Path(__file__).resolve().parents[1]
BEFORE='22f6a5b31d75a59b94a7ba991cf0c1f89e7a6e51'


class TeachingFocusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generators=core_library('generator','rxr-en-us')
        cls.reviewers=core_library('reviewer','rxr-en-us')
        cls.dynamic_g={x['template_id']:x for x in library('generator','rxr-en-us')}
        cls.dynamic_r={x['template_id']:x for x in library('reviewer','rxr-en-us')}

    def test_ten_distinct_generator_lessons_are_really_projected(self):
        actual=[teaching_card(x,'generator',True)['applicable_lesson'] for x in self.generators]
        self.assertEqual(actual,[LESSONS[i][0] for i in range(1,11)])
        self.assertEqual(len(set(actual)),10)

    def test_ten_distinct_reviewer_lessons_are_really_projected(self):
        actual=[teaching_card(x,'reviewer',True)['applicable_lesson'] for x in self.reviewers]
        self.assertEqual(actual,[LESSONS[i][1] for i in range(1,11)])
        self.assertEqual(len(set(actual)),10)

    def test_every_core_retains_its_route_and_source_identity(self):
        for role,rows in [('generator',self.generators),('reviewer',self.reviewers)]:
            for i,row in enumerate(rows,1):
                letter='G' if role=='generator' else 'R'
                path=f'{role}/templates/RxR/core/G{i:02d}_RxR-CORE-{letter}{i:02d}.json'
                old=json.loads(subprocess.check_output(['git','show',BEFORE+':'+path],cwd=ROOT))
                for key in ('template_id','role','dataset_scope','language','source','retrieval_tags','pair_id'):
                    self.assertEqual(row.get(key),old.get(key),(path,key))
                if role=='generator':
                    self.assertEqual(row['input'],old['input'])
                    self.assertEqual(row['output']['subtasks'],old['output']['subtasks'])
                else:
                    self.assertEqual(row['review_input'],old['review_input'])

    def test_all_thirty_three_core_requirements_have_authored_local_evidence(self):
        count=0
        for number,authored in COVERAGE.items():
            row=self.reviewers[number-1]
            stages=row['review_input']['candidate']['subtasks']
            coverage=row['expected_review']['source_coverage']
            self.assertEqual(len(coverage),len(authored))
            for c,(rid,meaning,pairs) in zip(coverage,authored):
                self.assertEqual(c['requirement_id'],f'SRC-{rid:02d}')
                self.assertEqual(c['requirement'],meaning)
                self.assertEqual(c['candidate_evidence'],[{'subtask_index':i,'quote':q} for i,q in pairs])
                self.assertIn(c['source_quote'],row['review_input']['original_instruction'])
                for i,q in pairs: self.assertIn(q,stages[i])
                count+=1
        self.assertEqual(count,33)

    def test_close_doorway_description_is_not_lost_from_coverage(self):
        coverage=self.reviewers[4]['expected_review']['source_coverage']
        self.assertIn('two doorways close together',coverage[1]['source_quote'])
        self.assertIn('darker-painted wall',coverage[1]['candidate_evidence'][0]['quote'])

    def test_handoffs_cite_authored_current_review_requirements(self):
        for number,groups in HANDOFF_REQUIREMENTS.items():
            audit=self.reviewers[number-1]['expected_review']
            self.assertEqual([h['source_requirement_ids'] for h in audit['handoffs']],[[f'SRC-{i:02d}' for i in ids] for ids in groups])
            known={r['requirement_id'] for r in audit['source_coverage']}
            for h in audit['handoffs']: self.assertLessEqual(set(h['source_requirement_ids']),known)

    def test_single_stage_core_has_no_invented_handoff(self):
        for number in (3,6):
            audit=self.reviewers[number-1]['expected_review']
            self.assertEqual(audit['handoffs'],[])
            self.assertEqual(next(l['status'] for l in audit['layer_checks'] if l['layer']=='L4_handoffs'),'not_applicable')

    def test_source_ambiguity_core_remains_unresolved(self):
        self.assertEqual(self.generators[9]['output']['status'],'needs_review')
        self.assertEqual(self.generators[9]['output']['subtasks'],[])
        self.assertEqual(self.reviewers[9]['expected_review']['verdict'],'unresolved')

    def test_auxiliary_uncertainty_has_no_actor_audit_comment(self):
        g=self.dynamic_g['RxR-GEN-002'];r=self.dynamic_r['RxR-REV-002']
        stage=g['output']['subtasks'][0]
        self.assertNotIn('The source gives',stage)
        self.assertNotIn('so treat the window',stage)
        self.assertIn('On your right a glass window on your left',stage)
        self.assertIn('black bench on your right',stage)
        self.assertNotIn('black bench on its right',stage)
        self.assertEqual(g['output']['subtasks'],r['review_input']['candidate']['subtasks'])

    def test_foot_of_bed_state_does_not_invent_a_further_traversal(self):
        g=self.dynamic_g['RxR-GEN-020'];stage=g['output']['subtasks'][1]
        self.assertIn('When you are standing at the chair, turn right.',stage)
        self.assertIn('Now you should be standing near the foot of the bed',stage)
        self.assertIn('once you are here, you are done.',stage)
        self.assertNotIn('continue until you are standing near the foot of the bed',stage)
        self.assertIn('Do not go outside; move near the opening and stand there.',g['output']['subtasks'][0])

    def test_expected_view_and_result_remain_states(self):
        stage=self.dynamic_g['RxR-GEN-020']['output']['subtasks'][1]
        self.assertIn('you should see a room or another door',stage)
        self.assertIn('Walk towards that target.',stage)
        self.assertIn('You should now be standing near a desk and at the back of the brown chairs.',stage)
        self.assertNotIn('look towards a room or another door',stage)

    def test_grouping_diagnostic_uses_the_current_reviewed_parent(self):
        parent=self.dynamic_r['RxR-REV-020']['review_input']['candidate']['subtasks']
        child=self.dynamic_r['RxR-DIAG-27']
        self.assertEqual(child['review_input']['candidate']['subtasks'],[' '.join(parent)])
        self.assertEqual(child['expected_review']['dimensions']['source_fidelity'],'pass')
        self.assertEqual(child['expected_review']['dimensions']['segmentation_adequacy'],'issue')
        self.assertEqual(child['expected_review']['handoffs'],[])

    def test_actual_four_phase_prompts_contain_all_case_lessons(self):
        for role,phase in [('generator','initial'),('generator','repair'),('reviewer','review'),('reviewer','recheck')]:
            text,_=compile_prompt(role,phase,profile='rxr-en-us',examples=False)
            offset=0 if role=='generator' else 1
            for i in range(1,11):
                # canonical JSON escapes punctuation but not these plain lesson strings.
                self.assertIn(LESSONS[i][offset],text)

    def test_compact_reviewer_diagnostics_keep_exact_findings(self):
        for row in self.dynamic_r.values():
            if row['expected_review']['verdict']!='revise': continue
            card=teaching_card(row,'reviewer',False)
            audit=runtime_review_output(row)
            self.assertEqual(card['teaching']['findings'],audit['findings'])
            self.assertTrue(card['applicable_lesson'])
            for finding in card['teaching']['findings']:
                self.assertIn(finding['source_quote'],row['review_input']['original_instruction'])
                self.assertTrue(finding['repair']['instruction'])

    def test_all_core_and_changed_pairs_obey_the_active_contract(self):
        for row in self.generators+[self.dynamic_g['RxR-GEN-002'],self.dynamic_g['RxR-GEN-020']]:
            protocol.generator(row['input']['original_instruction'],row['output'])
        for row in self.reviewers+[self.dynamic_r['RxR-REV-002'],self.dynamic_r['RxR-REV-020'],self.dynamic_r['RxR-DIAG-27']]:
            protocol.reviewer(row['review_input']['original_instruction'],row['review_input']['candidate'],runtime_review_output(row))

    def test_core_calibration_rejects_changed_requirement_identity(self):
        rows={r['template_id']:copy.deepcopy(r) for r in self.generators+self.reviewers}
        rows['RXR-CORE-R01']['expected_review']['source_coverage'][0]['requirement_id']='SRC-99'
        with self.assertRaises(ValueError): refine_core(rows)

    def test_core_calibration_rejects_missing_authored_action(self):
        rows={r['template_id']:copy.deepcopy(r) for r in self.generators+self.reviewers}
        row=rows['RXR-CORE-R02']
        row['review_input']['candidate']['subtasks'][0]=row['review_input']['candidate']['subtasks'][0].replace('Do not enter the first doorway.','Enter the first doorway.')
        with self.assertRaises(ValueError): refine_core(rows)

    def test_core_calibration_is_idempotent(self):
        rows={r['template_id']:copy.deepcopy(r) for r in self.generators+self.reviewers}
        before=copy.deepcopy(rows);refine_core(rows)
        self.assertEqual(rows,before)


if __name__=='__main__': unittest.main()
