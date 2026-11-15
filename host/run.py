"""Bounded G0 -> R0 -> optional G1 -> R1 workflow.

The run preserves the existing transport, source identity, renderer snapshots,
failure receipts, and exact-source fallback. It never retries an ambiguous
transport call and never releases a snapshot other than the one R0/R1 reviewed.
"""
from __future__ import annotations

from typing import Callable
from subprocess import run as subprocess_run
import json
import argparse
import sys
from pathlib import Path

from adapter.source import Source, load_record
from renderer.freeze import freeze, unchanged
from host.compile import compile_prompt
from host.template_selector import select_examples, DEFAULT_EXAMPLES
from host import protocol
from shared.identity import need, canonical, obj_hash, text_hash, ContractError

Transport = Callable[[dict], dict]
VERSION = "final-best-v1-runtime-contract-v2"


def request(role, phase, payload, pin, profile, selected_ids):
    text, active_schema = compile_prompt(
        role, phase, profile=profile, selected_ids=selected_ids
    )
    return {
        "role": role,
        "phase": phase,
        "model": pin["model"],
        "effort": pin["effort"],
        "messages": [
            {"role": "system", "content": text},
            {"role": "user", "content": canonical(payload)},
        ],
        "output_schema": active_schema,
        "selected_example_ids": list(selected_ids),
    }


def run_record(src: Source, transport: Transport, *, pins: dict,
               separator="\n", example_count=DEFAULT_EXAMPLES,
               selection_mode="adaptive"):
    """Run at most four calls; preserve exact source fallback on every failure."""
    events, snapshots = [], []
    selections = {role: [] for role in ("generator", "reviewer")}
    context = {"step": "configuration_validation", "role": None, "phase": None}

    def call(role, phase, payload, candidate_digest=None):
        context.update(step="request_construction", role=role, phase=phase)
        req = request(role, phase, payload, pins[role], src.profile, selections[role])
        system, user = req["messages"]
        event = {
            "role": role, "phase": phase, "request": req,
            "request_sha256": obj_hash(req),
            "system_sha256": text_hash(system["content"]),
            "schema_sha256": obj_hash(req["output_schema"]),
            "source_sha256": src.sha,
            "reviewed_snapshot": candidate_digest,
            "selected_example_ids": list(selections[role]),
            "call_state": "request_constructed",
        }
        events.append(event)
        context["step"] = "transport"
        event["call_state"] = "transport_entered"
        try:
            reply = transport(req)
        except Exception:
            # The provider may have executed the call; do not retry blindly.
            event["call_state"] = "transport_failed_execution_unknown"
            raise
        event["call_state"] = "transport_returned"
        context["step"] = "receipt_validation"
        need(isinstance(reply, dict) and "output" in reply,
             "Malformed transport reply", code="TRANSPORT_REPLY_INVALID",
             module="host.run", path="/output")
        event["raw_output"] = reply["output"]
        receipt = reply.get("receipt", {})
        need(isinstance(receipt, dict), "Malformed provider receipt",
             code="MODEL_RECEIPT_INVALID", module="host.run", path="/receipt")
        event["receipt"] = {
            key: receipt.get(key) for key in (
                "model", "effort", "request_id", "provider_request_sha256",
                "input_tokens", "output_tokens"
            )
        }
        event["call_state"] = "receipt_received"
        valid = (
            receipt.get("model") == req["model"] and
            receipt.get("effort") == req["effort"] and
            bool(receipt.get("request_id"))
        )
        if not valid:
            event["call_state"] = "receipt_invalid"
        need(valid, "Missing or mismatched actual invocation metadata",
             code="MODEL_RECEIPT_MISMATCH", module="host.run", path="/receipt",
             expected={"model": req["model"], "effort": req["effort"],
                       "request_id": "nonempty"})
        event["output_sha256"] = obj_hash(reply["output"])
        event["call_state"] = "receipt_verified"
        return reply["output"]

    def finish(disposition, view, detail=None, diagnostic=None):
        return {
            "version": VERSION,
            "task_key": src.key,
            "profile": src.profile,
            "source_sha256": src.sha,
            "example_selection": {
                "mode": selection_mode,
                "configured_example_count": example_count,
                "actual_generator_examples": len(selections["generator"]),
                "actual_reviewer_examples": len(selections["reviewer"]),
                "generator": list(selections["generator"]),
                "reviewer": list(selections["reviewer"]),
            },
            "disposition": disposition,
            "render_mode": view.mode,
            "instruction": view.rendered,
            "instruction_sha256": view.sha,
            "snapshot_sha256": view.snapshot,
            "separator_policy": repr(separator),
            "error": detail,
            "diagnostic": diagnostic,
            "semantic_correctness_verified": False,
            "navigation_evaluated": False,
            "snapshots": snapshots,
            "calls": events,
        }

    try:
        need(
            isinstance(pins, dict) and set(pins) == {"generator", "reviewer"} and
            all(isinstance(v, dict) and
                all(isinstance(v.get(k), str) and v[k] for k in ("model", "effort"))
                for v in pins.values()),
            "Explicit model/effort pins required for both roles",
            code="CONFIGURATION_INVALID", module="host.run", path="/pins"
        )
        context["step"] = "example_selection"
        selections = {
            role: select_examples(role, src.profile, src.raw,
                                  count=example_count, mode=selection_mode)
            for role in ("generator", "reviewer")
        }
        source_payload = {"original_instruction": src.raw}
        g0 = call("generator", "initial", source_payload)

        r0_review = None
        r0_candidate = None
        r0_rendered = None

        for turn in range(2):
            phase_g = "initial" if turn == 0 else "repair"
            context.update(step="generator_validation", role="generator", phase=phase_g)
            protocol.generator(src.raw, g0)
            active = g0["status"] == "ok"
            context["step"] = "renderer_freeze"
            view = freeze(src, g0["subtasks"], separator) if active else unchanged(src)

            candidate = {
                "status": g0["status"],
                "subtasks": list(view.stages) if active else [],
                "issues": g0["issues"],
            }
            candidate_json = canonical(candidate)
            candidate_snapshot = json.loads(candidate_json)
            snapshot = {
                "candidate": candidate_snapshot,
                "candidate_sha256": text_hash(candidate_json),
                "rendered_instruction": view.rendered if active else src.raw,
                "rendered_sha256": view.sha,
                "render_snapshot_sha256": view.snapshot if active else None,
                "mode": view.mode if active else "SOURCE_EXACT",
                "ledger": json.loads(view.ledger_json) if active else None,
            }
            binding = obj_hash([
                src.key, src.sha, snapshot["candidate_sha256"],
                snapshot["render_snapshot_sha256"]
            ])
            snapshot["bound_candidate"] = binding
            snapshots.append(snapshot)

            reviewer_payload = {
                **source_payload,
                "candidate": candidate_snapshot,
                "rendered_instruction": snapshot["rendered_instruction"],
            }
            if turn == 1:
                # R1 is a fresh session but must receive the exact R0 evidence
                # needed to verify each prior blocking finding.
                reviewer_payload.update({
                    "prior_review": r0_review,
                    "prior_candidate": r0_candidate,
                    "prior_rendered_instruction": r0_rendered,
                })

            review_phase = "review" if turn == 0 else "recheck"
            rv = call("reviewer", review_phase, reviewer_payload, binding)
            context.update(step="reviewer_validation", role="reviewer", phase=review_phase)
            protocol.reviewer(
                src.raw, candidate, rv,
                rendered_instruction=snapshot["rendered_instruction"],
                prior_review=r0_review if turn == 1 else None,
                prior_candidate=r0_candidate if turn == 1 else None,
                prior_rendered_instruction=r0_rendered if turn == 1 else None,
            )

            if turn == 0:
                r0_review = rv
                r0_candidate = candidate_snapshot
                r0_rendered = snapshot["rendered_instruction"]

            if rv["verdict"] == "pass":
                context["step"] = "snapshot_commit"
                need(
                    view.sha == snapshot["rendered_sha256"] and
                    view.snapshot == snapshot["render_snapshot_sha256"] and
                    binding == events[-1]["reviewed_snapshot"],
                    "Stale preview/review receipt",
                    code="SNAPSHOT_BINDING_MISMATCH",
                    module="host.run", path="/snapshots"
                )
                return finish(
                    "accepted_source_exact" if view.mode == "SOURCE_EXACT"
                    else "accepted_candidate", view
                )

            if turn == 1:
                return finish("fallback_unresolved_after_repair", unchanged(src))

            # A source-limited/inactive G0 refusal is not repaired into a guessed
            # partial route. An active candidate with R0=unresolved may enter G1:
            # Generator independently decides whether the concern is source-
            # supported, partially supported, or an over-rejection.
            if rv["verdict"] == "unresolved" and not active:
                return finish("fallback_unresolved", unchanged(src))

            answer = call(
                "generator", "repair",
                {**source_payload, "candidate": candidate_snapshot, "review": rv},
                binding
            )
            context.update(step="generator_repair_validation",
                           role="generator", phase="repair")
            protocol.feedback(src.raw, rv, answer)
            g0 = answer["candidate"]

    except (ContractError, KeyError, TypeError, ValueError, OSError,
            TimeoutError, RuntimeError) as ex:
        diagnostic = ex.to_dict() if isinstance(ex, ContractError) else {
            "code": "TRANSPORT_TIMEOUT" if isinstance(ex, TimeoutError)
                    else "HOST_EXECUTION_FAILED",
            "module": "host.run", "path": "",
            "exception_type": type(ex).__name__, "message": str(ex),
        }
        reviewer_events = [event for event in events if event["role"] == "reviewer"]
        diagnostic.update(context)
        diagnostic["reviewer_status"] = (
            reviewer_events[-1]["call_state"] if reviewer_events else "not_requested"
        )
        diagnostic["interpretation_limit"] = diagnostic.get(
            "interpretation_limit",
            "Technical diagnostic only; no semantic or navigation conclusion is established."
        )
        return finish("fallback_technical", unchanged(src),
                      f"{type(ex).__name__}: {ex}", diagnostic)
    raise RuntimeError("Unreachable workflow state")


def receipt_for_navigation(result, *, instruction_seen, full_prompt_utf8: bytes,
                           input_ids, tokenizer_id, template_id, image_ids,
                           truncated, request_id):
    """Capture the exact released instruction in the existing navigator request."""
    import hashlib
    need(isinstance(instruction_seen, str) and
         text_hash(instruction_seen) == result["instruction_sha256"],
         "Navigation instruction not the released bytes")
    need(isinstance(full_prompt_utf8, bytes) and full_prompt_utf8 and
         isinstance(input_ids, list) and input_ids and
         all(type(token) is int for token in input_ids),
         "Actual native request/IDs required")
    need(all(isinstance(value, str) and value
             for value in (tokenizer_id, template_id, request_id)),
         "Missing native metadata")
    need(isinstance(image_ids, list) and type(truncated) is bool,
         "Missing image/truncation metadata")
    return {
        "request_id": request_id, "task_key": result["task_key"],
        "source_sha256": result["source_sha256"],
        "snapshot_sha256": result["snapshot_sha256"],
        "instruction_sha256": result["instruction_sha256"],
        "full_prompt_sha256": hashlib.sha256(full_prompt_utf8).hexdigest(),
        "tokenizer_id": tokenizer_id, "template_id": template_id,
        "input_ids": input_ids, "input_ids_sha256": obj_hash(input_ids),
        "image_ids_in_order": image_ids, "truncated": truncated,
    }


def command_transport(argv, timeout=300):
    def send(req):
        import subprocess
        try:
            process = subprocess_run(
                argv, input=canonical(req).encode(),
                capture_output=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("existing transport timeout") from exc
        if process.returncode:
            raise RuntimeError(f"existing transport exit {process.returncode}; inspect its own log")
        return json.loads(process.stdout.decode("utf-8"))
    return send


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", required=True)
    parser.add_argument("--pins", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--transport", nargs=argparse.REMAINDER, required=True,
                        help="existing command: JSON request on stdin, reply on stdout; may incur cost")
    args = parser.parse_args()
    target = Path(args.output)
    need(not target.exists(), "Refuse to overwrite existing run")
    step = "source_loading"
    try:
        need(args.transport, "Transport required, no built-in live endpoint",
             code="CONFIGURATION_INVALID", module="host.run", path="/transport")
        source = load_record(args.record)
        step = "configuration_loading"
        pins = json.loads(Path(args.pins).read_bytes())
        result = run_record(source, command_transport(args.transport), pins=pins)
    except (ContractError, ValueError, TypeError, OSError) as exc:
        diagnostic = exc.to_dict() if isinstance(exc, ContractError) else {
            "code": "CONFIGURATION_LOAD_FAILED", "module": "host.run",
            "path": "/pins", "message": type(exc).__name__,
        }
        diagnostic.update(step=step, role=None, phase=None, reviewer_status="not_requested")
        result = {
            "version": VERSION, "disposition": "input_failed",
            "error": str(exc), "diagnostic": diagnostic,
            "calls": [], "navigation_evaluated": False,
            "semantic_correctness_verified": False,
        }
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(result["disposition"], result.get("instruction_sha256", "no-source-identity"))
    sys.exit(2 if result["disposition"] in
             ("fallback_technical", "input_failed") else 0)


if __name__ == "__main__":
    main()
