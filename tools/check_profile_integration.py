"""Read-only dual-baseline checks for the integrated profiles.

R2R/common is pinned to the requested source; RxR teaching is pinned to the
retained target. Complete teaching and independent process comparisons are
engineering checks, not model-accuracy or navigation certificates.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE = '33d66756de8d545db001f3854194bf5d5b5a8592'
RXR_BASE = 'b69e04ddc7097b47f8d201beed2fa5e2d9ffd34e'
SOURCE_PREFIXES = ('host/r2r/', 'tools/r2r_authoring/', 'generator/templates/R2R/',
                   'reviewer/templates/R2R/', 'shared/dataset_rules/r2r',
                   'generator/dataset_rules/r2r', 'reviewer/dataset_rules/r2r')
COMMON = ('host/cli_journal.py', 'host/role-pins.json', 'requirements.txt',
          'host/protocol.py', 'host/template_selector.py', 'adapter/source.py',
          'adapter/profiles.json', 'renderer/freeze.py', 'shared/semantic_contract.md',
          'generator/prompt.md', 'reviewer/prompt.md', 'reviewer/checklist.md',
          'generator/output.schema.json', 'generator/repair.schema.json',
          'reviewer/output.schema.json', 'generator/templates_manifest.json',
          'reviewer/templates_manifest.json', 'tools/verify_package.py')
RXR_PREFIXES = ('generator/templates/RxR/', 'reviewer/templates/RxR/')
RXR_EXACT = ('shared/dataset_rules/rxr_en_us.md', 'host/rxr_contract.py',
             'host/rxr_retrieval.py', 'host/rxr_assets.py',
             'provenance/rxr_training_sources.json', 'tools/build_rxr_reviewed.py',
             'tools/rxr_teaching_alignment.py', 'tools/rxr_teaching_focus.py',
             'tools/rxr_positive_repairs.py', 'tools/rxr_diagnostic_repairs.py')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def tree(ref):
    rows = {}
    for line in git('ls-tree', '-rz', ref).split(b'\0'):
        if line:
            meta, path = line.split(b'\t', 1)
            rows[path.decode()] = meta.decode().split()[2]
    return rows


def assert_assets(ref, prefixes, exact):
    baseline = tree(ref)
    paths = {p for p in baseline if p.startswith(prefixes) or p in exact}
    missing = set(exact) - set(baseline)
    if missing:
        raise ValueError('Pinned source missing declared assets: ' + repr(sorted(missing)))
    for name in paths:
        path = ROOT / name
        if not path.is_file() or blob(path.read_bytes()) != baseline[name]:
            raise ValueError('Pinned asset changed: ' + name)
    for prefix in prefixes:
        path = ROOT / prefix
        if prefix.endswith('/') and path.is_dir():
            present = {p.relative_to(ROOT).as_posix() for p in path.rglob('*')
                       if p.is_file() and '__pycache__' not in p.parts}
            if present != {p for p in paths if p.startswith(prefix)}:
                raise ValueError('Unreviewed inventory change: ' + prefix)
    return len(paths)


def check_static():
    inventory = json.loads((ROOT / 'provenance/profile_migration_inventory.json').read_bytes())
    if (inventory['source_commit'], inventory['target_commit']) != (SOURCE, RXR_BASE):
        raise ValueError('Dual baseline mismatch')
    r2r = assert_assets(SOURCE, SOURCE_PREFIXES, COMMON)
    rxr = assert_assets(RXR_BASE, RXR_PREFIXES, RXR_EXACT)
    from host.compile import core_library, runtime_review_output, teaching_card
    from host.template_selector import library
    from host.rxr_teaching import dynamic_is_detailed
    counts = {}
    for profile in ('r2r-en', 'rxr-en-us'):
        for role in ('generator', 'reviewer'):
            rows = core_library(role, profile) + library(role, profile)
            counts[profile + '/' + role] = len(rows)
            for row in rows:
                before = copy.deepcopy(row)
                card = teaching_card(row, role, True)
                if profile == 'r2r-en':
                    actual = card['expected_output']
                    expected = row['output'] if role == 'generator' else row['expected_review']
                elif role == 'generator':
                    shown = card['teaching']
                    actual = dict(status=shown['status'], subtasks=shown['stages'],
                                  stage_audit=shown['stage_evidence'],
                                  handoffs=shown['handoffs'], issues=shown['issues'])
                    expected = row['output']
                    if shown['source'] != row['input']['original_instruction']:
                        raise ValueError('RxR source projection changed')
                else:
                    shown = card['teaching']
                    actual = {k: shown[k] for k in ('verdict', 'dimensions', 'layer_checks',
                              'findings', 'stage_checks', 'handoffs', 'prior_finding_reviews')}
                    actual['source_coverage'] = shown['coverage_evidence']
                    expected = runtime_review_output(row)
                    if shown['review_case'] != row['review_input']:
                        raise ValueError('RxR review input changed')
                if actual != expected or before != row:
                    raise ValueError('Incomplete/mutating teaching: ' + row['template_id'])
                if profile == 'rxr-en-us':
                    if teaching_card(row, role, False) != card:
                        raise ValueError('Legacy flag re-enabled compressed teaching')
                    if not dynamic_is_detailed(role, 99):
                        raise ValueError('Later Dynamic unexpectedly compressed')
    for name in ('WORKFLOW.md', 'IMPLEMENTATION.md', 'CHANGELOG.md', 'CODEX_START_HERE.md',
                 'verify_package.py', 'validation.json', 'r2r', 'r2r_authoring'):
        if (ROOT / name).exists():
            raise ValueError('Obsolete root layout retained: ' + name)
    return dict(source_commit=SOURCE, retained_rxr_commit=RXR_BASE,
                source_assets_exact=r2r, retained_rxr_assets_exact=rxr,
                complete_teaching_counts=counts, cli_and_schema_source_exact=True,
                complete_dynamic_outputs_equal=True, navigation_evaluated=False)


SNAPSHOT = r'''
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from host.compile import compile_prompt
from host.template_selector import select_examples
from shared.identity import canonical,text_hash
requests=json.load(sys.stdin);result={}
for profile,sources in requests.items():
    output=[]
    for source in sources:
        selections={r:select_examples(r,profile,source) for r in ('generator','reviewer')}
        phases={}
        for role,phase in [('generator','initial'),('reviewer','review'),('generator','repair'),('reviewer','recheck')]:
            prompt,schema=compile_prompt(role,phase,profile=profile,original_instruction=source,selected_ids=selections[role])
            phases[role+'/'+phase]={'prompt':text_hash(prompt),'schema':text_hash(canonical(schema))}
        output.append({'source':text_hash(source),'ids':selections,'phases':phases})
    result[profile]=output
print(json.dumps(result,sort_keys=True))
'''


def snapshot(path, queries):
    return json.loads(subprocess.check_output([sys.executable, '-B', '-c', SNAPSHOT, str(path)],
                      cwd=path, input=json.dumps(queries).encode(), timeout=240))


def check_runtime():
    from host.compile import core_library
    from host.template_selector import library
    queries = {}
    for profile in ('r2r-en', 'rxr-en-us'):
        rows = core_library('generator', profile) + library('generator', profile)
        queries[profile] = list(dict.fromkeys([r['input']['original_instruction'] for r in rows]
                                  + ['Turn left at the chair and stop in the second doorway.',
                                     'Return through the same door after stopping beside the window.']))
    current = snapshot(ROOT, queries)
    with tempfile.TemporaryDirectory(prefix='profile-baselines-') as directory:
        paths = []
        try:
            for ref, name in ((SOURCE, 'source'), (RXR_BASE, 'rxr')):
                path = Path(directory) / name
                subprocess.run(['git', 'worktree', 'add', '--detach', str(path), ref],
                               cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
                paths.append(path)
            source = snapshot(paths[0], {'r2r-en': queries['r2r-en']})
            old_rxr = snapshot(paths[1], {'rxr-en-us': queries['rxr-en-us']})
        finally:
            for path in paths:
                subprocess.run(['git', 'worktree', 'remove', '--force', str(path)], cwd=ROOT, check=True)
    if current['r2r-en'] != source['r2r-en']:
        raise ValueError('Imported R2R model prompt/schema/selection changed')
    for old, new in zip(old_rxr['rxr-en-us'], current['rxr-en-us']):
        if old['source'] != new['source'] or old['ids'] != new['ids']:
            raise ValueError('Retained RxR selection changed')
        if any(old['phases'][p]['schema'] != new['phases'][p]['schema'] for p in old['phases']):
            raise ValueError('RxR active output schema changed')
    # Repeat with the profile order reversed to detect shared cache contamination.
    interleaved = snapshot(ROOT, dict(reversed(list(queries.items()))))
    if interleaved != current:
        raise ValueError('Cross-profile cache/order contamination')
    return dict(r2r_inputs=len(queries['r2r-en']), rxr_inputs=len(queries['rxr-en-us']),
                phases_per_input=4, r2r_prompts_schema_selection_equal=True,
                rxr_schema_selection_equal=True, reversed_profile_order_equal=True,
                live_model_called=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = check_static()
    if args.runtime:
        report['runtime'] = check_runtime()
    data = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.write_text(data)
    print(data)

if __name__ == '__main__':
    main()
