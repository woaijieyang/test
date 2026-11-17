import argparse
from workspace import owned, atomic_json
from result_contract import audit

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True)
    a = p.parse_args()
    run = owned(a.run)
    summary, receipt = audit(run)
    atomic_json(run / "validation.json", receipt)
    print({"status": "PASS", "run_id": receipt["run_id"]})
