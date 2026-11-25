"""Run every repository regression, reporting an absent external fixture honestly.

No test, runtime source, prompt expectation or template is changed by this tool.
A report path is explicit; use a temporary path for read-only CI validation.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / 'tests'))
    # Historical isolation tests own their exact baseline; never inherit an
    # unrelated checkout from a surrounding single-profile build job.
    os.environ.pop('R2R_BASELINE_DIR', None)
    selected = unittest.TestSuite()
    external = []

    def collect(suite):
        for test in suite:
            if isinstance(test, unittest.TestSuite):
                collect(test)
                continue
            error = str(getattr(test, '_exception', ''))
            missing_external = (test.id().endswith('.test_release_transaction')
                                and 'FileNotFoundError' in error and 'manage_release.py' in error)
            if missing_external:
                external.append({'test': test.id(),
                                 'reason': 'Missing external manage_release.py; not counted as passed.'})
            else:
                selected.addTest(test)

    collect(unittest.defaultTestLoader.discover('tests', top_level_dir='.'))
    result = unittest.TextTestRunner(verbosity=2).run(selected)
    report = dict(tests_run=result.testsRun,
                  failures=[{'test': str(t), 'traceback': e} for t, e in result.failures],
                  errors=[{'test': str(t), 'traceback': e} for t, e in result.errors],
                  skipped=[{'test': str(t), 'reason': r} for t, r in result.skipped],
                  external_fixture_tests_not_run=external, success=result.wasSuccessful(),
                  source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  workflow_run=os.environ.get('GITHUB_RUN_ID'),
                  navigation_evaluated=False, live_provider_evaluated=False,
                  token_budget_verified=False)
    data = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(data, encoding='utf-8')
    print(data)
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
