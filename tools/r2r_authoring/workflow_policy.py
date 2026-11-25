"""Keep RxR verification read-only on R2R-managed trees.

Compare against this run's immutable input snapshot, not an old R2R policy.
The legacy RxR-only writer remains available outside R2R-managed trees.
"""


def rxr_workflow(text):
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('RxR workflow policy anchor drift: ' + old[:80])
        text = text.replace(old, new, 1)

    replace("      - 'tools/rxr*'\n",
            "      - '.github/workflows/rxr-development.yml'\n      - 'tools/rxr*'\n")
    replace(
        '          git worktree add --detach "$RUNNER_TEMP/r2r-baseline" "$BASE_COMMIT"\n',
        '''          set -euo pipefail
          comparison="$BASE_COMMIT"
          if test -f tools/r2r_authoring/source_inventory.json; then
            comparison="$GITHUB_SHA"
            echo "R2R_MANAGED=true" >> "$GITHUB_ENV"
          else
            echo "R2R_MANAGED=false" >> "$GITHUB_ENV"
          fi
          git worktree add --detach "$RUNNER_TEMP/r2r-baseline" "$comparison"
''')
    replace(
        '          python -B tools/build_rxr_reviewed.py --write\n',
        '''          if test "$R2R_MANAGED" != true; then
            python -B tools/build_rxr_reviewed.py --write
          fi
''')
    replace(
        '        run: python -B tools/build_rxr_teaching.py --verify-upstream\n',
        '''        run: |
          if test "$R2R_MANAGED" = true; then
            python -B tools/build_rxr_teaching.py --check
          else
            python -B tools/build_rxr_teaching.py --verify-upstream
          fi
''')
    replace(
        '''          python -B tools/refresh_rxr_integrity.py
          python -B tools/verify_package.py
      - name: Run inherited''',
        '''          if test "$R2R_MANAGED" != true; then
            python -B tools/refresh_rxr_integrity.py
          fi
          python -B tools/verify_package.py
      - name: Run inherited''')
    # The old variable is consumed by the independently pinned RxR selection
    # audit. Keep build-before/after isolation separate from historical replay.
    if text.count('R2R_BASELINE_DIR') != 3:
        raise ValueError('Unexpected build comparison variable references')
    text = text.replace('R2R_BASELINE_DIR', 'R2R_BUILD_BASELINE_DIR')
    replace('          import json, os, unittest\n',
            '          import json, os, sys, unittest\n')
    replace('          from pathlib import Path\n          all_tests=',
            '          from pathlib import Path\n'
            '          sys.path.insert(0, str(Path("tests").resolve()))\n'
            '          all_tests=')
    replace("unittest.defaultTestLoader.discover('tests')",
            "unittest.defaultTestLoader.discover('tests', top_level_dir='.')")
    replace("test.id()=='unittest.loader._FailedTest.test_release_transaction'",
            "test.id().endswith('.test_release_transaction')")
    replace('      - name: Record actual validation and inherited label audit\n',
            "      - name: Record actual validation and inherited label audit\n"
            "        if: env.R2R_MANAGED != 'true'\n")
    replace('      - name: Commit the complete tested artifact set before pushing\n',
            "      - name: Commit the complete tested artifact set before pushing\n"
            "        if: env.R2R_MANAGED != 'true'\n")
    text += '''      - name: Prove read-only RxR verification on the R2R-managed tree
        if: env.R2R_MANAGED == 'true'
        run: |
          set -euo pipefail
          git diff --exit-code
          test -z "$(git ls-files --others --exclude-standard)"
          python -B tools/verify_package.py
'''
    return text
