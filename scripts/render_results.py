import argparse, json, os
from workspace import ROOT, read_json
from result_contract import render

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true")
    a = p.parse_args()
    if not a.check and not json.loads(os.environ.get("CASE1_PROTECTION", "{}")).get(
        "results_write"
    ):
        raise SystemExit("Use with_runtime.sh --results-write to generate result documents")
    root = ROOT / "results-show"
    table, reports = render(read_json(root / "records.json"))
    for name, content in {"model_results.md": table, **reports}.items():
        path = root / name
        if a.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit("Generated document drift: " + name)
        else:
            path.write_text(content, encoding="utf-8")
    print("Result documents verified" if a.check else "Result documents generated")
