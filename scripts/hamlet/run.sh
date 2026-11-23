#!/usr/bin/env bash
# Preserve the existing protected server runtime and its dependency environment.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd "$root"
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
if [[ -n "${CASE1_PROTECTION:-}" ]]; then
  exec python -m awarevln_memory.training.pipeline "$@"
fi
exec "$root/scripts/with_runtime.sh" python -m awarevln_memory.training.pipeline "$@"
