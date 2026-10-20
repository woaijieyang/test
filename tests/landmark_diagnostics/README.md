# Landmark-RxR diagnostic tools

Run from case1 root through scripts/with_runtime.sh. These preserve exploratory negative results; they do not generate accepted training or evaluation data. Run audit_landmark_connectivity.py on raw input first. Frozen raw source hashes and an exact join match are required. Geometry exploration additionally uses the case-owned .cache/geometry-tools diagnostic packages. Mesh builders use the authorized GPU7 EGL context and two CPUs; verify resources before restarting. All output profiles are DIAGNOSTIC_NOT_ACCEPTED. No changes to ongoing formal benchmark source/configuration are needed.

## Reproduce source-geometry diagnostics

Optional geometry tools are isolated from the frozen model environment. From a clean export, run `scripts/with_runtime.sh runtime/awarevln/bin/python -m pip install --no-deps --target .cache/geometry-tools -r tests/landmark_diagnostics/geometry-requirements.txt` only if the exact target packages are absent. Core numerical/native dependencies remain those in the model environment lock. Geometry scripts explicitly prepend this owned target in their own process; evaluation workers do not import from it. The pinned package versions were read from the actual diagnostic installation. Do not install these tools into the running model environment.
