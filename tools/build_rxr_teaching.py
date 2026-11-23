"""Build authored training demonstrations; verify public source bytes on demand.

Offline maintenance only. Runtime reads committed JSON and performs no download.
Validate every case before publishing a guarded, explicit complete bundle.
Mechanical contracts do not certify semantic entailment or navigation.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.rxr_lesson_specs import LESSONS, ARCHIVE_URL, ARCHIVE_SHA256
from tools.rxr_training_review import STOP_SCOPES, build_diagnostic
from tools.rxr_training_io import encode, publish


def validate_lesson_inventory(lessons):
    if not isinstance(lessons, list) or len(lessons) != 8:
        raise ValueError('The approved source inventory requires eight lessons')
    names, instructions, sources = set(), set(), set()
    for case in lessons:
        name, iid, source = case.get('id'), case.get('instruction_id'), case.get('source')
        if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
            raise ValueError('Invalid authored lesson identity')
        if isinstance(iid, bool) or not isinstance(iid, int) or iid < 0:
            raise ValueError('Invalid authored instruction identity')
        if not isinstance(source, str) or not source:
            raise ValueError('Empty authored source instruction')
        digest = hashlib.sha256(source.encode('utf-8')).hexdigest()
        if name in names or iid in instructions or digest in sources:
            raise ValueError('Duplicate authored lesson, instruction or source')
        if not isinstance(case.get('record_sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', case['record_sha256']):
            raise ValueError('Invalid authored source-record digest')
        names.add(name); instructions.add(iid); sources.add(digest)


def verify_upstream():
    validate_lesson_inventory(LESSONS)
    with urllib.request.urlopen(ARCHIVE_URL, timeout=90) as response:
        blob = response.read()
    if hashlib.sha256(blob).hexdigest() != ARCHIVE_SHA256:
        raise ValueError('Official training archive digest changed; stop and review the new source')
    wanted = {case['instruction_id']: case for case in LESSONS}
    found = set()
    for line in gzip.decompress(blob).splitlines(keepends=True):
        row = json.loads(line)
        key = row.get('instruction_id')
        if key not in wanted:
            continue
        case = wanted[key]
        if key in found:
            raise ValueError(f'Duplicate training instruction {key}')
        if hashlib.sha256(line).hexdigest() != case['record_sha256']:
            raise ValueError(f'Training source record digest mismatch: {key}')
        if (row['instruction'] != case['source'] or row['scan'] != case['scan']
                or row['path_id'] != case['path_id'] or row['language'] != 'en-US'):
            raise ValueError(f'Training source identity mismatch: {key}')
        found.add(key)
    if found != set(wanted):
        raise ValueError(f'Missing verified source records: {sorted(set(wanted) - found)}')


def field(text, quotes):
    return {'text': text, 'candidate_quotes': quotes}


def make_case(case):
    from host.template_selector import _template_validators
    versions = {role: _template_validators()[role].schema['properties']['schema_version']['const']
                for role in ('generator', 'reviewer')}
    name = case['id']
    gen_id, rev_id = (f'RxR-{role}-TRAIN-{name}' for role in ('GEN', 'REV'))
    stages = [stage[0] for stage in case['stages']]
    scopes = STOP_SCOPES[name]
    if len(scopes) != len(stages) or any(x not in ('none','intermediate','terminal') for x in scopes):
        raise ValueError(f'{name}: every stage requires an explicit authored stop scope')
    coverage = [dict(requirement_id=f'SRC-{i + 1:02d}', source_quote=src,
                     requirement=requirement,
                     candidate_evidence=[dict(subtask_index=index, quote=quote)], status='covered')
                for i, (src, index, quote, requirement) in enumerate(case['coverage'])]
    audits = []
    for i, (text, target, ending, kind, conditions, entry) in enumerate(case['stages']):
        audits.append(dict(
            subtask_index=i,
            entry=dict(mode='episode_start' if i == 0 else 'inherited_pose', text=entry, candidate_quotes=[]),
            target=field(target, [target]),
            process=field('Execute the ordered actions stated in this stage.', [text]),
            ending=dict(kind=kind, text='Complete the source-supported event: ' + ending,
                        candidate_quotes=[ending], stop_scope=scopes[i]),
            conditions=field('; '.join(conditions) if conditions else None, conditions),
            source_quotes=[row['source_quote'] for row in coverage if row['candidate_evidence'][0]['subtask_index'] == i],
            carryover=[]))
    handoffs = []
    for i in range(len(stages) - 1):
        ending = case['stages'][i][2]
        entry = case['stages'][i + 1][5]
        next_quote = case['coverage'][next(j for j, row in enumerate(case['coverage']) if row[1] == i + 1)][2]
        handoffs.append(dict(
            from_subtask_index=i, to_subtask_index=i + 1, status='supported',
            preceding_exit=dict(text=audits[i]['ending']['text'], candidate_quote=ending),
            next_entry=dict(text=entry, candidate_quote=next_quote),
            shared_context=[dict(kind='inherited_context', text=entry)],
            source_requirement_ids=[row['requirement_id'] for row in coverage if row['candidate_evidence'][0]['subtask_index'] in (i, i + 1)],
            handoff_rationale='The cited preceding completion supplies the next first unperformed action. The boundary adds no physical stop or traversal and does not cancel any stop explicitly required by the source.'))
    source = dict(split='train', role='guide', record_id=str(case['instruction_id']),
                  instruction_id=str(case['instruction_id']), scene_id=case['scan'], trajectory_id=str(case['path_id']))
    provenance = dict(kind='curated_train_guide_lesson', source_url=ARCHIVE_URL,
                      archive_sha256=ARCHIVE_SHA256, source_record_sha256=case['record_sha256'],
                      source_status='curated_teaching_target_not_official_subtask_annotation',
                      navigation_evaluated=False)
    notes = dict(segmentation_pattern=case['pattern'], why_this_case_matters=case['lesson'],
                 reusable_rule=case['lesson'], anti_pattern=case['anti'],
                 retrieval_rule='Retrieve only when the current source exhibits the same relation; the example never determines a stage count.')
    generator = dict(schema_version=versions['generator'], template_id=gen_id, role='generator',
                     dataset_scope='RxR', language='en-US', source=source, provenance=provenance,
                     input=dict(original_instruction=case['source']),
                     decision=dict(status='ok', mode='split' if len(stages) > 1 else 'keep', rationale=case['lesson']),
                     output=dict(status='ok', subtasks=stages, stage_audit=audits, handoffs=handoffs, issues=[]),
                     teaching_notes=notes, retrieval_tags=[case['pattern']])
    from host.protocol import LAYERS
    conclusions = [
        'This authored case supplies no Renderer artifact; review the actual stage strings.',
        'The indexed source passages identify their actual candidate events, not merely repeated words.',
        case['lesson'],
        'The authored five-element definitions preserve the actual entry, target, process, completion and scoped conditions.',
        'The cited preceding outcome supports the next first unperformed action; an inherited pose is not an extra command.',
        'The grouping respects source-supported completed objectives and coupled maneuvers.',
        'Source coverage and reverse source support retain the route. This is a teaching judgment, not a navigation success claim.']
    checks = []
    for i, audit in enumerate(audits):
        check = copy.deepcopy(audit)
        check['status'] = 'supported'
        check['source_requirement_ids'] = [row['requirement_id'] for row in coverage if row['candidate_evidence'][0]['subtask_index'] == i]
        checks.append(check)
    review = dict(verdict='pass', dimensions={d:'pass' for d in ('source_fidelity','closure_handoff','segmentation_adequacy')},
                  source_coverage=coverage,
                  layer_checks=[dict(layer=layer, status='not_applicable' if j == 0 or (j == 4 and len(stages) == 1) else 'pass', finding_indices=[], conclusion=conclusions[j]) for j, layer in enumerate(LAYERS)],
                  findings=[], stage_checks=checks, handoffs=copy.deepcopy(handoffs), prior_finding_reviews=[])
    reviewer = dict(schema_version=versions['reviewer'], template_id=rev_id, role='reviewer', dataset_scope='RxR',
                    language='en-US', pair_id=gen_id, source=copy.deepcopy(source), provenance=copy.deepcopy(provenance),
                    review_input=dict(original_instruction=case['source'], candidate=dict(status='ok', subtasks=copy.deepcopy(stages))),
                    expected_review=review, teaching_notes=dict(review_pattern=case['pattern'],
                        review_principle=case['lesson'], case_specific_focus=case['lesson'], anti_pattern=case['anti']),
                    retrieval_tags=[case['pattern']])
    diagnostic = build_diagnostic(case, reviewer)
    return generator, reviewer, diagnostic


def expected_bundle():
    validate_lesson_inventory(LESSONS)
    from host.template_selector import validate_template
    from host.compile import runtime_review_output
    from host import protocol
    inventory, outputs = [], {}
    for case in LESSONS:
        gen, rev, diag = make_case(case)
        validate_template('generator', gen)
        protocol.generator(case['source'], gen['output'])
        for row in (rev, diag):
            validate_template('reviewer', row)
            protocol.reviewer(case['source'], row['review_input']['candidate'], runtime_review_output(row))
        if gen['output']['subtasks'] != rev['review_input']['candidate']['subtasks']:
            raise ValueError('Authored pair does not review its actual Generator candidate')
        for role, row in (('generator',gen),('reviewer',rev),('reviewer',diag)):
            path = f"{role}/templates/RxR/train/{row['template_id']}.json"
            if path in outputs:
                raise ValueError('Duplicate authored training output: ' + path)
            outputs[path] = encode(row)
        inventory.append(dict(instruction_id=case['instruction_id'],scan=case['scan'],path_id=case['path_id'],
                              source_sha256=hashlib.sha256(case['source'].encode()).hexdigest(),
                              source_record_sha256=case['record_sha256'],
                              generator=gen['template_id'],reviewer=rev['template_id'],diagnostic=diag['template_id'],pattern=case['pattern']))
    registry = dict(source_url=ARCHIVE_URL, archive_sha256=ARCHIVE_SHA256,
        source_split='train',source_role='guide',language='en-US',annotation_status='curated_not_official_subtask_ground_truth',
        records=inventory, templates=[dict(path=name, sha256=hashlib.sha256(outputs[name]).hexdigest()) for name in sorted(outputs)])
    return outputs, registry


def build(verify=False, *, check=False):
    validate_lesson_inventory(LESSONS)
    if verify:
        verify_upstream()
    # A late invalid lesson cannot leave earlier generated files behind.
    outputs, registry = expected_bundle()
    changed = publish(ROOT, outputs, registry, check=check)
    print(json.dumps(dict(training_sources=len(registry['records']),generated_templates=len(outputs),
                          changed_files=len(changed),check_only=check,
                          upstream_bytes_verified=verify,semantic_correctness_certified=False,navigation_evaluated=False)))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--verify-upstream',action='store_true')
    parser.add_argument('--check',action='store_true',help='Validate authored bytes without writing any artifacts')
    args=parser.parse_args()
    build(args.verify_upstream, check=args.check)
