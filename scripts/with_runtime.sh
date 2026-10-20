#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$root"
options=()
while [[ "${1:-}" == --results-write || "${1:-}" == --prepare-configs ]]; do
    options+=("$1")
    shift
done
exec /usr/bin/python3 -B "$root/scripts/runtime_exec.py" "${options[@]}" -- "$@"
