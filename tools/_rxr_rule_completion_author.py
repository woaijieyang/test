"""One-time, reviewed rule-only authoring on the isolated work branch.

Removed before target publication. No runtime, schema, template, CLI or format edits.
The old role text is retained verbatim; new operations are inserted under existing headings.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = '48c61ee80330fe9ce12bd529fbec95a22f0b3c2c'

# role, parent heading, operational clarification, motivating observations.
ADDITIONS = [
('generator', 'Whole-instruction interpretation, grouping and expression',
 'Balanced decision check: choose grouping after interpreting the complete route, not as a way to avoid any edit. When a supported completed objective, distinct next objective, executable handoff and concrete local-focus benefit are present, retain that useful separation; when a coherent event needs no cut, retain it. Do not turn uncertainty about a proposed cut into default KEEP, blanket merging or a refusal of an otherwise usable route. Minimal editing limits unsupported change, not legitimate target binding, correction, temporal reassembly or necessary context.', ['6043/75568','10407/83394','8277/117379']),
('generator', 'Preconditions and completion-to-entry handoff',
 'Completion-strength check: compare the source event with both sides of the boundary before writing an entry anchor. Being near, at, in a threshold, or through it are not interchangeable states. A shared entity identifies what is meant, not how far movement has progressed. Retain a source-supported arrival or crossing when the full context requires it; otherwise adjust the cut or keep the original relation rather than strengthen it. A final completion description can remain valid without an invented connecting movement, metric distance or STOP; it cannot certify an unsupported intermediate prerequisite.', ['1881/91392','1365/52806','9298/47547']),
('generator', 'Source-faithful wording and final audit',
 'Edit-purpose check: for each route-bearing deletion or rewording, compare the event, actor or object, selected target, reference frame, time interval, quantity and completion strength before and after. Keep source-provided initial and later recognition cues that identify the place, target or required orientation; do not turn them into visits or pose-restoration commands. A genuinely redundant restatement may be coalesced when its meaning is still recoverable, but a unique recognition cue is not filler merely because it is not an action. Preserve descriptive alternatives when the route remains usable, and resolve a reference when the complete source uniquely supports it. There is no word-copy rate, edit quota or requirement to repeat every initial detail in every stage. Use the existing audit fields, not a new intermediate representation.', ['1914/46959','4932/69820','6445/25512']),
('generator', 'Oral repetition and actual return history',
 'Occurrence check: distinguish an event commanded again from a later description of its completion or entry depth. An anchor mentioning an already completed traversal carries context; it does not issue that traversal again. A later step or pass clause can refine the same event, but an independently ordered second movement or genuine return must remain. Use the intervening target and temporal evidence to decide, and retain the required travel even when the route ends at a previously named place. Do not compensate for hypothetical Actor memory errors by deleting a source-required event.', ['8277/117379']),
('generator', 'Conditional viewpoint description',
 'Action-authority check: a landmark being on the left or right does not by itself prescribe a turn of the body. Before making a viewing relation into an imperative, find an independently prescribed action or an unambiguous execution dependency in the complete source, not an assumed physical layout. Later wording that genuinely continues or requires a turn can supply that support. Otherwise preserve the relation as a recognition cue. Do not apply a blanket rule that removes all if/look clauses or all source-required turns; return to action coverage and reverse support for the specific occurrence.', ['10881/87653','8640/91332']),
('generator', 'Bounded movement and terminal refinement',
 'Extent and terminal-state check: bind each number to its action, counted category, starting event and endpoint. The second stair is an ordinal location, not automatically two new steps from the current pose; movement through an opening for a stated extent is not automatically a completed crossing followed by that extent again. Add no units, start point or additional movement absent from the source. At the final event, preserve location, relative placement, facing or looking requirement, recognition conditions and source-required stop scope together. Merely locating a landmark on one side does not replace looking towards it. Preserve a narrated final configuration without inventing a separate rotation, and keep a real intermediate stop distinct from a later bounded event.', ['6906/31539','9975/84498','7282/30051','7533/96039']),
('generator', 'Local lexical function',
 'Quoted-content check: distinguish a sign or label being described from the instruction author imposing a route prohibition. Retain quoted wording as an identifying cue without turning it into a new prohibition, detour or instruction to inspect it. Conversely, retain an actual do-not-enter command and its scope even when a sign is also mentioned. Quotation alone neither authorizes crossing nor cancels a real prohibition; determine the speaker and referent from the complete source, then check action coverage.', ['10250/98225','7533/96039']),
('generator', 'Target binding, spatial ownership and count origins',
 'Relation-scope check: classify the specific relation as an initial or local description, a predicted result, a required terminal configuration, or a maintained constraint. A narrated object on one side, even when repeated before and after movement, does not by itself authorize keep/stay for the whole interval. Preserve genuinely prescribed sustained relations; do not weaken them to a snapshot. When grammar leaves the subject or referent of behind/beside unclear, do not silently change an Agent-position reading into a furniture-layout fact. Use a uniquely supported binding when available; otherwise retain usable uncertainty and invoke the existing source-ambiguity path only when it actually prevents route interpretation. Recheck the affected Conditions and Handoff, not unrelated stages.', ['3054/48463','3256/46133','8680/46837','942/51571']),
('generator', 'Temporal dependencies and shared branch continuations',
 'Endpoint-limit check: determine whether before marks a required ordering between two commanded events or locates the endpoint on the near side of a later region. When it limits the destination, do not issue the later entry as a new command or put it into the predecessor completion. When the source independently commands that later entry, keep it in the supported order. Preserve the original trigger and relation without forcing every before phrase into a permanent ban or every described future region into another objective.', ['1365/52806','1881/91392']),
('reviewer', 'Ordered review framework: L0–L6',
 'Cross-layer evidence check: compare the source requirement and actual candidate at the same event occurrence, including its subject, action, target, reference, interval and completion strength. Use multiple local quotations when needed; a shared noun or direction token alone cannot establish preserved meaning. Test both loss of a required relation and addition of an unsupported one. This operationalizes L1/L2/L3/L6 without adding layers, output fields or a second acceptance standard.', ['3054/48463','3256/46133','6906/31539']),
('reviewer', 'Findings and decision',
 'Non-conservative acceptance check: propose a repair only for an identified change in executable meaning, a missing relevant recognition cue, or an evidenced grouping/handoff defect. Specify the source role and actual missing information rather than treating every omitted word as a defect. A faithful synonym, recoverable restatement or harmless supported anchor is not grounds to block. Neither copying the whole source nor choosing fewer stages automatically satisfies grouping; equally, more stages are not automatically better. Preserve a valid useful split and required clarification instead of demanding blanket merging or literal copying. Missing low-level motion details alone do not invalidate a source-prescribed final state. Diagnose the supplied text, not a hypothetical poor navigator response.', ['4932/69820','6445/25512','9298/47547','10407/83394']),
('reviewer', 'Existing recheck after a Generator repair',
 'Repair-delta check: compare each prior finding with the new frozen candidate and distinguish an actually restored requirement from a remaining defect. A supported rejection or partial acceptance of the old remedy must be judged on source evidence, not on whether a textual change occurred. Preserve independently correct repairs even if another defect remains; do not re-report an omission already restored, propagate an old incorrect-state description, or excuse a new error merely because the requested edit was made. Continue the full L0–L6 pass using the existing prior-finding dispositions.', ['942/51571','6445/25512','9975/84498','7282/30051']),
('reviewer', 'Conditional relations and retained dependencies',
 'Action-support check: distinguish a side-of-landmark description from an independently commanded body turn. Identify the exact extra action before alleging strengthening, and inspect later source text that may genuinely require or continue that turn. Do not remove a valid turn merely because its first mention is conditional. For before, distinguish temporal ordering from an endpoint limited before the next region; a repair must neither add the uncommanded entry nor erase an independently commanded one.', ['10881/87653','8640/91332','1365/52806']),
('reviewer', 'Spatial ambiguity',
 'Scope-and-subject check: identify whether a candidate changed a local or predicted relation into a maintained path constraint, or weakened a real sustained constraint into an observation. Repeated endpoint observations alone do not establish the whole interval. Show the actual source/candidate difference and preserve genuine keep/stay requirements. Resolve the subject and referent separately: a person standing behind an object and another object located behind it are different claims. Do not fix uncertain grammar by asserting a preferred layout. A retained descriptive alternative is acceptable when it does not prevent following the route; a uniquely supported reference can be clarified without being treated as speculation.', ['3054/48463','3256/46133','8680/46837','942/51571','6445/25512']),
('reviewer', 'Evidence, selection cues and count scope',
 'Quantity-and-cue check: identify the counted entity and start event before comparing an ordinal with a movement count. Check traversal-associated extent against post-traversal extent, and preserve approximation rather than sharpening it. A second stair does not automatically mean two additional steps. For a claimed omitted initial or later visual cue, locate its actual recognition or orientation role and whether its meaning survives elsewhere; neither deleting all descriptive detail nor demanding every repeated word is justified. Treat quoted sign text as a reference description unless the source itself imposes the prohibition, and do not let quotation erase a real do-not-enter instruction.', ['1914/46959','4932/69820','6445/25512','7533/96039','10250/98225']),
('reviewer', 'Entry, completion and stopping scope',
 'Strength-and-end-state check: verify near/at/in/through against the actual completion needed by the successor. Entry wording cannot silently upgrade an in-threshold state to completed passage, but full-context evidence can legitimately support a crossing or arrival. Check final position and required facing independently: a landmark located on the left does not by itself preserve looking towards it. Restore the missing relation, not an invented turn angle, extra approach or STOP. Keep a source-supported final state or allowed terminal approach valid without requiring unwritten low-level motions; do not use that final-only allowance to excuse a weak intermediate boundary. Recheck only genuinely dependent handoffs while preserving other valid boundaries.', ['1881/91392','6906/31539','9298/47547','10407/83394'])
]

INVARIANTS = [
 ('useful_grouping', 'generator', 'A coherent single stage is valid, and several complete objectives must not be buried merely because the route is continuous.', 'Preserve both valid KEEP and useful supported SPLIT; no default conservatism.', ['10407/83394','8277/117379']),
 ('source_stop', 'generator', 'An explicit source stop remains required even though the boundary itself adds no stop.', 'Restore a required stop, never create one solely from a boundary.', ['4932/69820','7533/96039']),
 ('local_correction', 'generator', 'A local correction does not invalidate all preceding clauses.', 'Apply the corrected meaning only within its supported scope.', ['6043/75568','942/51571']),
 ('minimal_supported_anchor', 'generator', 'A stage requires a supported entry state, not a mandatory new entry sentence.', 'Allow inheritance and genuinely necessary anchors; neither universal insertion nor deletion.', ['10407/83394','8277/117379']),
 ('no_navigation_oracle', 'reviewer', 'PASS means the candidate satisfies the language contract, not that navigation will succeed.', 'Judge the supplied text independently of trajectory outcomes.', ['9975/84498','7282/30051']),
 ('valid_alternative', 'reviewer', 'A different valid segmentation is not a defect.', 'Do not block a supported alternative merely to enforce a preferred partition.', ['10407/83394']),
 ('no_overrejection', 'reviewer', 'Absence of images is not source ambiguity.', 'Do not reject a usable source because the offline roles lack visual data.', ['9298/47547']),
 ('unchanged_repair', 'reviewer', 'textual change is not a prerequisite for resolving a false finding.', 'Correctly rejecting unsupported feedback may leave candidate English unchanged.', ['9298/47547']),
 ('restore_only_supported_stop', 'reviewer', 'explicitly allow restoration of source-required STOP, and reject unsupported additional stops or routes.', 'Do not confuse restoration with invention, or make every dimension fail.', ['4932/69820','7533/96039'])
]

def sha(data):
 return hashlib.sha256(data if isinstance(data,bytes) else data.encode()).hexdigest()

def old(path):
 return subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT).decode()

def sections(text):
 matches=list(re.finditer(r'^#{2,3} .+$',text,re.M));result={}
 for i,m in enumerate(matches):
  end=matches[i+1].start() if i+1<len(matches) else len(text)
  result[m.group()]=text[m.start():end]
 return result

def write_json(path,data):
 (ROOT/path).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def main():
 if os.environ.get('GITHUB_REF_NAME')!='rxr-rule-completion-work':
  raise RuntimeError('One-time authoring is restricted to the isolated work branch')
 roles={r:f'{r}/dataset_rules/rxr_en_us.md' for r in ('generator','reviewer')}
 baseline={r:old(p) for r,p in roles.items()}
 for r,p in roles.items():
  if (ROOT/p).read_text()!=baseline[r]:raise ValueError('Refuse to overwrite changed role source: '+p)
 current=dict(baseline);changes=[]
 for r,heading,paragraph,cases in ADDITIONS:
  text=current[r];start=text.index('### '+heading+'\n')
  m=re.search(r'^#{2,3} ',text[start+4:],re.M)
  end=start+4+m.start() if m else len(text)
  insertion=('' if text[:end].endswith('\n\n') else '\n')+paragraph+'\n\n'
  current[r]=text[:end]+insertion+text[end:]
  changes.append(dict(role=r,path=roles[r],heading=heading,inserted_text=insertion,
     status='locked_pending_validation',evidence_cases=cases,scope='Existing role-local P1/P2 operation; no new schema or runtime gate'))
 for r,p in roles.items():(ROOT/p).write_text(current[r],encoding='utf8')
 locks={r:dict(path=roles[r],baseline_sha256=sha(baseline[r]),sha256=sha(current[r]),
                  utf8_bytes=len(current[r].encode()),sections={h:sha(v) for h,v in sections(current[r]).items()}) for r in roles}
 frozen=[]
 for key,r,clause,scope,cases in INVARIANTS:
  if clause not in baseline[r] or clause not in current[r]:raise ValueError('Missing protected invariant '+key)
  frozen.append(dict(id=key,role=r,clause=clause,sha256=sha(clause),status='frozen_contract',scope=scope,
      evidence_cases=cases,evidence_level='Source-grounded semantic contract; historical observations are not a causal gain estimate',navigation_gain_proven=False))
 report=dict(baseline_commit=BASE,profile='rxr-en-us',content_status='locked',
  meaning='Content lock prevents unreviewed edits; it is not evidence of universal model effectiveness.',
  gain_frozen_rules=[],live_model_evaluated=False,navigation_evaluated=False,semantic_equivalence_certified=False,
  sources=[dict(filename='v6.6.3_5.6sol-high_ALL_EPISODES.md',sha256='42c3346fe89cdc05bd0e4bc6284f52f956ea88ada453860a708c05bb106a0229',evaluated_commit='081db4b9ea0712ff720c137fe96c240c26f7b15c'),
           dict(filename='RxR_逐项增强方案.md',sha256='429256075f262ae6f2dc73d7fba612372b56605769f6e77812e7f6c9b6605c04')],
  roles=locks,changes=changes,protected_invariants=frozen,
  unchanged=['P0','P1/P2 heading structure','L0-L6 framework','common contracts','runtime and CLI','all templates','selection','complete Dynamic input','output and rendering format','R2R'],
  reentry_policy='Change only for a reproducible source/candidate counterexample or controlled regression evidence; preserve a lawful counterexample and review the exact diff. Never reseal automatically to silence a failed test.')
 write_json('provenance/rxr_rule_lock.json',report)
 conversion=json.loads((ROOT/'provenance/rxr_role_conversion.json').read_text())
 for r,spec in conversion['roles'].items():
  spec.setdefault('before_rule_completion',dict(new_sha256=spec['new_sha256'],new_bytes=spec['new_bytes']))
  spec['new_sha256']=locks[r]['sha256'];spec['new_bytes']=locks[r]['utf8_bytes']
 write_json('provenance/rxr_role_conversion.json',conversion)
 from host.compile import compile_prompt
 from shared.identity import text_hash,canonical
 pins=json.loads((ROOT/'tests/fixtures/rxr_prompt_pins.json').read_text());measurements={}
 for role,phase in [('generator','initial'),('generator','repair'),('reviewer','review'),('reviewer','recheck')]:
  prompt,schema=compile_prompt(role,phase,profile='rxr-en-us',original_instruction=pins['query'],selected_ids=pins['selected_ids'][role])
  key=role+'/'+phase
  measurements[key]=dict(sha256=text_hash(prompt),schema_sha256=text_hash(canonical(schema)),utf8_bytes=len(prompt.encode()))
 write_json('provenance/rxr_rule_measurements.json',dict(measured_commit=os.environ.get('GITHUB_SHA'),
   workflow_run=os.environ.get('GITHUB_RUN_ID'),measurements=measurements,prompt_fixture_updated=False,
   rule_additions=len(changes),frozen_contracts=len(frozen),navigation_evaluated=False))
 print(json.dumps({'role_files':locks,'additions':len(changes),'protected_contracts':len(frozen),'measurements':measurements},indent=2))

if __name__=='__main__':main()
