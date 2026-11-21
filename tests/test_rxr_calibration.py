import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from host.compile import ROOT, compile_prompt, core_library, runtime_review_output
from host import protocol
from host.run import dataset_rules_metadata, prompt_components_metadata, template_bundle_metadata
from host.template_selector import library, source, select_examples
from host.rxr_retrieval import features, rank_examples
from host.rxr_assets import validate_training_assets, validate_training_library
from tools.rxr_lesson_specs import LESSONS


class RxRCalibrationTests(unittest.TestCase):
    def test_training_sources_are_distinct_train_only(self):
        registry=validate_training_assets()
        self.assertEqual(len(registry['records']),8)
        self.assertEqual(len(registry['templates']),24)
        self.assertEqual(registry['source_split'],'train')
        for role in ('generator','reviewer'):
            rows=library(role,'rxr-en-us')
            validate_training_library(role,rows)
            train=[r for r in rows if '-TRAIN-' in r['template_id']]
            self.assertEqual(len(train),8 if role=='generator' else 16)
            self.assertTrue(all(r['source']['split']=='train' for r in train))
            self.assertFalse(any(r['source']['split']=='val_unseen' for r in rows))

    def test_training_generators_and_both_reviews_pass_active_protocol(self):
        generators={r['template_id']:r for r in library('generator','rxr-en-us') if '-TRAIN-' in r['template_id']}
        for row in generators.values():
            with self.subTest(template=row['template_id']):
                protocol.generator(source(row),row['output'])
        for row in library('reviewer','rxr-en-us'):
            if '-TRAIN-' not in row['template_id']:
                continue
            with self.subTest(template=row['template_id']):
                protocol.reviewer(source(row),row['review_input']['candidate'],runtime_review_output(row))
                if row.get('pair_id'):
                    self.assertEqual(row['review_input']['candidate']['subtasks'],generators[row['pair_id']]['output']['subtasks'])
                    self.assertEqual(row['expected_review']['verdict'],'pass')
                else:
                    self.assertEqual(row['expected_review']['verdict'],'revise')
                    self.assertEqual(len(row['expected_review']['findings']),1)

    def test_diagnostics_change_exactly_one_authored_span(self):
        by_id={r['template_id']:r for r in library('reviewer','rxr-en-us')}
        for case in LESSONS:
            paired=by_id['RxR-REV-TRAIN-'+case['id']]
            diagnostic=by_id['RxR-DIAG-TRAIN-'+case['id']]
            expected=copy.deepcopy(paired['review_input']['candidate']['subtasks'])
            mutation=case['mutation']; i=mutation['stage']
            self.assertEqual(expected[i].count(mutation['old']),1)
            expected[i]=expected[i].replace(mutation['old'],mutation['new'],1)
            self.assertEqual(expected,diagnostic['review_input']['candidate']['subtasks'])
            self.assertEqual(source(paired),source(diagnostic))

    def test_fixed_core_identity_and_count_remain_unchanged(self):
        for role,letter in [('generator','G'),('reviewer','R')]:
            ids=[r['template_id'] for r in core_library(role,'rxr-en-us')]
            self.assertEqual(ids,[f'RXR-CORE-{letter}{i:02d}' for i in range(1,11)])

    def test_conditional_observation_is_not_a_branch_keyword(self):
        cues,_=features('If you look right, you will see an archway. Walk towards that archway.')
        self.assertIn('conditional_viewpoint',cues)
        self.assertNotIn('conditional_route',cues)
        cues,_=features('If the door is closed, use the other doorway; otherwise continue.')
        self.assertIn('conditional_route',cues)

    def test_repetition_and_return_remain_different_signals(self):
        cues,_=features('Walk straight down the hallway. Walk straight down the hallway until you see a sign.')
        self.assertIn('oral_repetition',cues)
        self.assertNotIn('return_identity',cues)
        self.assertIn('return_identity',features('Return through the same door.')[0])

    def test_local_correction_and_paired_choice_are_retrievable(self):
        self.assertIn('local_correction',features('Veer left, or rather right.')[0])
        self.assertIn('paired_spatial_choice',features('Choose the rightmost of the two doors.')[0])
        self.assertNotIn('paired_spatial_choice',features('Turn right at the next door.')[0])

    def test_deterministic_complementary_selection_and_pairs(self):
        by_id={r['template_id']:r for r in library('reviewer','rxr-en-us')}
        for case in LESSONS:
            text=case['source']+' Preserve the described route.'
            gen=select_examples('generator','rxr-en-us',text)
            rev=select_examples('reviewer','rxr-en-us',text)
            self.assertEqual(gen,select_examples('generator','rxr-en-us',text))
            self.assertTrue(2<=len(gen)<=4)
            self.assertEqual([by_id[i]['pair_id'] for i in rev[:len(gen)]],gen)
            self.assertTrue(0<=len(rev)-len(gen)<=2)
            self.assertEqual(len(gen),len(set(gen)))

    def test_exact_query_echo_is_not_selected(self):
        rows=library('generator','rxr-en-us')
        for case in LESSONS:
            selected=select_examples('generator','rxr-en-us',case['source'])
            self.assertNotIn('RxR-GEN-TRAIN-'+case['id'],selected)

    def test_foreign_rows_fail_closed(self):
        with self.assertRaises(ValueError):
            rank_examples(library('generator','r2r-en'),'walk to a doorway',2)

    def test_r2r_selection_and_compilation_survive_interleaving(self):
        text='Exit the bedroom and enter the second door on the left.'
        before={}
        for role,phase in [('generator','initial'),('reviewer','review'),('generator','repair'),('reviewer','recheck')]:
            ids=select_examples(role,'r2r-en',text)
            before[(role,phase)]=(ids,compile_prompt(role,phase,profile='r2r-en',selected_ids=ids,original_instruction=text))
        for case in LESSONS:
            for role in ('generator','reviewer'):
                select_examples(role,'rxr-en-us',case['source'])
        for (role,phase),(ids,compiled) in before.items():
            self.assertEqual(select_examples(role,'r2r-en',text),ids)
            self.assertEqual(compile_prompt(role,phase,profile='r2r-en',selected_ids=ids,original_instruction=text),compiled)

    def test_four_phase_guidance_and_provenance(self):
        text='If you look right, you see an arch. Walk through it and stop.'
        for role,phase in [('generator','initial'),('reviewer','review'),('generator','repair'),('reviewer','recheck')]:
            ids=select_examples(role,'rxr-en-us',text)
            prompt,_=compile_prompt(role,phase,profile='rxr-en-us',selected_ids=ids,original_instruction=text)
            self.assertIn('smallest supported scope',prompt)
            self.assertIn('Every stage requires an intelligible, supported entry state',prompt)
            files=[row['path'] for row in prompt_components_metadata(role,phase,'rxr-en-us')['files']]
            self.assertIn('host/rxr_retrieval.py',files)
            self.assertIn('provenance/rxr_training_sources.json',files)
        self.assertNotIn('host/rxr_retrieval.py',dataset_rules_metadata('r2r-en')['files'])

    def test_task_bundle_checks_training_disk_bytes_not_only_cached_library(self):
        registry=validate_training_assets()
        path=ROOT/registry['templates'][0]['path']
        original=path.read_bytes()
        from pathlib import Path as RealPath
        def altered(p):
            return original+b' ' if p==path else real_read(p)
        real_read=RealPath.read_bytes
        ids=select_examples('generator','rxr-en-us','Walk to the archway.')
        with patch.object(RealPath,'read_bytes',altered):
            with self.assertRaises(ValueError):
                template_bundle_metadata('generator','rxr-en-us',ids)

    def test_training_source_identity_cannot_be_forged(self):
        rows=copy.deepcopy(library('generator','rxr-en-us'))
        row=next(r for r in rows if '-TRAIN-' in r['template_id'])
        row['source']['split']='val_unseen'
        with self.assertRaises(ValueError):
            validate_training_library('generator',rows)

    def test_bad_diagnostic_cannot_be_relabelled_pass(self):
        row=next(r for r in library('reviewer','rxr-en-us') if r['template_id'].startswith('RxR-DIAG-TRAIN-'))
        review=runtime_review_output(row); review['verdict']='pass'
        from shared.identity import ContractError
        with self.assertRaises(ContractError):
            protocol.reviewer(source(row),row['review_input']['candidate'],review)

if __name__=='__main__':
    unittest.main()
