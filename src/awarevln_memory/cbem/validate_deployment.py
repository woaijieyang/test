from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from awarevln_memory.cbem.router import validate_deployment_contract


def validate_deployment(checkpoint: str | Path) -> dict[str, Any]:
    validation = validate_deployment_contract(
        checkpoint,
        require_eligible=True,
    )
    return {
        "status": "verified",
        "deployment_eligible": validation["deployment_eligible"],
        "final_gate_passed": validation["final_gate"]["passed"],
        "artifact_manifest_sha256": validation[
            "artifact_manifest_provenance"
        ]["sha256"],
        "training_manifest_sha256": validation[
            "training_manifest_provenance"
        ]["sha256"],
        "deployment_manifest_sha256": validation[
            "deployment_provenance"
        ]["sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed CBEM deployment-manifest preflight"
    )
    parser.add_argument("--checkpoint", required=True)
    args = parser.parse_args()
    json.dump(validate_deployment(args.checkpoint), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
