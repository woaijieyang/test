"""Request-bound Codex CLI journal. Keep outside the published source directory."""
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from uuid import UUID, uuid4

from shared.identity import obj_hash


def save(path, value):
    tmp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    with tmp.open("x", encoding="utf8") as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


class JournalCLI:
    def __init__(self, ledger, task_key, *, executable=None, sessions=None, timeout=600):
        self.root = Path(ledger).resolve()
        self.task_key = task_key
        self.executable = executable
        self.sessions = Path(sessions) if sessions else Path(os.environ.get("CODEX_HOME") or Path.home()/".codex")/"sessions"
        self.timeout = timeout

    def _inspect(self, attempt, request):
        if (json.loads((attempt/"request.json").read_bytes()) != request or
                json.loads((attempt/"identity.json").read_bytes()) != self.task_key):
            raise RuntimeError("CLI_REQUEST_BINDING_MISMATCH")
        exit_file = attempt/"exit.json"
        code = json.loads(exit_file.read_bytes())["code"] if exit_file.exists() else None
        event_file = attempt/"events.jsonl"
        events = list(map(json.loads, event_file.read_bytes().splitlines())) if event_file.exists() else []
        complete = [x for x in events if x.get("type") == "turn.completed"]
        if code is None:
            # After a bridge crash, require both a terminal turn and agreement
            # with its final agent message; a partially written file is insufficient.
            messages = [e["item"].get("text") for e in events if e.get("type") == "item.completed"
                        and e.get("item", {}).get("type") == "agent_message"]
            output_file = attempt/"output.txt"
            if not (len(complete) == 1 and messages and output_file.is_file()
                    and output_file.read_text(encoding="utf8").rstrip("\r\n") == messages[-1]
                    and events[-1].get("type") == "turn.completed"):
                raise RuntimeError("CLI_EXIT_UNKNOWN: reconcile original invocation before resubmitting")
            code = 0
        if code and not complete and events and events[-1].get("type") == "turn.failed":
            if events[-1].get("error", {}).get("message") == "workspace routing discovery failed" and not any(
                x.get("item", {}).get("type") == "agent_message" for x in events
            ):
                return None
        if code or len(complete) != 1:
            raise RuntimeError("CLI_EXECUTION_UNRESOLVED: retained events and stderr")
        tids = [x["thread_id"] for x in events if x.get("type") == "thread.started"]
        if len(tids) != 1 or str(UUID(tids[0])) != tids[0]:
            raise RuntimeError("CLI_THREAD_IDENTITY_MISSING")
        contexts = []
        for session in self.sessions.glob("*/*/*/*" + tids[0] + "*.jsonl"):
            with session.open(encoding="utf8") as stream:
                for line in stream:
                    if '"turn_context"' in line:
                        e = json.loads(line)
                        if e.get("type") == "turn_context":
                            contexts.append(e["payload"])
        if not contexts or any((c.get("model"), c.get("effort")) !=
                               (request["model"], request["effort"]) for c in contexts):
            raise RuntimeError("CLI_ACTUAL_MODEL_UNVERIFIED")
        raw = (attempt/"output.txt").read_bytes()
        try:
            output = json.loads(raw)
            state = "parsed"
        except json.JSONDecodeError:
            # A completed, verified invocation can receive schema-type feedback.
            output = raw.decode("utf8")
            state = "malformed_json"
        usage = complete[0].get("usage") or {}
        receipt = dict(request_id=tids[0], model=request["model"], effort=request["effort"],
                       provider_request_sha256=obj_hash(request), input_tokens=usage.get("input_tokens"),
                       output_tokens=usage.get("output_tokens"), parse_state=state,
                       raw_sha256=hashlib.sha256(raw).hexdigest())
        return dict(output=output, receipt=receipt)

    def recover(self, request):
        parent = self.root/obj_hash([self.task_key, request])[:32]
        for a in sorted(parent.glob("attempt-*"), reverse=True):
            return self._inspect(a, request)
        return None

    def __call__(self, request):
        parent = self.root/obj_hash([self.task_key, request])[:32]
        parent.mkdir(parents=True, exist_ok=True)
        gate = self.root/"route-cooldown.json"
        for i in range(3):
            attempt = parent/f"attempt-{i}"
            if not attempt.exists() and gate.exists():
                until = json.loads(gate.read_bytes())["until"]
                delay = min(12.0, until - time.time())
                if delay > 0:
                    time.sleep(delay + int(parent.name[:2], 16)/255)
            try:
                attempt.mkdir()
            except FileExistsError:
                if not (attempt/"request.json").exists():
                    raise RuntimeError("CLI_ATTEMPT_CLAIMED: launch status unknown")
            else:
                save(attempt/"identity.json", self.task_key)
                save(attempt/"request.json", request)
                exe = self.executable or shutil.which("codex.cmd" if os.name == "nt" else "codex")
                if not exe:
                    raise RuntimeError("CODEX_EXECUTABLE_MISSING")
                args = [exe, "exec", "-m", request["model"], "-c", "model_reasoning_effort="+json.dumps(request["effort"]),
                        "-c", 'approval_policy="never"', "--sandbox", "read-only", "--skip-git-repo-check",
                        "--json", "--color", "never", "--output-last-message", str(attempt/"output.txt"), "-"]
                with (attempt/"events.jsonl").open("xb") as log, (attempt/"stderr.txt").open("xb") as err:
                    proc = subprocess.run(args, input="\n\n".join(m["content"] for m in request["messages"]).encode(),
                                          stdout=log, stderr=err, timeout=self.timeout)
                save(attempt/"exit.json", {"code": proc.returncode})
            reply = self._inspect(attempt, request)
            if reply is not None:
                return reply
            if i < 2:
                save(gate, {"until": time.time() + 5*2**i})
        raise RuntimeError("CLI_ROUTING_UNAVAILABLE: three confirmed failures retained")

def main():
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Codex CLI journal bridge; one JSON request on stdin")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--task-key", required=True)
    parser.add_argument("--lookup", action="store_true")
    args = parser.parse_args()
    cli = JournalCLI(args.ledger, args.task_key)
    data = json.load(sys.stdin)
    if args.lookup:
        request = data["request"]
        if data.get("operation") != "lookup_original_request" or data.get("request_sha256") != obj_hash(request):
            raise ValueError("Lookup identity mismatch")
        reply = cli.recover(request)
        result = {"found": reply is not None, "reply": reply}
    else:
        result = cli(data)
    json.dump(result, sys.stdout, ensure_ascii=True)


if __name__ == "__main__":
    main()
