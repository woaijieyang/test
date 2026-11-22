"""Mechanical and source-grounded teaching checks, not LLM quality claims."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from host import protocol
from host.compile import ROOT, compile_prompt, core_library, runtime_review_output, teaching_card
from host.r2r_retrieval import select
from host.template_selector import (
    library, select_examples, select_r2r_bundle, selection_evidence,
)
from shared.identity import canonical, text_hash


class ComplementarySelectionTests(unittest.TestCase):
    def fixtures(self):
        keys = ['transit_continuation', 'attribute_description', 'hallway_endpoint_turn',
                'endpoint_refinement', 'ordinal_navigation', 'terminal_relation']
        rows = [dict(template_id=f'case-{i}', input=dict(original_instruction=k),
                     teaching_notes={}) for i, k in enumerate(keys)]
        feature = lambda text: (set(text.split()) & set(keys), set())
        return keys, rows, feature

    def choose(self, text, rows, feature, core=(), count=None):
        return select(rows, text, minimum=4, maximum=6, core=core,
                      feature_fn=feature, relation_fn=lambda text: set(),
                      evidence_fn=lambda text, coverage: [], count=count)

    def test_optional_fifth_and_sixth_require_new_relationships(self):
        keys, rows, feature = self.fixtures()
        for n in (4, 5, 6):
            chosen, trace = self.choose(' '.join(keys[:n]), rows, feature)
            self.assertEqual(len(chosen), n)
            for extra in trace[4:]:
                self.assertEqual(extra['selection_reason'], 'uncovered_relation')
                self.assertTrue(extra['optional_coverage'])

    def test_core_reduces_redundancy_but_never_replaces_base(self):
        keys, rows, feature = self.fixtures()
        core = [dict(input=dict(original_instruction=' '.join(keys)))]
        chosen, trace = self.choose(' '.join(keys), rows, feature, core=core)
        self.assertEqual(len(chosen), 4)
        self.assertTrue(all(x['core_overlap'] for x in trace))

    def test_length_alone_does_not_add_examples(self):
        keys, rows, feature = self.fixtures()
        short, _ = self.choose(' '.join(keys[:4]), rows, feature)
        long, _ = self.choose(' '.join(keys[:4]) + ' padding'*200, rows, feature)
        self.assertEqual([r['template_id'] for r in short], [r['template_id'] for r in long])

    def test_explicit_count_and_invalid_types(self):
        keys, rows, feature = self.fixtures()
        for n in (4, 5, 6):
            self.assertEqual(len(self.choose('query', rows, feature, count=n)[0]), n)
        for bad in (True, 4.0, 3, 7):
            with self.assertRaises(ValueError):self.choose('query', rows, feature, count=bad)

    def test_bundle_pairs_once_and_records_real_source_spans(self):
        text = 'Walk through the open door, continue past the chairs and stop near the table.'
        bundle = select_r2r_bundle(text)
        rev = {x['template_id']: x for x in library('reviewer', 'r2r-en')}
        n = len(bundle['generator'])
        self.assertTrue(4 <= n <= 6)
        self.assertEqual([rev[i]['pair_id'] for i in bundle['reviewer'][:n]], bundle['generator'])
        self.assertTrue(2 <= len(bundle['reviewer'])-n <= 3)
        for role in ('generator', 'reviewer'):
            trace = selection_evidence(role, 'r2r-en', text, bundle[role])
            for row in trace:
                for span in row['matched_source_spans']:
                    self.assertEqual(text[span['start']:span['end']], span['quote'])

    def test_runtime_does_not_independently_reselect_reviewer(self):
        from adapter.source import Source
        from host.run import run_record
        from test_runtime_contract_v2 import SOURCE, generator_candidate, reviewer_output
        src=Source('bundle-test','R2R','en',SOURCE)
        candidate=generator_candidate(repaired=True)
        review=reviewer_output(candidate,repaired=True)
        replies=[candidate,review]
        def transport(req):
            return {'output':replies.pop(0), 'receipt':{
                'model':req['model'],'effort':req['effort'],'request_id':str(len(replies)),
                'provider_request_sha256':__import__('shared.identity',fromlist=['obj_hash']).obj_hash(req)}}
        with patch('host.run.select_r2r_bundle', wraps=select_r2r_bundle) as resolved:
            out=run_record(src,transport,pins={r:{'model':'fixture','effort':'low'} for r in ('generator','reviewer')})
        self.assertEqual(resolved.call_count,1)
        self.assertIn(out['disposition'],('accepted_candidate','accepted_source_exact'))


class TeachingConsistencyTests(unittest.TestCase):
    def examples(self):
        return {r['template_id']:r for r in library('reviewer','r2r-en')}

    def test_repaired_and_added_diagnostics_pass_full_runtime_protocol(self):
        bank=self.examples()
        for name in ('07','19','27','28','29'):
            row=bank['R2R-DIAG-'+name]
            audit=runtime_review_output(row)
            protocol.reviewer(row['review_input']['original_instruction'],row['review_input']['candidate'],audit)
            self.assertEqual(audit['verdict'],'revise')

    def test_stop_omission_does_not_corrupt_ordinal_coverage(self):
        review=self.examples()['R2R-DIAG-07']['expected_review']
        self.assertEqual(review['source_coverage'][0]['status'],'covered')
        self.assertEqual(review['findings'][0]['source_requirement_ids'],['SRC-02'])
        self.assertEqual(review['stage_checks'][0]['ending']['kind'],'unspecified')
        self.assertIn('explicitly',review['stage_checks'][0]['ending']['text'])

    def test_orientation_and_stop_are_both_reviewed(self):
        audit=self.examples()['R2R-DIAG-19']['expected_review']
        self.assertEqual(audit['source_coverage'][0]['status'],'covered')
        self.assertEqual({rid for f in audit['findings'] for rid in f['source_requirement_ids']},{'SRC-02','SRC-03'})
        self.assertEqual(audit['dimensions']['closure_handoff'],'issue')
        self.assertEqual(audit['layer_checks'][3]['status'],'issue')

    def test_added_corruptions_preserve_traceable_source_identity(self):
        for name in ('27','28','29'):
            row=self.examples()['R2R-DIAG-'+name]
            base_id=row['provenance']['source_template']
            path=ROOT/'generator/templates/R2R/val_seen'/f'{base_id[-3:]}_{base_id}.json'
            base=json.loads(path.read_bytes())
            self.assertEqual(row['review_input']['original_instruction'],base['input']['original_instruction'])
            self.assertEqual(row['source'],base['source'])
            self.assertTrue(row['provenance']['candidate_corruption_is_authored_not_model_output'])

    def test_rules_and_contrast_boundaries_reach_actual_prompt(self):
        source='Walk through the open doors and follow the hall until you reach the room.'
        for role,phases in [('generator',('initial','repair')),('reviewer',('review','recheck'))]:
            ids=select_examples(role,'r2r-en',source)
            for phase in phases:
                text,_=compile_prompt(role,phase,profile='r2r-en',selected_ids=ids,original_instruction=source)
                self.assertIn('Completion versus segmentation value',text)
                self.assertIn('transfer_boundary',text)
                self.assertIn('counter_boundary',text)
                self.assertNotIn('RXR ROLE GUIDANCE',text)
                if role=='reviewer':self.assertIn('Material consequences, not edit distance',text)
        for row in self.examples().values():
            card=teaching_card(row,'reviewer',detailed=False)
            self.assertTrue(card['transfer_boundary'])
            self.assertTrue(card['counter_boundary'])


class RxRIsolationTests(unittest.TestCase):
    def test_mixed_profile_sequence_preserves_frozen_rxr_requests(self):
        rows=json.loads((ROOT/'tests/fixtures/rxr_contract.json').read_bytes())
        for row in rows:
            def snapshot():
                ids=select_examples(row['role'],'rxr-en-us',row['source'])
                prompt,schema=compile_prompt(row['role'],row['phase'],profile='rxr-en-us',selected_ids=ids,original_instruction=row['source'])
                return ids,text_hash(prompt),text_hash(canonical(schema))
            before=snapshot()
            select_r2r_bundle(row['source'])
            after=snapshot()
            self.assertEqual(before,after)
            self.assertEqual(after,(row['ids'],row['prompt_sha256'],row['schema_sha256']))
