"""Regression tests for source-local repairs, selection semantics and ownership.

These are deterministic engineering tests. They do not measure LLM correctness
or navigation success.
"""
import copy, hashlib, json, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from host.compile import ROOT, core_library, compile_prompt
from host.template_selector import library
from host import protocol
from host.r2r.selection import _choose, select_bundle, teaching_index
from host.r2r.relations import route_family
from host.r2r.teaching import card
from tools.r2r_authoring.contrast import examples
from tools.r2r_authoring.detail import author_paired


def bank():
    return {r['template_id']:r for role in ('generator','reviewer') for r in core_library(role,'r2r-en')+library(role,'r2r-en')}


class AuthoredEvidence(unittest.TestCase):
    def test_staircase_reference_and_target_evidence(self):
        r=bank()['R2R-GEN-030'];out=r['output']
        self.assertIn('first room to the left of the staircase',out['subtasks'][1])
        self.assertTrue(any('to the left of the staircase' in q for q in out['stage_audit'][1]['target']['candidate_quotes']))
        self.assertNotEqual(out['stage_audit'][0]['source_quotes'],out['stage_audit'][1]['source_quotes'])
        self.assertNotIn('first room on the left',json.dumps(r['teaching_notes']))
        self.assertIn('source-required final',out['stage_audit'][1]['ending']['text'])

    def test_hallway_boundary_and_wait_are_not_misdescribed(self):
        r=bank()['R2R-GEN-035'];n=r['teaching_notes']
        self.assertIn('hallway entry',n['handoff_focus'].lower())
        self.assertNotIn("Stage 1 ends with 'passing",n['why_this_case_matters'])
        self.assertIn('terminal',r['output']['stage_audit'][1]['ending']['stop_scope'])
        self.assertIn('source-required final',r['output']['stage_audit'][1]['ending']['text'])

    def test_valid_coarse_review_preserves_conditions_without_false_defect(self):
        r=bank()['R2R-CORE-R06'];a=r['expected_review']
        self.assertEqual(a['verdict'],'pass');self.assertFalse(a['findings'])
        self.assertGreaterEqual(len(a['stage_checks'][0]['conditions']['candidate_quotes']),3)
        self.assertNotIn('This is a grouping defect',json.dumps(r['teaching_notes']))

    def test_fine_grained_review_has_event_coverage_and_real_handoffs(self):
        r=bank()['R2R-DIAG-28'];a=r['expected_review']
        self.assertEqual(len(a['source_coverage']),3)
        self.assertEqual([c['candidate_evidence'][0]['subtask_index'] for c in a['source_coverage']],[0,1,2])
        for stage in a['stage_checks']:
            self.assertNotEqual(stage['target']['text'],stage['process']['text'])
            self.assertTrue(stage['conditions']['candidate_quotes'])
        for h in a['handoffs']:
            self.assertTrue(h['shared_context']);self.assertNotIn('finding below',h['handoff_rationale'])
        protocol.reviewer(r['review_input']['original_instruction'],r['review_input']['candidate'],a)

    def test_paired_authoring_does_not_trust_generator_self_audit(self):
        g=copy.deepcopy(bank()['R2R-GEN-035'])
        path='reviewer/templates/R2R/paired/035_R2R-REV-035.json'
        old=json.loads(subprocess.check_output(['git','show','9dd24a655a845d59698e835c0326fbf73db5fbb8:'+path],cwd=ROOT))
        left=copy.deepcopy(old);right=copy.deepcopy(old);author_paired(left,g,35)
        g['output']['stage_audit']=[{'untrusted':'invented endpoint'}];g['output']['handoffs']=[{'untrusted':'already done'}]
        author_paired(right,g,35)
        self.assertEqual(left['expected_review'],right['expected_review'])

    def test_changed_candidate_cannot_inherit_a_supported_source_completion(self):
        g=copy.deepcopy(bank()['R2R-GEN-035']);g['output']['subtasks'][0]=g['output']['subtasks'][0].replace('enter the hallway','look at the hallway')
        r=copy.deepcopy(bank()['R2R-REV-035'])
        with self.assertRaises(ValueError):author_paired(r,g,35)

    def test_all_stop_scopes_preserve_source_request(self):
        for r in bank().values():
            if r['role']!='generator':continue
            for s in r['output']['stage_audit']:
                if s['ending']['stop_scope']=='terminal':
                    self.assertNotIn('it adds no physical STOP',s['ending']['text'])
                    self.assertTrue(s['ending']['candidate_quotes'])

    def test_synthetic_additions_have_no_fabricated_official_identity(self):
        for path,r in examples().items():
            self.assertEqual(r['source']['split'],'authored_synthetic')
            self.assertFalse(r['provenance']['is_official_dataset_record'])
            self.assertIsNone(r['source']['episode_id']);self.assertIsNone(r['source']['trajectory_id'])
            if r['role']=='generator':protocol.generator(r['input']['original_instruction'],r['output'])
            else:protocol.reviewer(r['review_input']['original_instruction'],r['review_input']['candidate'],r['expected_review'])

    def test_branch_and_return_defects_do_not_become_false_grouping_errors(self):
        for tid in ('R2R-DIAG-30','R2R-DIAG-31'):
            r=bank()[tid];a=r['expected_review']
            self.assertEqual(a['verdict'],'revise')
            self.assertEqual(a['dimensions']['segmentation_adequacy'],'pass')
            self.assertTrue(a['findings'][0]['repair']['protected_requirements'])

    def test_compact_projection_retains_actual_process(self):
        for r in bank().values():
            c=card(r,r['role'],False)
            for s in c['stage_semantics']:
                self.assertIn('process',s);self.assertIn('entry',s)


class RelationSelection(unittest.TestCase):
    def fake(self,tid,facet,polarity='generate',family=None):
        return dict(template_id=tid,input=dict(original_instruction=tid)),dict(status='dynamic',skills=['entry'],retrieval_skills=['entry'],facets=[facet],teaching_polarity=polarity,content_sha256=tid,route_family=family)

    def choose(self,rows,index,core=(),prior=(),minimum=4,maximum=6,source_family=None):
        with patch('host.r2r.selection._verify'),patch('host.r2r.selection.signals',return_value={'entry':[]}),patch('host.r2r.selection.facet_signals',return_value={str(i):[] for i in range(8)}):
            return _choose(rows,'query',index,core,minimum,maximum,prior=prior,source_family=source_family)

    def test_optional_slots_use_new_facets_even_when_core_has_same_skill(self):
        pairs=[self.fake(str(i),str(i)) for i in range(7)];core=[pairs[0][0]]
        rows=[r for r,_ in pairs[1:]];index={r['template_id']:m for r,m in pairs}
        selected,trace=self.choose(rows,index,core)
        self.assertEqual(len(selected),6)
        self.assertTrue(all(t['added_lesson_units'] for t in trace['selected'][4:]))
        self.assertTrue(all(t['selection_reason']=='uncovered_facet_or_contrast' for t in trace['selected'][4:]))

    def test_no_extra_slots_for_repeated_same_facet(self):
        pairs=[self.fake(str(i),'0') for i in range(7)]
        selected,_=self.choose([r for r,_ in pairs[1:]],{r['template_id']:m for r,m in pairs},[pairs[0][0]])
        self.assertEqual(len(selected),4)

    def test_positive_pair_does_not_suppress_negative_contrast(self):
        pairs=[self.fake('positive','0','accept'),self.fake('repeat','0','accept'),self.fake('contrast','0','detect')]
        selected,trace=self.choose([r for r,_ in pairs[1:]],{r['template_id']:m for r,m in pairs},prior=[pairs[0][0]],minimum=1,maximum=1)
        self.assertEqual(selected[0]['template_id'],'contrast')
        self.assertIn('0|accept',trace['prior_lesson_units'])

    def test_explicit_route_family_exclusion_is_fail_closed(self):
        pairs=[self.fake(str(i),str(i),family='same') for i in range(5)]
        with self.assertRaises(ValueError):self.choose([r for r,_ in pairs],{r['template_id']:m for r,m in pairs},source_family='same')

    def test_selected_route_family_is_not_repeated(self):
        pairs=[self.fake(str(i),str(i),family='same' if i<2 else str(i)) for i in range(6)]
        selected,trace=self.choose([r for r,_ in pairs],{r['template_id']:m for r,m in pairs})
        self.assertLessEqual(len({r['template_id'] for r in selected}&{'0','1'}),1)
        self.assertTrue(trace['excluded'])

    def test_host_family_identity_uses_only_explicit_scene_and_path(self):
        self.assertEqual(route_family({'scene_id':'mp3d/scan/scan.glb','path_id':42},'val_seen'),'R2R|val_seen|scan|42')
        self.assertIsNone(route_family({'path_id':42},'val_seen'))
        self.assertIsNone(route_family({'scene_id':'scan','path_id':42},'unspecified'))

    def test_branch_and_return_lessons_are_retrievable(self):
        b=select_bundle('If the passage on your left is open, enter it; otherwise use the door on your right and wait.')
        self.assertIn('R2R-GEN-036',b['generator']);self.assertIn('R2R-DIAG-30',b['reviewer'])
        b=select_bundle('Leave the door, walk around the chair and return to the same door before waiting.')
        self.assertIn('R2R-GEN-037',b['generator']);self.assertIn('R2R-DIAG-31',b['reviewer'])

    def test_rule_and_facet_mappings_are_role_scoped(self):
        index,_=teaching_index();rules={n['id'] for n in json.loads((ROOT/'provenance/r2r_rule_links.json').read_bytes())['nodes']}
        for item in index.values():
            self.assertTrue(item['rule_ids']);self.assertLessEqual(set(item['rule_ids']),rules)
            prefix='G-' if item['role']=='generator' else 'R-'
            self.assertTrue(all(r.startswith(prefix) for r in item['rule_ids']))
            self.assertNotIn('lost_action',item['retrieval_skills']);self.assertNotIn('grouping',item['retrieval_skills'])

    def test_task_bundle_pins_relation_implementation(self):
        from host.run import prompt_components_metadata
        # The profile freeze must include all runtime retrieval code, not only IDs.
        data=prompt_components_metadata('generator','initial','r2r-en')
        self.assertIn('host/r2r/relations.py',[r['path'] for r in data['files']])

    def test_current_core_overlap_is_reported_without_silent_core_removal(self):
        r=core_library('generator','r2r-en')[0];b=select_bundle(r['input']['original_instruction'])
        self.assertTrue(b['evidence']['generator']['fixed_core_overlap'])
        prompt,_=compile_prompt('generator','initial',profile='r2r-en',selected_ids=b['generator'])
        self.assertIn(r['template_id'],prompt)


class LayoutAndInventory(unittest.TestCase):
    def test_module_owned_paths_have_no_root_copies(self):
        moves=json.loads((ROOT/'provenance/layout_migration.json').read_bytes())['moves']
        for old,new in moves.items():
            self.assertFalse((ROOT/old).exists(),old);self.assertTrue((ROOT/new).is_file(),new)
        self.assertTrue((ROOT/'FILE_HASHES.json').is_file())
        from tools.r2r_authoring.integrate import expected
        workflow=expected()['.github/workflows/rxr-development.yml']
        self.assertEqual(workflow,(ROOT/'.github/workflows/rxr-development.yml').read_text())
        self.assertNotIn("      - '.github/workflows/rxr-development.yml'",workflow)
        self.assertIn('workflow_dispatch:',workflow)

        # A clean build and an incrementally refreshed tree must serialize the
        # same global integrity manifest, regardless of insertion history.
        from tools.r2r_authoring import verify
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'provenance').mkdir()
            (root/'provenance/r2r_profile_integrity.json').write_text('{"files": []}')
            (root/'z.txt').write_text('last');(root/'a.txt').write_text('first')
            manifest=root/'FILE_HASHES.json'
            manifest.write_text(json.dumps({'z.txt':'gitblob-sha1:','a.txt':'gitblob-sha1:'}))
            with patch.object(verify,'ROOT',root):
                verify.refresh();expected_bytes=manifest.read_bytes()
                entries=json.loads(expected_bytes)
                self.assertEqual(list(entries),sorted(entries))
                manifest.write_text(json.dumps(dict(reversed(list(entries.items())))))
                verify.refresh()
                self.assertEqual(expected_bytes,manifest.read_bytes())

    def test_author_inventory_has_explicit_synthetic_sources(self):
        inv=json.loads((ROOT/'tools/r2r_authoring/source_inventory.json').read_bytes())
        self.assertEqual(len(inv['historical']),119);self.assertEqual(len(inv['additions']),6)
        authored=examples()
        for item in inv['additions']:
            row=authored[item['path']];source=(row.get('input') or row['review_input'])['original_instruction']
            self.assertEqual(item['source_sha256'],hashlib.sha256(source.encode()).hexdigest())

    def test_authoring_rejects_unregistered_source_changes(self):
        from tools.r2r_authoring.build import materialize
        data=examples();next(iter(data.values()))['input']['original_instruction']='Unregistered changed source.'
        with patch('tools.r2r_authoring.contrast.examples',return_value=data):
            with self.assertRaisesRegex(ValueError,'source drift'):materialize()

    def test_rules_keep_existing_hierarchy_size(self):
        nodes=json.loads((ROOT/'provenance/r2r_rule_links.json').read_bytes())['nodes']
        self.assertEqual(sum(n['level']==2 and n['role']=='generator' for n in nodes),12)
        self.assertEqual(sum(n['level']==2 and n['role']=='reviewer' for n in nodes),10)
        self.assertIn('submit the candidate',(ROOT/'generator/dataset_rules/r2r_en.md').read_text())

if __name__=='__main__':unittest.main()
