"""Mechanical contracts for the v1.5.2 G0 -> R0 -> G1 -> R1 protocol.

The Host validates structure, exact evidence, indices, snapshots and verdict
consistency. Semantic entailment remains the responsibility of Generator and
Reviewer; this module is not a third semantic auditor.
"""
import json
import re
from functools import lru_cache
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from shared.identity import need, text_hash
from host.compile import ROOT

LAYERS = (
    "L0_integrity", "L1_source_coverage", "L2_dependencies",
    "L3_stage_checks", "L4_handoffs", "L5_grouping", "L6_route_readback",
)
DIMENSIONS = ("source_fidelity", "closure_handoff", "segmentation_adequacy")
COVERAGE_STATES = ("covered", "omitted", "altered_or_missing", "superseded", "requires_review")
STOP_WORDS = re.compile(r"\b(stop|wait|halt|stand|standing|remain|staying)\b", re.I)


def pointer(parts):
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def check(test, message, *, path="", code="CONTRACT_VIOLATION", **details):
    if "stage_index" in details:
        details["stage_number"] = details["stage_index"] + 1
    need(test, message, code=code, module="host.protocol", path=path, **details)


@lru_cache(maxsize=4)
def schema(path):
    data = json.loads((ROOT / path).read_text(encoding="utf-8"))
    registry = Registry()
    shared = ROOT / "shared" / "template_schemas_v1_5_2"
    for item in shared.glob("*.schema.json"):
        uri = "https://vln.local/shared/template_schemas_v1_5_2/" + item.name
        registry = registry.with_resource(
            uri, Resource.from_contents(json.loads(item.read_text(encoding="utf-8")))
        )
    for rel, uri in (
        ("generator/output.schema.json", "https://vln.local/generator/output.schema.json"),
        ("reviewer/output.schema.json", "https://vln.local/reviewer/output.schema.json"),
        ("generator/repair.schema.json", "https://vln.local/generator/repair.schema.json"),
    ):
        p = ROOT / rel
        if p.is_file():
            registry = registry.with_resource(
                uri, Resource.from_contents(json.loads(p.read_text(encoding="utf-8")))
            )
    return Draft202012Validator(data, registry=registry)


def validate(path, value, *, prefix=""):
    err = next(schema(path).iter_errors(value), None)
    if err is None:
        return
    while len(err.context) == 1:
        err = err.context[0]
    location = list(err.absolute_path)
    if err.validator == "required" and isinstance(err.instance, dict):
        missing = [k for k in err.validator_value if k not in err.instance]
        if missing:
            location.append(missing[0])
    details = {}
    for i, part in enumerate(location[:-1]):
        if part in ("stage_audit", "stage_checks") and isinstance(location[i + 1], int):
            details["stage_index"] = location[i + 1]
    if not isinstance(err.instance, (dict, list)):
        details["actual"] = err.instance
    check(
        False, "Bad " + path + ": " + err.message,
        code="SCHEMA_VALIDATION_FAILED", path=prefix + pointer(location),
        schema_file=path, schema_path=pointer(err.absolute_schema_path),
        validator=err.validator, expected=err.validator_value,
        actual_type=type(err.instance).__name__, **details
    )


def quote(q, text, *, path="", target="source", stage_index=None):
    details = {"target": target, "actual": q, "target_sha256": text_hash(text)}
    if stage_index is not None:
        details["stage_index"] = stage_index
    check(isinstance(q, str) and bool(q.strip()), "Empty or invalid exact quotation",
          path=path, code="EXACT_QUOTE_INVALID", **details)
    check(q in text, "Unverifiable exact quotation",
          path=path, code="EXACT_QUOTE_NOT_FOUND", **details)


def _entry(value, index, path, *, enforce_mode=True):
    mode = value["mode"]
    if enforce_mode:
        allowed = ("episode_start", "explicit_context") if index == 0 else (
            "explicit_context", "inherited_pose", "inherited_entity"
        )
        check(mode in allowed, "Entry mode is inconsistent with the stage index",
              code="ENTRY_MODE_INVALID_FOR_STAGE", path=path + "/mode",
              stage_index=index, actual=mode, expected=list(allowed),
              interpretation_limit="Audit classification only; route correctness is not inferred.")
    if mode == "explicit_context":
        check(bool(value["text"].strip()) and bool(value["candidate_quotes"]),
              "Explicit context requires a nonblank explanation and exact candidate evidence",
              code="EXPLICIT_CONTEXT_EVIDENCE_MISSING", path=path, stage_index=index)
    if mode == "inherited_entity":
        check(bool(value["text"].strip()),
              "Inherited entity must be uniquely identified",
              path=path + "/text", stage_index=index)


def _field_quotes(fields, candidate_stage, path, index):
    for field_name in ("entry", "target", "process", "ending", "conditions"):
        field = fields[field_name]
        for j, q in enumerate(field["candidate_quotes"]):
            quote(q, candidate_stage, path=f"{path}/{field_name}/candidate_quotes/{j}",
                  target="candidate_stage", stage_index=index)
        if field_name in ("process", "ending"):
            check(bool(field["text"]) and bool(field["candidate_quotes"]),
                  f"Stage requires grounded {field_name} in executable English",
                  path=f"{path}/{field_name}", stage_index=index)
        elif field_name in ("target", "conditions"):
            check(
                (field["text"] is None and not field["candidate_quotes"]) or
                (bool(field["text"]) and bool(field["candidate_quotes"])),
                f"{field_name} text and evidence must be jointly present or absent",
                path=f"{path}/{field_name}", stage_index=index
            )


def _stop_scope(ending, index, stage_count, path):
    scope = ending["stop_scope"]
    if scope == "intermediate":
        check(index < stage_count - 1,
              "intermediate stop_scope is only valid before a later stage", path=path)
        check(bool(STOP_WORDS.search(" ".join(ending["candidate_quotes"]))),
              "intermediate stop_scope requires quoted stationary/stop evidence", path=path)
    elif scope == "terminal":
        check(index == stage_count - 1,
              "terminal stop_scope is only valid on the final stage", path=path)
        check(bool(STOP_WORDS.search(" ".join(ending["candidate_quotes"]))),
              "terminal stop_scope requires quoted stationary/stop evidence", path=path)


def _check_handoff(h, parts, path, *, accepted):
    left, right = h["from_subtask_index"], h["to_subtask_index"]
    check(right == left + 1 and 0 <= left < len(parts) and right < len(parts),
          "Handoff must link adjacent in-range stages", path=path,
          actual={"from_subtask_index": left, "to_subtask_index": right})
    check(bool(h["preceding_exit"]["text"].strip()) and bool(h["next_entry"]["text"].strip()),
          "Handoff must describe the actual preceding exit and next required entry", path=path)
    quote(h["preceding_exit"]["candidate_quote"], parts[left],
          path=path + "/preceding_exit/candidate_quote",
          target="candidate_stage", stage_index=left)
    quote(h["next_entry"]["candidate_quote"], parts[right],
          path=path + "/next_entry/candidate_quote",
          target="candidate_stage", stage_index=right)
    if accepted:
        check(h["status"] == "supported",
              "An accepted candidate cannot contain a gap/source-limited handoff",
              path=path + "/status")


def generator(source, candidate, *, prefix=""):
    validate("generator/output.schema.json", candidate, prefix=prefix)
    status, parts = candidate["status"], candidate["subtasks"]
    if status == "needs_review":
        check(not parts and not candidate["stage_audit"] and not candidate["handoffs"],
              "needs_review must not publish partial subtasks, stage audits or handoffs",
              path=prefix + "/status")
        check(bool(candidate["issues"]),
              "needs_review requires at least one source-grounded issue",
              path=prefix + "/issues")
        for i, item in enumerate(candidate["issues"]):
            quote(item["source_quote"], source, path=f"{prefix}/issues/{i}/source_quote")
        return

    n = len(parts)
    check(n > 0, "ok candidate requires at least one subtask", path=prefix + "/subtasks")
    check(len(candidate["stage_audit"]) == n,
          "Generator must provide exactly one stage audit per subtask",
          path=prefix + "/stage_audit")
    check(len(candidate["handoffs"]) == max(0, n - 1),
          "Generator must provide exactly one handoff per adjacent pair",
          path=prefix + "/handoffs")
    for i, text in enumerate(parts):
        check(isinstance(text, str) and bool(text.strip()), "Blank subtask",
              path=f"{prefix}/subtasks/{i}", stage_index=i)
        audit = candidate["stage_audit"][i]
        loc = f"{prefix}/stage_audit/{i}"
        check(audit["subtask_index"] == i, "Stage audit index mismatch",
              path=loc + "/subtask_index", stage_index=i)
        for j, q in enumerate(audit["source_quotes"]):
            quote(q, source, path=f"{loc}/source_quotes/{j}", stage_index=i)
        _field_quotes(audit, text, loc, i)
        _entry(audit["entry"], i, loc + "/entry")
        _stop_scope(audit["ending"], i, n, loc + "/ending/stop_scope")
        check(audit["ending"]["kind"] != "unspecified",
              "An accepted stage needs a supported ending basis",
              path=loc + "/ending/kind", stage_index=i)
        if audit["ending"]["kind"] == "terminal_goal_directive":
            wording = audit["ending"]["text"].casefold()
            check(i == n - 1 and (re.search(r"(?:does not (?:specify|state)|do not invent|no further)\b[^.;]*\b(?:arrival|stop|stopping)\b", wording) or any(term in wording for term in (
                "no arrival", "arrival is not", "not asserted", "no explicit",
                "unspecified", "not specified", "no stop", "stop is not"
            ))), "terminal_goal_directive must be final-only and disclaim arrival/STOP",
                  path=loc + "/ending", stage_index=i)
    for j, handoff in enumerate(candidate["handoffs"]):
        _check_handoff(handoff, parts, f"{prefix}/handoffs/{j}", accepted=True)


def feedback(source, review, answer):
    validate("generator/repair.schema.json", answer)
    expected = list(range(len(review["findings"])))
    actual = [row["finding_index"] for row in answer["responses"]]
    check(actual == expected,
          "G1 must answer every R0 finding exactly once and in original order",
          path="/responses", expected=expected, actual=actual)
    for i, row in enumerate(answer["responses"]):
        for j, q in enumerate(row["source_quotes"]):
            quote(q, source, path=f"/responses/{i}/source_quotes/{j}")
    generator(source, answer["candidate"], prefix="/candidate")


def _validate_prior_context(source, prior_review, prior_candidate, prior_rendered):
    check(isinstance(prior_review, dict) and isinstance(prior_candidate, dict),
          "R1 requires the frozen R0 review and old candidate", path="/prior_review")
    check(isinstance(prior_rendered, str),
          "R1 requires the exact R0 rendered instruction", path="/prior_rendered_instruction")
    old_parts = prior_candidate.get("subtasks", [])
    for i, stage_text in enumerate(old_parts):
        check(stage_text in prior_rendered,
              "R0 rendered snapshot does not contain its frozen candidate stage",
              path=f"/prior_rendered_instruction/stage/{i}", stage_index=i)
    for i, finding in enumerate(prior_review.get("findings", [])):
        quote(finding["source_quote"], source, path=f"/prior_review/findings/{i}/source_quote")
        for j, ev in enumerate(finding.get("candidate_evidence", [])):
            idx = ev["subtask_index"]
            check(0 <= idx < len(old_parts),
                  "R0 evidence stage index is out of range",
                  path=f"/prior_review/findings/{i}/candidate_evidence/{j}/subtask_index",
                  actual=idx)
            quote(ev["quote"], old_parts[idx],
                  path=f"/prior_review/findings/{i}/candidate_evidence/{j}/quote",
                  target="prior_candidate_stage", stage_index=idx)


def reviewer(source, candidate, review, *, rendered_instruction=None,
             prior_review=None, prior_candidate=None, prior_rendered_instruction=None):
    validate("reviewer/output.schema.json", review)
    check(candidate.get("status") in ("ok", "needs_review"),
          "Reviewer candidate has an unknown Generator status", path="/candidate/status")
    parts, verdict = candidate["subtasks"], review["verdict"]
    n = len(parts)
    if candidate["status"] == "needs_review":
        check(not parts, "needs_review candidate cannot contain partial stages", path="/candidate/subtasks")
    else:
        check(bool(parts), "ok candidate must contain at least one stage", path="/candidate/subtasks")
    axes = review["dimensions"]
    is_recheck = prior_review is not None

    if rendered_instruction is not None:
        check(isinstance(rendered_instruction, str),
              "Rendered instruction must be a string", path="/rendered_instruction")
        for i, stage_text in enumerate(parts):
            check(stage_text in rendered_instruction,
                  "Frozen rendered instruction does not contain the reviewed candidate stage",
                  code="RENDERED_CANDIDATE_MISMATCH", path="/rendered_instruction",
                  stage_index=i,
                  interpretation_limit="Host integrity failure; do not ask Generator to rewrite route text.")

    if is_recheck:
        _validate_prior_context(source, prior_review, prior_candidate, prior_rendered_instruction)
        expected_prior = list(range(len(prior_review["findings"])))
        actual_prior = [x["finding_index"] for x in review["prior_finding_reviews"]]
        check(actual_prior == expected_prior,
              "R1 must disposition every prior R0 finding exactly once and in order",
              path="/prior_finding_reviews", expected=expected_prior, actual=actual_prior)
        for i, item in enumerate(review["prior_finding_reviews"]):
            for j, ev in enumerate(item["candidate_evidence"]):
                idx = ev["subtask_index"]
                check(0 <= idx < n,
                      "R1 prior-finding evidence index is out of range",
                      path=f"/prior_finding_reviews/{i}/candidate_evidence/{j}/subtask_index",
                      actual=idx)
                quote(ev["quote"], parts[idx],
                      path=f"/prior_finding_reviews/{i}/candidate_evidence/{j}/quote",
                      target="candidate_stage", stage_index=idx)
        for i, item in enumerate(review["prior_finding_reviews"]):
            if item["status"] in ("resolved", "partially_resolved"):
                check(bool(item["candidate_evidence"]),
                      "Resolved/partially resolved prior finding requires evidence from the new candidate",
                      path=f"/prior_finding_reviews/{i}/candidate_evidence")
        if verdict == "pass":
            check(all(x["status"] == "resolved" for x in review["prior_finding_reviews"]),
                  "R1 cannot pass while any prior blocking finding remains unresolved",
                  path="/prior_finding_reviews")
    else:
        check(not review["prior_finding_reviews"],
              "R0 must return an empty prior_finding_reviews array",
              path="/prior_finding_reviews")

    check([x["layer"] for x in review["layer_checks"]] == list(LAYERS),
          "Reviewer must complete L0-L6 exactly once and in order", path="/layer_checks")
    check([x["subtask_index"] for x in review["stage_checks"]] == list(range(n)),
          "Reviewer stage checks must cover every actual candidate stage exactly once",
          path="/stage_checks")
    check([(x["from_subtask_index"], x["to_subtask_index"]) for x in review["handoffs"]] ==
          [(i, i + 1) for i in range(max(0, n - 1))],
          "Reviewer must check every adjacent handoff exactly once", path="/handoffs")

    coverage = review["source_coverage"]
    ids = [x["requirement_id"] for x in coverage]
    check(len(ids) == len(set(ids)), "Source coverage requirement IDs must be unique",
          path="/source_coverage")
    idset = set(ids)
    for j, row in enumerate(coverage):
        loc = f"/source_coverage/{j}"
        quote(row["source_quote"], source, path=loc + "/source_quote")
        check(row["status"] in COVERAGE_STATES, "Unknown source coverage status",
              path=loc + "/status")
        for k, ev in enumerate(row["candidate_evidence"]):
            idx = ev["subtask_index"]
            check(0 <= idx < n, "Coverage evidence stage index is out of range",
                  path=f"{loc}/candidate_evidence/{k}/subtask_index", actual=idx)
            quote(ev["quote"], parts[idx], path=f"{loc}/candidate_evidence/{k}/quote",
                  target="candidate_stage", stage_index=idx)
        if row["status"] in ("covered", "superseded"):
            check(bool(row["candidate_evidence"]),
                  "Covered/superseded source requirement needs candidate evidence",
                  path=loc + "/candidate_evidence")
        if row["status"] in ("omitted", "altered_or_missing"):
            check(any(row["requirement_id"] in f["source_requirement_ids"]
                      for f in review["findings"]),
                  "Omitted/altered source requirement must have a blocking finding",
                  path=loc + "/status")
        if row["status"] == "requires_review":
            check(any(
                row["requirement_id"] in f["source_requirement_ids"] and
                f["code"] == "SOURCE_AMBIGUITY"
                for f in review["findings"]
            ), "A requires_review source row must map to a source-ambiguity finding",
                 path=loc + "/status")

    for i, stage_check in enumerate(review["stage_checks"]):
        loc = f"/stage_checks/{i}"
        check(all(rid in idset for rid in stage_check["source_requirement_ids"]),
              "Stage references an unknown source requirement ID",
              path=loc + "/source_requirement_ids", stage_index=i)
        for j, q in enumerate(stage_check["source_quotes"]):
            quote(q, source, path=f"{loc}/source_quotes/{j}", stage_index=i)
        _field_quotes(stage_check, parts[i], loc, i)
        _entry(stage_check["entry"], i, loc + "/entry", enforce_mode=(verdict == "pass"))
        _stop_scope(stage_check["ending"], i, n, loc + "/ending/stop_scope")
        if stage_check["status"] in ("gap", "source_limited"):
            check(any(
                i in finding["affected_subtask_indices"] and
                bool(set(stage_check["source_requirement_ids"]) & set(finding["source_requirement_ids"]))
                for finding in review["findings"]
            ), "A gap/source-limited stage requires a matching evidence-backed finding",
                 path=loc + "/status", stage_index=i)
        if verdict == "pass":
            check(stage_check["status"] == "supported" and
                  stage_check["entry"]["mode"] not in ("missing", "source_unspecified") and
                  stage_check["ending"]["kind"] != "unspecified",
                  "PASS contains an unsupported stage", path=loc, stage_index=i)

    for j, handoff in enumerate(review["handoffs"]):
        loc = f"/handoffs/{j}"
        check(all(rid in idset for rid in handoff["source_requirement_ids"]),
              "Handoff references an unknown source requirement ID",
              path=loc + "/source_requirement_ids")
        _check_handoff(handoff, parts, loc, accepted=(verdict == "pass"))
        if handoff["status"] in ("gap", "source_limited"):
            adjacent = {handoff["from_subtask_index"], handoff["to_subtask_index"]}
            required_ids = set(handoff["source_requirement_ids"])
            check(any(
                bool(adjacent & set(finding["affected_subtask_indices"])) and
                bool(required_ids & set(finding["source_requirement_ids"])) and
                ("closure_handoff" == finding["dimension"] or
                 "closure_handoff" in finding["related_dimensions"] or
                 finding["failed_layer"] == "L4_handoffs")
                for finding in review["findings"]
            ), "A gap/source-limited handoff requires a matching cross-stage finding",
                 path=loc + "/status")

    for j, finding in enumerate(review["findings"]):
        loc = f"/findings/{j}"
        quote(finding["source_quote"], source, path=loc + "/source_quote")
        check(all(rid in idset for rid in finding["source_requirement_ids"]),
              "Finding references an unknown source requirement ID",
              path=loc + "/source_requirement_ids")
        affected = finding["affected_subtask_indices"]
        check(all(0 <= idx < n for idx in affected),
              "Finding affected-stage index is out of range",
              path=loc + "/affected_subtask_indices")
        if finding["code"] != "SOURCE_AMBIGUITY":
            check(bool(affected),
                  "A candidate defect finding must identify at least one affected stage",
                  path=loc + "/affected_subtask_indices")
        if not finding["candidate_evidence"]:
            check(finding["code"] in (
                "OMISSION", "MISSING_ENTRY_ANCHOR", "SOURCE_AMBIGUITY", "OVERREJECTION"
            ), "Empty candidate evidence is only valid for a genuine absence or source-level uncertainty",
                 path=loc + "/candidate_evidence")
        repair_indices = finding["repair"]["affected_subtask_indices"]
        check(all(idx in affected for idx in repair_indices),
              "Repair target indices must be a subset of affected stage indices",
              path=loc + "/repair/affected_subtask_indices")
        for k, ev in enumerate(finding["candidate_evidence"]):
            idx = ev["subtask_index"]
            check(0 <= idx < n, "Finding evidence stage index is out of range",
                  path=f"{loc}/candidate_evidence/{k}/subtask_index")
            # Evidence may span stages outside the local repair target; this is
            # required for genuine previous-exit / next-entry diagnoses.
            quote(ev["quote"], parts[idx], path=f"{loc}/candidate_evidence/{k}/quote",
                  target="candidate_stage", stage_index=idx)
        layer = review["layer_checks"][LAYERS.index(finding["failed_layer"])]
        check(layer["status"] in ("issue", "source_limited") and
              j in layer["finding_indices"],
              "Finding must be indexed by its failed layer", path=loc + "/failed_layer")

    for j, layer in enumerate(review["layer_checks"]):
        check(all(0 <= idx < len(review["findings"]) for idx in layer["finding_indices"]),
              "Layer references an unknown finding",
              path=f"/layer_checks/{j}/finding_indices")
        if layer["status"] in ("issue", "source_limited"):
            check(bool(layer["finding_indices"]),
                  "Issue/source-limited layer requires a supporting finding",
                  path=f"/layer_checks/{j}/finding_indices")

    for dimension in DIMENSIONS:
        if axes[dimension] in ("issue", "source_limited"):
            check(any(f["dimension"] == dimension or dimension in f["related_dimensions"]
                      for f in review["findings"]),
                  "Dimension diagnosis has no supporting finding",
                  path="/dimensions/" + dimension)

    if verdict == "pass":
        check(candidate["status"] == "ok" and not review["findings"] and
              all(axes[d] == "pass" for d in DIMENSIONS),
              "PASS requires an active candidate, no findings and all dimensions pass",
              path="/verdict")
        check(all(x["status"] in ("covered", "superseded") for x in coverage),
              "PASS cannot contain omitted, altered or unresolved source requirements",
              path="/source_coverage")
        check(all(x["status"] in ("pass", "not_applicable") for x in review["layer_checks"]),
              "PASS cannot contain an issue/source-limited layer", path="/layer_checks")
    elif verdict == "revise":
        prior_blockers = is_recheck and any(
            x["status"] != "resolved" for x in review["prior_finding_reviews"]
        )
        check(bool(review["findings"]) or prior_blockers,
              "REVISE requires a current or unresolved prior blocking finding",
              path="/verdict")
        check(any(axes[d] == "issue" for d in DIMENSIONS),
              "REVISE requires at least one repairable dimension issue",
              path="/dimensions")
    else:
        check(any(axes[d] == "source_limited" for d in DIMENSIONS),
              "UNRESOLVED requires a route-critical source limitation",
              path="/dimensions")
        check(any(f["code"] == "SOURCE_AMBIGUITY" and f["evidence_level"] in ("S1", "S2")
                  for f in review["findings"]),
              "UNRESOLVED requires a source-ambiguity finding", path="/findings")
        check(candidate["status"] == "ok" or not parts,
              "UNRESOLVED must not publish a guessed partial route", path="/verdict")
