"""Offline end-to-end demonstration using the same validated fixture builders as runtime tests."""
from pathlib import Path
import json
import sys

from adapter.source import from_record
from host.run import run_record

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
# Reuse the protocol-complete, maintained fixture constructors. They are imported
# explicitly from the test fixture module; no provider or network call is made.
sys.path.insert(0, str(ROOT / "tests"))
from test_runtime_contract_v2 import SOURCE, generator_candidate, reviewer_output  # noqa: E402


def main():
    record = json.loads((HERE / "record.json").read_bytes())
    record["original_instruction"] = SOURCE
    first = generator_candidate(repaired=False)
    repaired = generator_candidate(repaired=True)
    replies = [
        first,
        reviewer_output(first, repaired=False),
        {
            "candidate": repaired,
            "responses": [{
                "finding_index": 0,
                "decision": "accept",
                "source_quotes": ["go down the hall"],
                "reason": "The source explicitly requires the omitted hallway traversal.",
            }],
        },
        reviewer_output(repaired, repaired=True, r1=True),
    ]
    phases = [("generator", "initial"), ("reviewer", "review"),
              ("generator", "repair"), ("reviewer", "recheck")]
    call_index = 0

    def transport(request):
        nonlocal call_index
        expected = phases[call_index]
        actual = (request["role"], request["phase"])
        if actual != expected:
            raise AssertionError(f"Unexpected demo call order: expected {expected}, got {actual}")
        output = replies[call_index]
        call_index += 1
        return {
            "output": output,
            "receipt": {
                "model": request["model"],
                "effort": request["effort"],
                "request_id": f"offline-demo-{call_index}",
            },
        }

    result = run_record(
        from_record(record),
        transport,
        pins={role: {"model": "offline-fixture", "effort": "low"}
              for role in ("generator", "reviewer")},
    )
    if result["disposition"] != "accepted_candidate" or call_index != 4:
        raise AssertionError(f"Offline workflow did not complete successfully: {result.get('error')}")
    print(json.dumps({key: result[key] for key in (
        "disposition", "render_mode", "instruction", "instruction_sha256",
        "semantic_correctness_verified", "navigation_evaluated"
    )}, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
