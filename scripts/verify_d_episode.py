"""One real R2R 1015 D run, from reviewed CLI receipts to a token-level audit."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path.cwd()
REFERENCE = ROOT / "outputs/subtaskAdapter/llm-valunseen-B-Remaining-de-20261105-r0/navigation-batch001/runs/D-r2r-smoke"
MIGRATIONS = {
    "scripts/subtaskAdapter/native_language_worker.py": (
        "3f2ec7d664f068676c9188acaa0dba2a54a36f7d6e727a090b2ce838166fb89c",
        "477e93e324c2b2214e9740ef27cbce24cb19a1dc41e9614345d13cae087f9423"),
    "src/subtaskAdapter/base/agent_semantic_validation.py": (
        "9536a7e494ed85c0ca093c8829ba4341d763e314143d83344df9a47ab1e9e626",
        "7fa24fbd9eab9055a3b3c79f0952163359cd233326552f1f3b10a2051ff980bf"),
}
def load(p):
    return json.loads(p.read_bytes())
def sha(data):
    return hashlib.sha256(data).hexdigest()
def save(p, value):
    with p.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
def original():
    row, = load(REFERENCE/"mapping.json")["records"]
    artifact = ROOT/row["language_file"]
    assert sha(artifact.read_bytes()) == row["sha256"]
    return load(ROOT/load(artifact)["source_original"])
def prepare(p):
    orig = original()
    key = orig["task_key"]
    language = p/"language"/sha(key.encode())
    decision = load(p/"primary.json")
    pending = load(language/"await_primary.json")
    assert decision["owner"]=="primary" and decision["verdict"]==pending["reviewer_verdict"]=="pass"
    assert decision["record_id"]==pending["record_id"]==key
    assert decision["hashes"]==pending["hashes"] and decision["attempt"]==pending["attempt"]
    assert load(language/"source.json")["original_instruction"]==orig["assigned_task_text"]
    attempt = language/f"attempt{pending['attempt']}"
    receipts = {}
    for role in ("generator","reviewer"):
        receipt=load(attempt/role/"receipt.json")
        assert load(attempt/role/"validation.json")["status"]=="STRUCTURE_AND_SOURCE_CHECKED_NOT_SEMANTIC_PASS"
        assert sha(receipt["text"].encode())==decision["hashes"][role]
        receipts[role]=json.loads(receipt["text"])
    assert receipts["reviewer"]["verdict"]=="pass"
    units=receipts["generator"]["subtasks"]
    assert units==pending["proposed_units"] and len(units)>=2
    text="\n".join(units)
    run=p/"navigation"
    run.mkdir()
    artifact=run/"instruction.json"
    save(artifact,dict(task_key=key, instruction_sha256=sha(orig["assigned_task_text"].encode()),
        assigned_task_text=text, assigned_task_sha256=sha(text.encode()), subtasks=units,
        dispatch_permission=False,source_review={"status":"SOURCE_LANGUAGE_ACCEPTED"},variant="D"))
    paths=[artifact,run/"mapping.json",run/"config.yaml"]
    save(paths[1],dict(records=[dict(language_file=str(artifact.relative_to(ROOT)),sha256=sha(artifact.read_bytes()))]))
    manifest=load(REFERENCE/"manifest.json")
    assert manifest["variant"]=="D" and manifest["task_keys"]==[key] and manifest["static_subtask_input"] and manifest["goal_adapter_enabled"] is False
    assert not any(k in manifest for k in ("method_id","method_config","task_assembly_mapping","llm_context_variant"))
    oldfiles=[REFERENCE/"mapping.json",REFERENCE/"config.yaml",ROOT/load(REFERENCE/"mapping.json")["records"][0]["language_file"]]
    for path in oldfiles:
        assert manifest["files"].pop(str(path.relative_to(ROOT)))==sha(path.read_bytes())
    for name,(old,new) in MIGRATIONS.items():
        assert manifest["files"][name]==old and sha((ROOT/name).read_bytes())==new
        manifest["files"][name]=new
    config=(REFERENCE/"config.yaml").read_text()
    assert str(REFERENCE) in config
    paths[2].write_text(config.replace(str(REFERENCE),str(run)))
    for path in [*paths,p/"primary.json",language/"await_primary.json"]:
        manifest["files"][str(path.relative_to(ROOT))]=sha(path.read_bytes())
    manifest["language_mapping"]=str(paths[1].relative_to(ROOT))
    manifest["trace_descriptor"]["run_id"]=p.name
    manifest["source_sha256"]=sha(json.dumps(manifest["files"],sort_keys=True).encode())
    save(run/"manifest.json",manifest)
    print(text)

def audit(p):
    from transformers import AutoTokenizer
    from llava.mm_utils import tokenizer_image_token
    from llava.constants import IMAGE_TOKEN_INDEX
    run=p/"navigation"
    manifest=load(run/"manifest.json")
    assert manifest["goal_adapter_enabled"] is False and not any((run/n).exists() for n in ["native-goals","rule-episodes"])
    assert load(run/"source-freeze.json")["status"]=="CLOSED"
    assert load(run/"worker-result.json")["status"]=="EXECUTION_COMPLETE_PENDING_INDEPENDENT_AUDIT"
    trace=run/"trace";result,=map(json.loads,(trace/"results.jsonl").read_text().splitlines())
    key,=manifest["task_keys"];assert result["task_key"]==key
    artifact=load(run/"instruction.json");text=artifact["assigned_task_text"]
    assert text=="\n".join(artifact["subtasks"])
    path=trace/result["trace_path"];assert sha(path.read_bytes())==result["trace_sha256"]
    events=list(map(json.loads,path.read_text().splitlines()))
    calls=[ev for ev in events if ev["kind"]=="model_call"]
    bindings=list(map(json.loads,(run/"input-language-bindings.jsonl").read_text().splitlines()))
    assert len(calls)==len(bindings)==result["model_calls"] and calls
    tokenizer=AutoTokenizer.from_pretrained(str(ROOT/"models/awarevln/llm"),local_files_only=True,use_fast=False,legacy=False)
    for call,binding in zip(calls,bindings):
        assert call["task_key"]==binding["task_key"]==key and call["frame"]==binding["frame_id"]
        assert call["prompt"].count('Your assigned task is: "'+text+'". ')==1
        assert binding["assigned_task_sha256"]==sha(text.encode()) and binding["progress_assertion"] is None
        assert len(call["images"])==len(binding["slots"])==8
        assert tokenizer_image_token(call["prompt"],tokenizer,IMAGE_TOKEN_INDEX)==call["input_ids"][0]
    steps=sum(ev["kind"]=="primitive_action" for ev in events)
    assert steps==result["primitive_steps"] and events[-1]["kind"]=="terminal"
    independent=trace/"independent_metrics.json"
    if not independent.exists():
        subprocess.run([sys.executable,"-B","scripts/recompute_metrics.py","--run",str(trace)],check=True)
    row,=load(independent)["results"];assert row["task_key"]==key and row["trace_sha256"]==result["trace_sha256"]
    for metric in ("sr","spl","ndtw","ne","oracle_sr"):
        assert abs(row["metrics"][metric]-result["metrics"][metric])<1e-4
    report=dict(status="PASS",task_key=key,exact_text_and_tokens_verified_calls=len(calls),environment_steps=steps,
       goal_adapter_enabled=False,instruction=text,instruction_sha256=sha(text.encode()),trace_sha256=result["trace_sha256"],
       metrics=row["metrics"],stop_source=result["stop_source"],termination=result["termination_reason"])
    if (p/"audit.json").exists():assert load(p/"audit.json")==report
    else:save(p/"audit.json",report)
    print(json.dumps(report,ensure_ascii=False))

def main():
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument("action",choices=["source","approve","prepare","audit"])
    args.add_argument("run",type=Path)
    args.add_argument("--candidate-sha256", help="Hash reviewed by the primary conversation")
    args.add_argument("--reviewer-sha256", help="Hash of the independently reviewed verdict")
    args.add_argument("--primary-id")
    args.add_argument("--note", help="Record the actual primary review rationale")
    opt=args.parse_args();p=opt.run.resolve()
    if not p.is_relative_to(ROOT/"outputs/subtaskAdapter") or p==ROOT/"outputs/subtaskAdapter":args.error("Run must be under case1/outputs/subtaskAdapter")
    if opt.action=="source":
        p.mkdir(parents=True,exist_ok=False);s=original()
        (p/"one.jsonl").write_text(json.dumps(dict(record_id=s["task_key"],original_instruction=s["assigned_task_text"]))+"\n")
    elif opt.action=="approve":
        if not all([opt.candidate_sha256,opt.reviewer_sha256,opt.primary_id,opt.note]):
            args.error("Explicit reviewed hashes, primary ID and rationale required")
        pending_file, = (p/"language").glob("*/await_primary.json")
        pending=load(pending_file)
        hashes=dict(generator=opt.candidate_sha256,reviewer=opt.reviewer_sha256)
        if hashes!=pending["hashes"] or pending["reviewer_verdict"]!="pass":
            args.error("No matching passing reviewed candidate")
        save(p/"primary.json",dict(owner="primary",verdict="pass",record_id=pending["record_id"],
             attempt=pending["attempt"],hashes=hashes,primary_thread_id=opt.primary_id,rationale=opt.note))
    elif opt.action=="prepare":prepare(p)
    else:audit(p)
if __name__=="__main__":main()
