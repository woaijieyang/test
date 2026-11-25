"""Migrate approved R2R test expectations, never weaken runtime contracts.

No test is removed. RxR golden prompt/schema pins are not regenerated; the
shared source-byte check admits only the explicit reviewed integration delta.
"""
from pathlib import Path
import argparse,json,re,subprocess
from r2r_authoring.runtime_layout import extend_tests
from r2r_authoring.projection_expectations import apply as projection
ROOT=Path(__file__).resolve().parents[1]
PARENT='081db4b9ea0712ff720c137fe96c240c26f7b15c'
FILES=('test_r2r_core.py','test_r2r_specialization.py','test_paired_selection.py','test_closed_loop_35.py','test_roles_repair.py','test_workflow_integration.py','test_host_dispatch_profiles.py','test_rxr_profile.py','test_entry_diagnostics.py','test_example_injection.py','test_rxr_prompt_snapshots.py')
REPLACEMENTS=(
 ('("reviewer", 52)','("reviewer", 55)'),("('r2r-en',(25,52))","('r2r-en',(25,55))"),
 ('sum(not x.get("pair_id") for x in rows), 23','sum(not x.get("pair_id") for x in rows), 26'),
 ("sum(not r.get('pair_id') for r in library('reviewer',profile)),23","sum(not r.get('pair_id') for r in library('reviewer',profile)),26"),
 ('6 <= len(generator_ids) <= 8','4 <= len(generator_ids) <= 6'),
 ('2 <= len(diagnostics) <= 4','2 <= len(diagnostics) <= 3'),
 ('6 <= len(g) <= 8 and 2 <= len(extras) <= 4','4 <= len(g) <= 6 and 2 <= len(extras) <= 3'),
 ('6 <= len(g) <= 8','4 <= len(g) <= 6'),('8 <= len(r) <= 12','6 <= len(r) <= 9'),
 ('6 <= len(a) <= 8','4 <= len(a) <= 6'),('8 <= len(a) <= 12','6 <= len(a) <= 9'),
 ('6 <= len(ids) <= 8','4 <= len(ids) <= 6'),('8 <= len(ids) <= 12','6 <= len(ids) <= 9'),
 ('6 <= len(select_examples("generator", "r2r-en", "Walk through the doorway.")) <= 8','4 <= len(select_examples("generator", "r2r-en", "Walk through the doorway.")) <= 6'),
 ('8 <= len(select_examples("reviewer", "r2r-en", "Walk through the doorway.")) <= 12','6 <= len(select_examples("reviewer", "r2r-en", "Walk through the doorway.")) <= 9'),
 ('for invalid in (1, 5, 9, 25):','for invalid in (True, 1, 3, 7, 8, 25, 4.0):'),
 ('source, count=8)), 8','source, count=4)), 4'),
 ('verdicts.count("pass"), 4','verdicts.count("pass"), 5'),('verdicts.count("revise"), 5','verdicts.count("revise"), 4'),
 ('self.assertIn("## Required decision sequence", generator)','self.assertIn("## G-P0", generator)'),
 ('self.assertIn("## Independent review sequence", reviewer)','self.assertIn("## R-P0", reviewer)'),
 ('self.assertIn("R2R-specific", (ROOT / "shared/dataset_rules/r2r_en.md")','self.assertIn("S-ROLE", (ROOT / "shared/dataset_rules/r2r_en.md")'),
 ("patch('host.run.select_examples',side_effect=ValueError('offline selection failure'))","patch('r2r.selection.select_bundle',side_effect=ValueError('offline selection failure'))"),
)

def main():
    p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');args=p.parse_args();report=[]
    for name in FILES:
        rel='tests/'+name;old=subprocess.check_output(['git','show',PARENT+':'+rel],cwd=ROOT).decode();new=old;changes=[]
        for a,b in REPLACEMENTS:
            if a in new:new=new.replace(a,b);changes.append(a)
        if name=='test_host_dispatch_profiles.py':
            body='''    def test_r2r_selector_matches_declared_selection_contract(self):
        from r2r.selection import select_bundle
        from host.template_selector import library, select_examples
        bundle = select_bundle(SOURCE)
        generator_ids = select_examples("generator", "r2r-en", SOURCE)
        reviewer_ids = select_examples("reviewer", "r2r-en", SOURCE)
        self.assertEqual(generator_ids, bundle["generator"])
        self.assertEqual(reviewer_ids, bundle["reviewer"])
        self.assertTrue(4 <= len(generator_ids) <= 6)
        self.assertTrue(2 <= len(reviewer_ids) - len(generator_ids) <= 3)
        bank = {r["template_id"]: r for r in library("reviewer", "r2r-en")}
        self.assertEqual([bank[i]["pair_id"] for i in reviewer_ids[:len(generator_ids)]], generator_ids)
        self.assertEqual([r["template_id"] for r in bundle["evidence"]["generator"]["selected"]], generator_ids)
'''
            new,n=re.subn(r'    def test_r2r_selector_matches_declared_selection_contract\(self\):[\s\S]*?(?=\n    def |\nif __name__|\Z)',lambda _:body,new)
            if n!=1:raise ValueError('Missing explicit legacy selection-contract test')
            changes.append('Assert actual count, pair mapping and captured trace instead of replaying the retired ranking formula.')
        revised=projection(name,new)
        if revised!=new:changes.append('Validate the exact new teaching representation and evidence; keep RxR expected prompt/schema hashes unchanged.')
        previous=revised
        new=extend_tests(name,revised)
        if new==old:continue
        path=ROOT/rel;actual=path.read_text()
        # read_text normalizes CRLF; compare normalized text only for this
        # one-time authoring guard, never for prompt or released Source hashes.
        if actual not in (previous.replace('\r\n','\n'),old.replace('\r\n','\n'),new.replace('\r\n','\n')):raise ValueError('Concurrent test edit: '+rel)
        if args.write:path.write_text(new)
        elif actual!=new.replace('\r\n','\n'):raise ValueError('R2R test expectations not materialized: '+rel)
        report.append(dict(path=rel,approved_expectation_changes=changes))
    print('TEST_EXPECTATION_CHANGES '+json.dumps(report))
if __name__=='__main__':main()
