"""Finalize reviewed source migrations without dropping inherited assertions.

The changed RxR inventory and prompt snapshots reflect the intentional RxR
extension. R2R content is compared with an immutable baseline before any shared
runtime integrity pin may be refreshed.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path, old, new):
    file = ROOT / path
    text = file.read_text(encoding='utf-8')
    if old not in text:
        if new in text:
            return
        raise ValueError(f'Migration anchor missing: {path}: {old!r}')
    if text.count(old) != 1:
        raise ValueError(f'Ambiguous migration anchor: {path}: {old!r}')
    file.write_text(text.replace(old, new), encoding='utf-8')


def main():
    replace_once('tests/test_rxr_calibration.py',
                 "self.assertIn('not a mandatory new entry sentence',prompt)",
                 "self.assertIn('Every stage requires an intelligible, supported entry state',prompt)")
    # These are inventory assertions, not relaxed validation. Each added source
    # produces exactly one generator, one paired review and one diagnostic.
    replace_once('tests/test_roles_repair.py',
                 "('rxr-en-us',(35,64))", "('rxr-en-us',(43,80))")
    replace_once('tests/test_r2r_specialization.py',
                 'self.assertEqual(len(rxr["files"]), 4)',
                 'self.assertEqual(rxr["files"], [\n'
                 '            "shared/semantic_contract.md",\n'
                 '            "shared/dataset_rules/rxr_en_us.md",\n'
                 '            "generator/dataset_rules/rxr_en_us.md",\n'
                 '            "reviewer/dataset_rules/rxr_en_us.md",\n'
                 '            "host/rxr_retrieval.py",\n'
                 '            "host/rxr_assets.py",\n'
                 '            "provenance/rxr_training_sources.json",\n'
                 '        ])')
    # Reviewed, literal snapshots from the actual compiled RxR messages. Do not
    # derive expected values from the function under test or disable this test.
    replacements = {
        'a7dfd35332c41f8ac150d0fba18fdafe294d00d6601c75aff72bf5135d7d61c5':
        '8793949f5f2037cfeb6c1e3158f3c1440047860c8bf0c02f296b04b72e681550',
        'b4b880fec24d46e951d01157f104152041df1cddf250cde4611668aea8c6a95a':
        'bb96ba0eb4d764ac5c9e49045bd3ffbae4259ac68cf69b0c8b21cc5a6271ccae',
        '91e0ca112eda38413521c2423b13c69b84d747825a1e5098f89389f7e815cc9b':
        '7944892ea3ffb0ce1d86a454ed2b03a642e65c22410c98aff34a0002ee8443de',
    }
    for old, new in replacements.items():
        replace_once('tests/test_r2r_specialization.py', old, new)
    # Only README receives a release display label. Runtime identities use
    # profile names and content hashes; no release suffix is introduced here.
    integration = ROOT / 'tools/integrate_rxr.py'
    lines = integration.read_text(encoding='utf-8').splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.strip().startswith("text='# LLM-decompose-"):
            lines[index] = ("    import os\n"
                            "    branch=os.environ.get('GITHUB_REF_NAME','LLM-decompose')\n"
                            "    text='# '+branch+'\\n'+text\n")
    integration.write_text(''.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
