"""Idempotent, exact-anchor integration of the isolated RxR extension.

This maintenance script never guesses an interface. Unexpected source edits are
an error, so a concurrent branch change cannot be silently overwritten.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def replace(path, old, new, count=1):
    file=ROOT/path
    text=file.read_text(encoding='utf-8')
    if old not in text:
        if new in text:
            return
        raise ValueError(f'Integration anchor missing: {path}: {old[:120]!r}')
    if text.count(old) != count:
        raise ValueError(f'Unexpected integration anchor multiplicity: {path}: {text.count(old)}')
    file.write_text(text.replace(old,new),encoding='utf-8')


def main():
    # Correct two short audit quotes to exactly match the explicitly authored
    # candidate and use the active repair operation (not a historical alias).
    replace('tools/rxr_lesson_specs.py', "'below the arch','until you are standing below it'", "'below it','until you are standing below it'")
    replace('tools/rxr_lesson_specs.py', "'the bottom of the grey staircase','Go down the grey staircase to its bottom'", "'its bottom','Go down the grey staircase to its bottom'")
    replace('tools/build_rxr_teaching.py', "operation='restore_source_semantics'", "operation='restore'")
    replace('tools/build_rxr_teaching.py',
            "        records=inventory))",
            "        records=inventory, templates=[dict(path=path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for role in ('generator','reviewer') for path in sorted((ROOT/role/'templates'/'RxR'/'train').glob('*.json'))]))")

    selector='host/template_selector.py'
    replace(selector, 'ROOT = Path(__file__).resolve().parents[1]',
            'from host.rxr_retrieval import features as rxr_features, rank_examples as rank_rxr_examples\nfrom host.rxr_assets import validate_training_library\n\nROOT = Path(__file__).resolve().parents[1]')
    replace(selector, "    files = []\n    for kind in dynamic_dirs:",
            "    if profile == 'rxr-en-us':\n        dynamic_dirs += ('train',)\n    files = []\n    for kind in dynamic_dirs:")
    replace(selector, '        validate_dynamic_identity(role, profile, row)\n',
            "        validate_dynamic_identity(role, profile, row)\n    if profile == 'rxr-en-us':\n        validate_training_library(role, rows)\n")
    replace(selector, "('RxR', 'generator'): 35, ('RxR', 'reviewer'): 64,", "('RxR', 'generator'): 43, ('RxR', 'reviewer'): 80,")
    replace(selector, "        expected_paired = 29 if dataset == 'R2R' else 35\n        expected_diagnostics = 23 if dataset == 'R2R' else 29",
            "        if dataset == 'RxR':\n            expected_pairs = {row['template_id'] for row in library('generator', profile)}\n        expected_paired = 29 if dataset == 'R2R' else 43\n        expected_diagnostics = 23 if dataset == 'R2R' else 37")
    replace(selector, 'cue_fn = features if profile == "rxr-en-us" else r2r_features',
            'cue_fn = rxr_features if profile == "rxr-en-us" else r2r_features', count=2)
    replace(selector, 'rank_fn = rank_examples if profile == "rxr-en-us" else rank_r2r_examples',
            'rank_fn = rank_rxr_examples if profile == "rxr-en-us" else rank_r2r_examples')
    replace(selector, '        allowed = ("val_seen",) if role == "generator" else ("paired", "diagnostics")',
            '        allowed = ("val_seen",) if role == "generator" else ("paired", "diagnostics")\n        if profile == "rxr-en-us":\n            allowed += ("train",)')

    runtime='host/run.py'
    replace(runtime, '            root/"reviewer/dataset_rules/rxr_en_us.md",\n',
            '            root/"reviewer/dataset_rules/rxr_en_us.md",\n            root/"host/rxr_retrieval.py",\n            root/"host/rxr_assets.py",\n            root/"provenance/rxr_training_sources.json",\n')
    replace(runtime, '            root/role/"dataset_rules/rxr_en_us.md",\n',
            '            root/role/"dataset_rules/rxr_en_us.md",\n            root/"host/rxr_retrieval.py",\n            root/"host/rxr_assets.py",\n            root/"provenance/rxr_training_sources.json",\n')
    replace(runtime, '    fixed = core_library(role, profile)\n',
            '    if profile == "rxr-en-us":\n        from host.rxr_assets import validate_training_assets\n        validate_training_assets()\n    fixed = core_library(role, profile)\n')

    replace('tests/test_closed_loop_35.py', "('rxr-en-us',(35,64))", "('rxr-en-us',(43,80))")
    rxr_test='tests/test_rxr_profile.py'
    replace(rxr_test, 'selection["actual_generator_examples"], 35)', 'selection["actual_generator_examples"], 43)')
    replace(rxr_test, 'selection["actual_reviewer_examples"], 64)', 'selection["actual_reviewer_examples"], 80)')
    replace(rxr_test, 'selection["reviewer_pair_count"], 35)', 'selection["reviewer_pair_count"], 43)')
    replace(rxr_test, 'len(selection["reviewer_diagnostic_ids"]), 29)', 'len(selection["reviewer_diagnostic_ids"]), 37)')
    replace(rxr_test, 'len(rxr["files"]), 4)', 'len(rxr["files"]), 7)')
    replace(rxr_test, 'len(metadata["files"]), 4)', 'len(metadata["files"]), 7)')

    for role in ('generator','reviewer'):
        path=ROOT/role/'templates_manifest.json'
        data=json.loads(path.read_text())
        data.pop('version',None)
        profile=data['dataset_profiles']['rxr-en-us']
        profile['training_directory']='templates/RxR/train'
        profile['training_source_count']=8
        profile['fixed_core_source']='Frozen original teaching cases expressed using the current authored template contract.'
        if role=='generator':
            profile['dynamic_count']=43
            profile['runtime_dynamic_count']=43
        else:
            profile['paired_count']=43
            profile['diagnostics_count']=37
            profile['runtime_dynamic_count']=80
        # Keep the entire R2R configuration and every example-count policy intact.
        data['selection']='Profile-scoped Core is unconditional. Dynamic examples supplement it; RxR adds source-verified training relations, with paired reviews and separately selected diagnostics.'
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    readme=ROOT/'README.md'
    text=readme.read_text(encoding='utf-8')
    text=text.split('\n',1)[1] if text.startswith('# ') else text
    text='# LLM-decompose-v6.6.2\n'+text
    marker='## RxR semantic calibration'
    if marker not in text:
        text+='\n'+marker+'\n\nRxR-only event, correction, relation and entry calibration with eight verified train-guide lesson groups. Fixed Core and per-request example counts are unchanged. R2R is protected by four-phase prompt/schema and selection comparisons. See [the implementation and validation contract](docs/RXR_ENHANCEMENT.md). Engineering checks do not establish navigation gains.\n'
    readme.write_text(text,encoding='utf-8')

if __name__=='__main__':
    main()
