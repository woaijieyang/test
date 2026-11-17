"""Dispatch independent generator/reviewer calls. Run from the case1 root."""
import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import ExitStack
import os
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import sys

from jsonschema import Draft202012Validator

PACKAGE = Path(__file__).resolve().parents[1]
CASE = PACKAGE.parents[2]
sys.path.insert(0, str(PACKAGE / "backends"))
from transport import CodexCLIBackend, ResponsesBackend, Task, execute_once, write_new

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def compile_role(role):
    folder = PACKAGE / role
    manifest = load(folder / "manifest.json")
    schema = load(folder / manifest["schema"])
    parts = [(folder / manifest["prompt"]).read_text(), "\nOUTPUT SCHEMA\n" + (folder / manifest["schema"]).read_text()]
    for name in manifest["examples"]:
        ex = load(folder / name)
        parts.append("\nTEACHING EXAMPLE " + ex["id"] + "\nInput:\n" + json.dumps(ex["input"], ensure_ascii=False)
                     + "\nOutput:\n" + json.dumps(ex["output"], ensure_ascii=False))
    return "\n".join(parts), schema

def validate(role, source, candidate, value, schema):
    Draft202012Validator(schema).validate(value)
    if role == "generator":
        ok = value["status"] == "ok"
        if bool(value["subtasks"]) != ok or bool(value["issues"]) == ok or any(not t.strip() for t in value["subtasks"]):
            raise ValueError("Invalid candidate state")
        findings = value["issues"]
    else:
        checks = value["stage_checks"]
        if [s["subtask_index"] for s in checks] != list(range(len(candidate["subtasks"]))):
            raise ValueError("Incomplete stage coverage")
        passed = value["verdict"] == "pass"
        findings = value["findings"]
        if bool(findings) == passed or (passed and candidate["status"] != "ok"):
            raise ValueError("Invalid verdict")
        for f in findings:
            if any(i < 0 or i >= len(checks) for i in f["subtask_indices"]):
                raise ValueError("Invalid finding index")
        for s in checks:
            if passed and (not s["source_quotes"] or not s["completion_condition"]):
                raise ValueError("Missing stage evidence")
            if any(not q or q not in source for q in s["source_quotes"]):
                raise ValueError("Invalid stage quote")
    if any(not f["source_quote"] or f["source_quote"] not in source for f in findings):
        raise ValueError("Invalid source quote")

def freeze(path, value):
    if path.exists():
        if load(path) != value:
            raise ValueError("Frozen file differs: " + str(path))
    else:
        write_new(path, value)

def dispatch(records, run, config, backend_name, provider):
    roles = ("generator", "reviewer")
    assets = {role: compile_role(role) for role in roles}
    repair = (PACKAGE / "generator/repair.md").read_text()
    max_rounds = config["max_review_rounds"]
    slots = {role: config[role + "_workers"] for role in roles}
    if any(type(n) is not int or n < 1 for n in [*slots.values(), max_rounds]):
        raise ValueError("Positive integer worker counts and review rounds required")
    freeze(run / "run.json", dict(backend=backend_name, policy=config, records_sha256=sha(json.dumps(records, ensure_ascii=False)),
                                    assets={r:sha(assets[r][0]) for r in roles}, repair_sha256=sha(repair)))
    def invoke(role, key, round_no, candidate, feedback):
        source = records[key]
        rules, schema = assets[role]
        payload = {"original_instruction": source}
        if candidate is not None:
            payload["candidate"] = candidate
        if role == "generator" and feedback is not None:
            rules += "\n" + repair
            payload["review"] = feedback
        prompt = ("Independent " + role + " for ONE record. Ignore all other records. No tools, other files, GT or subagents. "
                  "Return only schema JSON. Primary owns final acceptance and does not request repairs. "
                  "Review globally; pass valid alternatives. Verify feedback before repairing actual defects. "
                  f"Maximum total reviewer rounds {max_rounds}.\n" + rules + "\nACTUAL INPUT (process only this record)\n"
                  + json.dumps(payload, ensure_ascii=False))
        task = Task(role, prompt, schema)
        def check(value):
            validate(role, source, candidate, value, schema)
        directory = run / sha(key) / f"attempt{round_no}" / role
        if directory.exists():
            if not (directory / "validation.json").exists():
                raise RuntimeError("Incomplete call retained; reconcile before retry")
            receipt = load(directory / "receipt.json")
            if load(directory / "task.json")["compiled_prompt_sha256"] != sha(prompt) or receipt["output_sha256"] != sha(receipt["text"]):
                raise ValueError("Resume receipt mismatch")
            value = json.loads(receipt["text"])
            check(value)
        else:
            value = json.loads(execute_once(provider, task, directory, check).text)
        return value

    errors = {}
    with ExitStack() as stack:
        pools = {r:stack.enter_context(ThreadPoolExecutor(max_workers=slots[r])) for r in roles}
        pending = {}
        def submit(role, key, attempt, cand=None, feedback=None):
            future = pools[role].submit(invoke, role, key, attempt, cand, feedback)
            pending[future] = (role, key, attempt, cand)
        for key, source in records.items():
            directory = run / sha(key)
            directory.mkdir(exist_ok=True)
            freeze(directory / "source.json", {"record_id":key,"original_instruction":source,"instruction_sha256":sha(source)})
            submit("generator", key, 0)
        while pending:
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                role, key, attempt, cand = pending.pop(future)
                try:
                    value = future.result()
                except Exception as exc:
                    errors[key] = {"role":role,"attempt":attempt,"error_type":type(exc).__name__}
                    continue
                if role == "generator":
                    submit("reviewer", key, attempt, value)
                elif value["verdict"] != "pass" and attempt + 1 < max_rounds:
                    submit("generator", key, attempt+1, cand, value)
                else:
                    base = run / sha(key) / f"attempt{attempt}"
                    bind = {r:load(base/r/"receipt.json")["output_sha256"] for r in roles}
                    freeze(run / sha(key) / "await_primary.json", dict(record_id=key, attempt=attempt,
                           reviewer_verdict=value["verdict"], hashes=bind, primary_accepted=False,
                           proposed_units=cand["subtasks"] if value["verdict"]=="pass" else [records[key]]))
    print(json.dumps({"records":len(records),"await_primary":len(records)-len(errors),"technical":errors}))
    return bool(errors)

@contextmanager
def run_lock(path):
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0, 2)
            if not stream.tell():
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="UTF-8 JSONL: record_id, original_instruction")
    parser.add_argument("--run", type=Path, required=True, help="Directory under case1/outputs")
    parser.add_argument("--config", type=Path, default=PACKAGE / "config/workflow.json")
    parser.add_argument("--backend", choices=("codex_cli", "responses"))
    args = parser.parse_args()
    run = args.run.resolve()
    if CASE / "outputs" not in run.parents or not args.input.resolve().is_relative_to(CASE):
        parser.error("Use a case1 input and a run directory below case1/outputs")
    config = load(args.config)
    allowed = {"backend","codex_cli","responses","generator_workers","reviewer_workers","max_review_rounds"}
    cli_fields = {"executable","model","effort"}
    api_fields = {"endpoint","api_key_env","api_key_file","model","effort","timeout_seconds","max_output_tokens","structured_output"}
    if set(config) != allowed or set(config["codex_cli"]) - cli_fields or set(config["responses"]) - api_fields:
        parser.error("Unexpected workflow setting. Store credentials separately.")
    name = args.backend or config["backend"]
    if name == "codex_cli":
        params = config[name]
        if not shutil.which(params["executable"]):
            parser.error("Configured Codex executable is unavailable on this server")
        provider = CodexCLIBackend(**params, cwd=CASE)
    elif name == "responses":
        params = config[name]
        if not params["model"]:
            parser.error("Configure responses.model before using the API")
        provider = ResponsesBackend(**params)
        provider._key()  # Fail before creating requests if credentials are missing.
    else:
        parser.error("Unsupported backend")
    records = {}
    for line in args.input.read_text(encoding="utf-8-sig").splitlines():
        row = json.loads(line)
        key, source = row["record_id"], row["original_instruction"]
        if not isinstance(key,str) or not key.strip() or key in records or not isinstance(source,str) or not source.strip():
            parser.error("Empty or duplicate record")
        records[key] = source
    if not records:
        parser.error("Input is empty")
    run.mkdir(parents=True, exist_ok=True)
    with run_lock(run / ".dispatch.lock"):
        return dispatch(records, run, config, name, provider)

if __name__ == "__main__":
    raise SystemExit(main())

