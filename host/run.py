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
import shlex
from pathlib import Path

from adapter.source import Source, load_record
from renderer.freeze import freeze, unchanged
from host.compile import compile_prompt, core_library
from host.template_selector import select_examples, selection_evidence, library, DEFAULT_EXAMPLES
from host import protocol
from shared.identity import need, canonical, obj_hash, text_hash, ContractError

Transport = Callable[[dict], dict]
VERSION = "current"


def dataset_rules_metadata(profile):
    """Immutable per-task record of common and dataset-specific rule bytes."""
    paths = [Path(__file__).resolve().parents[1]/"shared/semantic_contract.md"]
    version = "shared-semantic-contract"
    if profile == "rxr-en-us":
        root = Path(__file__).resolve().parents[1]
        paths.extend([
            root/"shared/dataset_rules/rxr_en_us.md",
            root/"generator/dataset_rules/rxr_en_us.md",
            root/"reviewer/dataset_rules/rxr_en_us.md",
        ])
        version = "rxr-en-us-profile"
    elif profile == "r2r-en":
        root = Path(__file__).resolve().parents[1]
        paths.extend([
            root/"shared/dataset_rules/r2r_en.md",
            root/"shared/dataset_rules/r2r_fragments.json",
            root/"generator/dataset_rules/r2r_en.md",
            root/"reviewer/dataset_rules/r2r_en.md",
        ])
        version = "r2r-en-profile"
    material = "\n".join(
        f"## {path.relative_to(Path(__file__).resolve().parents[1]).as_posix()}\n{path.read_text(encoding='utf-8')}"
        for path in paths
    )
    return {
        "version": version,
        "sha256": text_hash(material),
        "files": [path.relative_to(Path(__file__).resolve().parents[1]).as_posix() for path in paths],
    }



def prompt_components_metadata(role, phase, profile):
    """Freeze all source files that contribute to this role's compiled prompt."""
    root = Path(__file__).resolve().parents[1]
    # Include compiler/selector implementation so the frozen task record identifies
    # not only prompt text assets but also the code that assembles and selects them.
    paths = [
        root/role/"prompt.md",
        root/"shared/semantic_contract.md",
        root/"host/compile.py",
        root/"host/template_selector.py",
    ]
    if role == "reviewer":
        paths.append(root/"reviewer/checklist.md")
    if role == "generator" and phase == "repair":
        paths.extend([root/"generator/repair.md", root/"generator/repair_examples.json"])
    schema_path = root/role/("repair.schema.json" if role == "generator" and phase == "repair"
                            else "output.schema.json")
    paths.append(schema_path)
    if profile == "rxr-en-us":
        paths.extend([
            root/"shared/dataset_rules/rxr_en_us.md",
            root/role/"dataset_rules/rxr_en_us.md",
        ])
    elif profile == "r2r-en":
        paths.extend([
            root/"shared/dataset_rules/r2r_en.md",
            root/role/"dataset_rules/r2r_en.md",
        ])
    files = []
    for path in paths:
        data = path.read_bytes()
        files.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": text_hash(data.decode("utf-8")),
        })
    return {"role": role, "profile": profile, "files": files,
            "sha256": obj_hash(files)}


def template_bundle_metadata(role, profile, selected_ids):
    """Hash the fixed core and selected dynamic templates for task-level freezing."""
    fixed = core_library(role, profile)
    dynamic_by_id = {row["template_id"]: row for row in library(role, profile)}
    missing = [template_id for template_id in selected_ids if template_id not in dynamic_by_id]
    need(not missing, f"Selected template IDs disappeared: {missing}",
         code="TEMPLATE_BUNDLE_INVALID", module="host.run", path="/selected_example_ids")
    bundle = {
        "fixed_core": fixed,
        "dynamic": [dynamic_by_id[template_id] for template_id in selected_ids],
    }
    return {
        "fixed_core_ids": [row["template_id"] for row in fixed],
        "dynamic_ids": list(selected_ids),
        "sha256": text_hash(canonical(bundle)),
    }

def request(role, phase, payload, pin, profile, selected_ids):
    text, active_schema = compile_prompt(
        role, phase, profile=profile, selected_ids=selected_ids,
        original_instruction=payload.get("original_instruction")
    )
    rules = dataset_rules_metadata(profile)
    bundle = template_bundle_metadata(role, profile, selected_ids)
    return {
        "role": role,
        "phase": phase,
        "profile": profile,
        "dataset_rules": rules,
        "prompt_components": prompt_components_metadata(role, phase, profile),
        "template_bundle": bundle,
        "fixed_core_template_ids": bundle["fixed_core_ids"],
        "model": pin["model"],
        "effort": pin["effort"],
        "messages": [
            {"role": "system", "content": text},
            {"role": "user", "content": canonical(payload)},
        ],
        "output_schema": active_schema,
        "selected_example_ids": list(selected_ids),
    }


def run_record(src: Source, transport: Transport, *, pins: dict | None = None,
               separator="\n", example_count=DEFAULT_EXAMPLES,
               selection_mode="adaptive"):
    """Run at most four semantic calls plus at most two technical corrections per role; preserve exact source fallback on every failure."""
    events, snapshots = [], []
    rules_frozen = None
    prompt_components_frozen = {}
    template_bundles = {}
    fixed_core_ids = {role: [] for role in ("generator", "reviewer")}
    selections = {role: [] for role in ("generator", "reviewer")}
    context = {"step": "configuration_validation", "role": None, "phase": None}

    def call(role, phase, payload, candidate_digest=None):
        context.update(step="request_construction", role=role, phase=phase)
        req = request(role, phase, payload, pins[role], src.profile, selections[role])
        need(req["template_bundle"] == template_bundles[role],
             "Selected template content changed during the task",
             code="TEMPLATE_BUNDLE_MUTATED", module="host.run", path="/template_bundle")
        need(req["dataset_rules"] == rules_frozen,
             "Dataset-specific rule bundle changed during the task",
             code="RULE_BUNDLE_MUTATED", module="host.run", path="/dataset_rules")
        need(req["prompt_components"] == prompt_components_frozen[role][phase],
             "Compiled prompt source components changed during the task",
             code="PROMPT_COMPONENTS_MUTATED", module="host.run", path="/prompt_components")
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
            event["call_state"] = "transport_returned"
        except Exception as transport_error:
            # A timeout/connection loss does not prove the provider did not
            # execute. First query the same invocation by its deterministic
            # request hash. Never submit a second generation request.
            event["call_state"] = "transport_failed_execution_unknown"
            event["transport_error"] = f"{type(transport_error).__name__}: {transport_error}"
            recover = getattr(transport, "recover", None)
            if not callable(recover):
                event["recovery_state"] = "unavailable"
                raise
            context["step"] = "transport_recovery_lookup"
            event["recovery_state"] = "lookup_started"
            try:
                recovered = recover(req)
            except Exception as recovery_error:
                event["recovery_state"] = "lookup_failed"
                event["recovery_error"] = f"{type(recovery_error).__name__}: {recovery_error}"
                raise transport_error
            if recovered is None:
                event["recovery_state"] = "not_found"
                raise transport_error
            reply = recovered
            event["recovery_state"] = "original_call_recovered"
            event["call_state"] = "original_call_recovered"
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
                "input_tokens", "output_tokens", "parse_state", "raw_sha256"
            )
        }
        event["call_state"] = "receipt_received"
        valid = (
            receipt.get("model") == req["model"] and
            receipt.get("effort") == req["effort"] and
            bool(receipt.get("request_id")) and
            (receipt.get("provider_request_sha256") is None or
             receipt.get("provider_request_sha256") == obj_hash(req))
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

    retrieval_evidence = {}
    reviewer_rows_by_id = {}
    technical_by_role = {"generator": 0, "reviewer": 0}
    quote_corrections = 0
    semantic_repairs = 0

    def review_feedback(error, review):
        details = error.to_dict()
        if details.get("path", "").startswith("/source_coverage/") and isinstance(review, dict):
            # After schema validation the complete cross-reference table can be
            # checked in one correction, instead of consuming a turn per row.
            rows = review.get("source_coverage")
            findings = review.get("findings")
            if isinstance(rows, list) and isinstance(findings, list) and error.details.get("code") == "CONTRACT_VIOLATION":
                details["coverage_links"] = [
                    {"id": row["requirement_id"], "status": row["status"],
                     "findings": [j for j, finding in enumerate(findings)
                                  if row["requirement_id"] in finding["source_requirement_ids"]]}
                    for row in rows
                ]
        return details

    def validated_call(role, phase, payload, validator, binding=None):
        nonlocal quote_corrections
        request_payload = payload
        while True:
            output = call(role, phase, request_payload, binding)
            step = {"initial": "generator_validation", "repair": "generator_repair_validation"}.get(phase, "reviewer_validation")
            context.update(step=step, role=role, phase=phase)
            try:
                validator(output)
                events[-1]["validation_state"] = "validated"
                return output
            except ContractError as exc:
                code = exc.details.get("code")
                quote_error = code in ("EXACT_QUOTE_NOT_FOUND", "EXACT_QUOTE_INVALID")
                structural = (code == "SCHEMA_VALIDATION_FAILED" and
                              exc.details.get("validator") in ("required", "type", "additionalProperties"))
                events[-1]["validation_error"] = exc.to_dict()
                events[-1]["validation_state"] = "invalid"
                path = exc.details.get("path", "")
                reviewer_owned = (role == "reviewer" and exc.details.get("module") == "host.protocol"
                                  and code != "RENDERED_CANDIDATE_MISMATCH"
                                  and not any(path == prefix or path.startswith(prefix + "/") for prefix in
                                              ("/candidate", "/rendered_instruction", "/prior_review",
                                               "/prior_candidate", "/prior_rendered_instruction")))
                if technical_by_role[role] >= 2 or not (reviewer_owned or (role == "generator" and (quote_error or structural))):
                    raise
                technical_by_role[role] += 1
                quote_corrections += int(quote_error)
                request_payload = {
                    **payload, "previous_output": output, "technical_feedback": exc.to_dict(),
                    "technical_attempt": technical_by_role[role],
                    "instruction": "Correct the reported field against its governing schema and evidence. "
                                   "Copy source quotations from the immutable original and candidate quotations "
                                   "from their own stage. If the stage itself has a transcription mistake, "
                                   "correct it from source and refresh its evidence. Preserve unrelated content. "
                                   "Return the complete active response object."
                }
                if role == "reviewer":
                    request_payload["technical_feedback"] = review_feedback(exc, output)
                    request_payload["instruction"] = (
                        "Correct your review object at the reported path using its schema and the exact "
                        "frozen source and candidate. Do not edit either text. Cite literal substrings "
                        "of the indicated stage/source. Keep grounded objections and reassess verdict "
                        "consistency; do not force pass. Check all rows for the same defect. For an empty plan, "
                        "link ambiguity findings only to genuinely ambiguous requirements. Keep clear context "
                        "out of the affected requirement IDs and use not_assessed_no_candidate where applicable. "
                        "Return the entire corrected review."
                    )

    def finish(disposition, view, detail=None, diagnostic=None):
        return {
            "version": VERSION,
            "quote_corrections": quote_corrections,
            "technical_corrections": sum(technical_by_role.values()),
            "technical_by_role": dict(technical_by_role),
            "semantic_repairs": semantic_repairs,
            "task_key": src.key,
            "source_identity": src.identity(),
            "navigation_eligible": disposition not in ("fallback_technical", "input_failed"),
            "profile": src.profile,
            "source_sha256": src.sha,
            "dataset_rules": rules_frozen,
            "prompt_components": prompt_components_frozen,
            "template_bundles": template_bundles,
            "fixed_core_template_ids": {
                role: list(ids) for role, ids in fixed_core_ids.items()
            },
            "example_selection": {
                "mode": selection_mode,
                "fixed_core_generator_ids": list(fixed_core_ids["generator"]),
                "fixed_core_reviewer_ids": list(fixed_core_ids["reviewer"]),
                "retrieval_evidence": retrieval_evidence,
                "configured_example_count": example_count,
                "reviewer_pair_count": sum(
                    1 for template_id in selections["reviewer"]
                    if reviewer_rows_by_id.get(template_id, {}).get("pair_id")
                ),
                "reviewer_diagnostic_ids": [
                    template_id for template_id in selections["reviewer"]
                    if not reviewer_rows_by_id.get(template_id, {}).get("pair_id")
                ],
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
        if pins is None:
            pins = json.loads(Path(__file__).with_name("role-pins.json").read_bytes())
        need(
            isinstance(pins, dict) and set(pins) == {"generator", "reviewer"} and
            all(isinstance(v, dict) and
                all(isinstance(v.get(k), str) and v[k] for k in ("model", "effort"))
                for v in pins.values()),
            "Explicit model/effort pins required for both roles",
            code="CONFIGURATION_INVALID", module="host.run", path="/pins"
        )
        context["step"] = "example_selection"
        rules_frozen = dataset_rules_metadata(src.profile)
        prompt_components_frozen = {
            "generator": {
                phase: prompt_components_metadata("generator", phase, src.profile)
                for phase in ("initial", "repair")
            },
            "reviewer": {
                phase: prompt_components_metadata("reviewer", phase, src.profile)
                for phase in ("review", "recheck")
            },
        }
        # Resolve and validate fixed core once before any model invocation.
        # finish() reports cached IDs and remains safe if core loading fails.
        fixed_core_ids = {
            role: [row["template_id"] for row in core_library(role, src.profile)]
            for role in ("generator", "reviewer")
        }
        selections = {
            role: select_examples(role, src.profile, src.raw,
                                  count=example_count, mode=selection_mode)
            for role in ("generator", "reviewer")
        }
        retrieval_evidence = {role: selection_evidence(role, src.profile, src.raw, ids)
                              for role, ids in selections.items()}
        reviewer_rows_by_id = {
            row["template_id"]: row for row in library("reviewer", src.profile)
        }
        template_bundles = {
            role: template_bundle_metadata(role, src.profile, ids)
            for role, ids in selections.items()
        }
        source_payload = {"original_instruction": src.raw}
        g0 = validated_call("generator", "initial", source_payload, lambda out: protocol.generator(src.raw, out))

        r0_review = None
        r0_candidate = None
        r0_rendered = None

        for turn in range(2):
            phase_g = "initial" if turn == 0 else "repair"
            context.update(step="generator_validation", role="generator", phase=phase_g)
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
            def validate_review(output):
                protocol.reviewer(
                    src.raw, candidate, output, rendered_instruction=snapshot["rendered_instruction"],
                    prior_review=r0_review if turn else None,
                    prior_candidate=r0_candidate if turn else None,
                    prior_rendered_instruction=r0_rendered if turn else None,
                )

            rv = validated_call("reviewer", review_phase, reviewer_payload, validate_review, binding)

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

            semantic_repairs += 1
            answer = validated_call(
                "generator", "repair", {**source_payload, "candidate": candidate_snapshot, "review": rv},
                lambda out: protocol.feedback(src.raw, rv, out), binding
            )
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
    need(result.get("navigation_eligible", True), "Cannot bind an unconfirmed invocation to navigation",
         code="UNCONFIRMED_RESULT", module="host.run", path="/navigation_eligible")
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


def command_transport(argv, timeout=300, recovery_argv=None):
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

    if recovery_argv:
        def recover(req):
            import subprocess
            payload = {
                "operation": "lookup_original_request",
                "request_sha256": obj_hash(req),
                "request": req,
            }
            try:
                process = subprocess_run(
                    recovery_argv, input=canonical(payload).encode(),
                    capture_output=True, timeout=timeout, check=False
                )
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError("original-request recovery lookup timeout") from exc
            if process.returncode:
                raise RuntimeError(
                    f"recovery lookup exit {process.returncode}; no generation retry was attempted"
                )
            result = json.loads(process.stdout.decode("utf-8"))
            need(isinstance(result, dict) and type(result.get("found")) is bool,
                 "Malformed recovery lookup result",
                 code="RECOVERY_REPLY_INVALID", module="host.run", path="/recovery/found")
            if not result["found"]:
                return None
            need(isinstance(result.get("reply"), dict),
                 "Recovery result must contain the original transport reply",
                 code="RECOVERY_REPLY_INVALID", module="host.run", path="/recovery/reply")
            return result["reply"]
        send.recover = recover
    return send


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", required=True)
    parser.add_argument("--pins", help="override the packaged host/role-pins.json")
    parser.add_argument("--output", required=True)
    parser.add_argument("--recover-command", default=None,
                        help="optional lookup-only command; receives {operation, request_sha256, request} and returns {found:false} or {found:true, reply:<original reply>}")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cli-ledger", help="durable Codex CLI journal directory")
    group.add_argument("--transport", nargs=argparse.REMAINDER,
                        help="existing command: JSON request on stdin, reply on stdout; may incur cost")
    args = parser.parse_args()
    target = Path(args.output)
    need(not target.exists(), "Refuse to overwrite existing run")
    step = "source_loading"
    try:
        need(args.cli_ledger or args.transport, "Transport required, no built-in live endpoint",
             code="CONFIGURATION_INVALID", module="host.run", path="/transport")
        source = load_record(args.record)
        step = "configuration_loading"
        pins = json.loads(Path(args.pins).read_bytes()) if args.pins else None
        recovery_argv = shlex.split(args.recover_command) if args.recover_command else None
        if args.cli_ledger:
            from host.cli_journal import JournalCLI
            transport = JournalCLI(args.cli_ledger, source.key)
        else:
            transport = command_transport(args.transport, recovery_argv=recovery_argv)
        result = run_record(source, transport, pins=pins)
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
