import argparse, json, os
from result_contract import register

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True)
    a = p.parse_args()
    if not json.loads(os.environ.get("CASE1_PROTECTION", "{}")).get("results_write"):
        raise SystemExit("Use with_runtime.sh --results-write for registration")
    register(a.run)
    print("Registered; run render_results.py next")
