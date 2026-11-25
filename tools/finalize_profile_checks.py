"""One-time reviewed expectation and baseline migration; removed after application."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def edit(path,fn):
 p=ROOT/path;old=p.read_bytes().decode();new=fn(old)
 if new==old:raise ValueError('Patch did not apply: '+path)
 p.write_bytes(new.encode())
def main():
 def test_patch(s):
  s=s.replace('complete/summarized teaching','complete teaching').replace('test_first_two_dynamic_cases_are_detailed_in_every_phase','test_all_dynamic_cases_are_detailed_in_every_phase')
  s=s.replace('else \'stage_checks\' in teaching), position < 2)','else \'stage_checks\' in teaching), True)')
  s=s.replace("                if position >= 2:\n                    self.assertIn('stage_summary', teaching)","                self.assertNotIn('stage_summary', teaching)")
  s=s.replace('test_generator_summaries_keep_all_five_meanings_and_exact_evidence','test_generator_complete_cards_keep_all_five_meanings_and_exact_evidence')
  s=s.replace('test_reviewer_summaries_keep_findings_coverage_and_handoffs','test_reviewer_complete_cards_keep_findings_coverage_and_handoffs')
  s=s.replace("summary['stage_summary']","summary['stage_evidence']").replace("card['coverage_summary']","card['coverage_evidence']").replace("card['stage_summary']","card['stage_checks']").replace("card['teaching']['stage_summary']","card['teaching']['stage_evidence']")
  return s
 edit('tests/test_rxr_refinement.py',test_patch)
 def protect(s):
  s=s.replace("BASE = '803ebf2c9edb5e60bb240dd1a2c411663c1a185e'","BASE = 'b69e04ddc7097b47f8d201beed2fa5e2d9ffd34e'\nSOURCE_BASE = '33d66756de8d545db001f3854194bf5d5b5a8592'")
  s=s.replace("git('diff', '--name-only', BASE, '--', *PROTECTED)","git('diff', '--name-only', SOURCE_BASE, '--', *PROTECTED)")
  s=s.replace('Protected common/R2R behavior source changed: ','Imported common/R2R source differs from requested migration source: ')
  s=s.replace('return dict(baseline_commit=BASE, protected_assets_equal=True,','return dict(baseline_commit=BASE, source_baseline_commit=SOURCE_BASE, protected_assets_equal=True,')
  s=s.replace("        if current != old:\n            changed_templates.append(current['template_id'])","        if current != old:\n            raise ValueError('Retained RxR teaching bytes changed: ' + path)")
  return s
 edit('tools/check_rxr_refinement.py',protect)
 p=ROOT/'provenance/rxr_role_conversion.json';data=json.loads(p.read_bytes())
 for spec in data['roles'].values():
  b=(ROOT/spec['path']).read_bytes();spec['new_bytes']=len(b);spec['new_sha256']=hashlib.sha256(b).hexdigest()
 data['current_delivery_policy']='Every selected Dynamic is complete; dual-baseline migration is recorded separately in profile_migration_inventory.json.'
 p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 print('Applied explicit full-teaching assertions and declared dual baseline')
if __name__=='__main__':main()
