import argparse
from workspace import owned, read_json, atomic_json
from result_contract import rows, aggregate

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True)
    a = p.parse_args()
    run = owned(a.run)
    result = aggregate(read_json(run / "run_manifest.json"), rows(run / "results.jsonl"))
    atomic_json(run / "summary.json", result)
    print(result)
