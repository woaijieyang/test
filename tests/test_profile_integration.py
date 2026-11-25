"""Exact dual-source migration and complete runtime teaching assertions."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
from host.compile import compile_prompt, core_library, teaching_card, runtime_review_output
from host.template_selector import library, select_examples
from tools.check_profile_integration import check_static, SOURCE, RXR_BASE

ROOT = Path(__file__).resolve().parents[1]

class ProfileIntegrationTests(unittest.TestCase):
    def test_requested_sources_and_full_teaching_are_preserved(self):
        report = check_static()
        self.assertEqual(report['source_commit'], SOURCE)
        self.assertEqual(report['retained_rxr_commit'], RXR_BASE)
        self.assertTrue(report['complete_dynamic_outputs_equal'])

    def test_all_rxr_positions_are_complete_in_every_phase(self):
        query = 'Walk through the doorway, turn right, pass two chairs and stop by the window.'
        for role, phase in [('generator','initial'),('generator','repair'),('reviewer','review'),('reviewer','recheck')]:
            ids = select_examples(role,'rxr-en-us',query,count=4)
            text, schema = compile_prompt(role,phase,profile='rxr-en-us',original_instruction=query,selected_ids=ids)
            cards = [json.loads(line) for line in text.splitlines() if line.startswith('{') and '"applicable_lesson"' in line]
            rows = {r['template_id']:r for r in core_library(role,'rxr-en-us')+library(role,'rxr-en-us')}
            self.assertEqual([c['template_id'] for c in cards],[r['template_id'] for r in core_library(role,'rxr-en-us')]+ids)
            for card in cards:
                row = rows[card['template_id']]
                self.assertEqual(card,teaching_card(row,role,True))
                self.assertNotIn('stage_summary',card['teaching'])
                self.assertNotIn('coverage_summary',card['teaching'])
                if role=='reviewer':
                    self.assertEqual(card['teaching']['layer_checks'],runtime_review_output(row)['layer_checks'])
                else:
                    self.assertEqual(card['teaching']['stage_evidence'],row['output']['stage_audit'])

    def test_all_mode_diagnostics_are_not_compressed(self):
        for role, phase in [('generator','initial'),('reviewer','review')]:
            rows=library(role,'rxr-en-us');ids=[r['template_id'] for r in rows]
            text,_=compile_prompt(role,phase,profile='rxr-en-us',selected_ids=ids,selection_mode='all')
            for row in rows:self.assertIn(json.dumps(teaching_card(row,role,True),ensure_ascii=False,sort_keys=True,separators=(',',':')),text)

    def test_cli_interfaces_and_packaged_role_settings(self):
        help_text=subprocess.check_output([sys.executable,'-B','-m','host.run','--help'],cwd=ROOT,text=True)
        for option in ('--record','--pins','--cli-ledger','--transport','--recover-command','--output'):
            self.assertIn(option,help_text)
        expected=subprocess.check_output(['git','show',SOURCE+':host/role-pins.json'],cwd=ROOT)
        self.assertEqual((ROOT/'host/role-pins.json').read_bytes(),expected)

    def test_repair_and_recheck_keep_frozen_role_selection(self):
        query='Stop at the counter, then return through the same blue door.'
        for profile in ('r2r-en','rxr-en-us'):
            for role, phases in [('generator',('initial','repair')),('reviewer',('review','recheck'))]:
                ids=select_examples(role,profile,query)
                prompts=[compile_prompt(role,p,profile=profile,original_instruction=query,selected_ids=ids)[0] for p in phases]
                marker='Selected dynamic example IDs in order: '+', '.join(ids)
                for text in prompts:self.assertIn(marker,text)
        # The independent R2R repair/recheck lessons imported from source still exist.
        for path in ('generator/dataset_rules/r2r_repair_examples.json','reviewer/dataset_rules/r2r_recheck_examples.json'):
            self.assertEqual((ROOT/path).read_bytes(),subprocess.check_output(['git','show',SOURCE+':'+path],cwd=ROOT))

if __name__=='__main__':unittest.main()
