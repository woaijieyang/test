#!/usr/bin/env bash
set -euo pipefail
runtime_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
code_root="$(cd -- "$runtime_dir/../../.." && pwd -P)"
if [[ "$code_root" == /data/zy/vln/case2 ]]; then
 exec /data/zy/vln/case2/scripts/with_graph_runtime.sh "$@"
fi
cd /data/zy/vln/case2
options=(--candidate-code-root "$code_root")
while [[ "${1:-}" == --results-write || "${1:-}" == --prepare-configs || "${1:-}" == --memory-broker || "${1:-}" == --storage-run ]]; do
 option="$1"; options+=("$option"); shift
 if [[ "$option" == --storage-run ]]; then options+=("$1"); shift; fi
done
if [[ "${1:-}" == --pose-broker || "${1:-}" == --pose-package-parent ]]; then
 echo "Current graph execution policy uses SimulatorAdapter only" >&2; exit 2
fi
exec /usr/bin/python3 -B "$runtime_dir/runtime_exec.py" "${options[@]}" -- "$@"
