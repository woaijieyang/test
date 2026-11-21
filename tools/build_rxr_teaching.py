"""Build authored training demonstrations; verify public source bytes on demand.

Offline maintenance only. Runtime reads committed JSON and performs no download.
The builder checks mechanical contracts, not semantic entailment or navigation.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.rxr_lesson_specs import LESSONS, ARCHIVE_URL, ARCHIVE_SHA256


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def verify_upstream():
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
        assert hashlib.sha256(line).hexdigest() == case['record_sha256'], key
        assert row['instruction'] == case['source'], key
        assert row['scan'] == case['scan'] and row['path_id'] == case['path_id'], key
        assert row['language'] == 'en-US', key
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
    gen_id, rev_id, diag_id = (f'RxR-{role}-TRAIN-{name}' for role in ('GEN', 'REV', 'DIAG'))
    stages = [stage[0] for stage in case['stages']]
    coverage = [dict(requirement_id=f'SRC-{i + 1:02d}', source_quote=src,
                     requirement=requirement,
                     candidate_evidence=[dict(subtask_index=index, quote=quote)], status='covered')
                for i, (src, index, quote, requirement) in enumerate(case['coverage'])]
    audits = []
    for i, (text, target, ending, kind, conditions, entry) in enumerate(case['stages']):
        # These descriptions and evidence are explicitly authored in the specs.
        # No hidden plan or trajectory is inferred here.
        audits.append(dict(
            subtask_index=i,
            entry=dict(mode='episode_start' if i == 0 else 'inherited_pose', text=entry, candidate_quotes=[]),
            target=field(target, [target]),
            process=field('Execute the ordered actions stated in this stage.', [text]),
            ending=dict(kind=kind, text='Complete the source-supported event: ' + ending,
                        candidate_quotes=[ending], stop_scope='none'),
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
            handoff_rationale='The preceding completion supplies the next first unperformed action; no physical stop or extra traversal is inferred.'))
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
        'Map every listed route requirement to indexed candidate text.',
        case['lesson'],
        'Audit the actual stage entry, target, ordered process, ending and conditions independently.',
        'Compare every previous completion with the next first unperformed action; inheritance is supported.',
        'The grouping respects source-supported completed objectives and coupled maneuvers.',
        'Coverage and reverse source support preserve the route; this is not a navigation success claim.']
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
    diagnostic = copy.deepcopy(reviewer)
    diagnostic['template_id'], diagnostic['pair_id'] = diag_id, None
    diagnostic['provenance']['kind'] = 'authored_single_defect_training_diagnostic'
    diagnostic['provenance']['candidate_corruption_is_authored_not_model_output'] = True
    mutation = case['mutation']
    index, old, new = mutation['stage'], mutation['old'], mutation['new']
    if stages[index].count(old) != 1:
        raise ValueError(f'{name}: mutation must match exactly one stage span')
    bad = stages[index].replace(old, new, 1)
    diagnostic['review_input']['candidate']['subtasks'][index] = bad
    audit = diagnostic['expected_review']
    audit['verdict'] = 'revise'
    audit['dimensions']['source_fidelity'] = 'issue'
    changed_id = audit['source_coverage'][mutation['requirement']]['requirement_id']

    def quote_after(quote):
        if quote in bad:
            return quote
        result = quote.replace(old, new)
        return result if result in bad else new

    for row in audit['source_coverage']:
        for evidence in row['candidate_evidence']:
            if evidence['subtask_index'] == index:
                evidence['quote'] = quote_after(evidence['quote'])
    changed_row = audit['source_coverage'][mutation['requirement']]
    changed_row['status'] = 'altered_or_missing'
    changed_row['candidate_evidence'] = [dict(subtask_index=index, quote=new)]
    check = audit['stage_checks'][index]
    check['status'] = 'gap'
    for key in ('entry','target','process','ending','conditions'):
        check[key]['candidate_quotes'] = [quote_after(q) for q in check[key]['candidate_quotes']]
    check['process']['text'] = 'The candidate contains the material change identified by the finding; other ordered actions remain.'
    for handoff in audit['handoffs']:
        for key, endpoint in (('preceding_exit','from_subtask_index'),('next_entry','to_subtask_index')):
            if handoff[endpoint] == index:
                handoff[key]['candidate_quote'] = quote_after(handoff[key]['candidate_quote'])
    cchecks = {'UNSUPPORTED_ADDITION':'C02','WRONG_REFERENCE_FRAME':'C03','WRONG_RELATION':'C06','COUNT_SCOPE_DRIFT':'C07','WRONG_TARGET':'C05'}
    finding = dict(code=mutation['code'], failed_layer='L2_dependencies', c_check=cchecks[mutation['code']],
                   dimension='source_fidelity', related_dimensions=[], affected_subtask_indices=[index],
                   source_requirement_ids=[changed_id], source_quote=case['coverage'][mutation['requirement']][0],
                   candidate_evidence=[dict(subtask_index=index,quote=new)], evidence_level='S1',
                   problem=mutation['problem'], execution_consequence=mutation['consequence'],
                   repair=dict(operation='restore_source_semantics', affected_subtask_indices=[index],
                               instruction=f'Restore {old!r} in place of {new!r}; preserve the unaffected route.',
                               protected_requirements=['Preserve all unaffected actions, relationships, quantities and source order.',case['lesson']]))
    audit['findings'] = [finding]
    for layer in audit['layer_checks']:
        if layer['layer'] in ('L1_source_coverage','L2_dependencies','L3_stage_checks','L6_route_readback'):
            layer.update(status='issue', finding_indices=[0], conclusion=mutation['problem'])
    diagnostic['teaching_notes'] = dict(review_pattern=case['pattern'], review_principle=mutation['problem'],
                                        case_specific_focus=mutation['consequence'], anti_pattern='Do not reject a legal paraphrase or alternative segmentation; this candidate changes a specific source relation.')
    return generator, reviewer, diagnostic


def build(verify=False):
    if verify:
        verify_upstream()
    from host.template_selector import validate_template
    from host.compile import runtime_review_output
    from host import protocol
    inventory = []
    for case in LESSONS:
        gen, rev, diag = make_case(case)
        validate_template('generator', gen)
        protocol.generator(case['source'], gen['output'])
        for row in (rev, diag):
            validate_template('reviewer', row)
            protocol.reviewer(case['source'], row['review_input']['candidate'], runtime_review_output(row))
        for role, row in (('generator',gen),('reviewer',rev),('reviewer',diag)):
            write(ROOT/role/'templates'/'RxR'/'train'/f"{row['template_id']}.json", row)
        inventory.append(dict(instruction_id=case['instruction_id'],scan=case['scan'],path_id=case['path_id'],
                              source_sha256=hashlib.sha256(case['source'].encode()).hexdigest(),
                              source_record_sha256=case['record_sha256'],
                              generator=gen['template_id'],reviewer=rev['template_id'],diagnostic=diag['template_id'],pattern=case['pattern']))
    write(ROOT/'provenance/rxr_training_sources.json', dict(source_url=ARCHIVE_URL, archive_sha256=ARCHIVE_SHA256,
        source_split='train',source_role='guide',language='en-US',annotation_status='curated_not_official_subtask_ground_truth',
        records=inventory))
    print(json.dumps(dict(training_sources=len(inventory),generated_templates=3*len(inventory),
                          upstream_bytes_verified=verify,semantic_correctness_certified=False,navigation_evaluated=False)))

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--verify-upstream',action='store_true')
    build(parser.parse_args().verify_upstream)
