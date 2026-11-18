"""Compile v5 common contracts and v6 profile-specific teaching material separately from active schemas."""
from __future__ import annotations
import json
import re
from pathlib import Path
from shared.identity import canonical,text_hash
from host.template_selector import select_examples,library,DEFAULT_EXAMPLES,PROFILES,write_type_index
ROOT=Path(__file__).resolve().parents[1]

def wire_schema(path):
    """Resolve the package's finite local schema references for standalone requests."""
    from urllib.parse import urljoin, urlsplit

    def expand(node, base, ancestors):
        if isinstance(node, list):
            return [expand(item, base, ancestors) for item in node]
        if not isinstance(node, dict):
            return node
        base = urljoin(base, node.get('$id', ''))
        result = {key: expand(value, base, ancestors) for key, value in node.items()
                  if key not in ('$ref', '$id', '$defs')}
        if '$ref' in node:
            uri = urljoin(base, node['$ref'])
            address = urlsplit(uri)
            if address.scheme != 'https' or address.netloc != 'vln.local' or uri in ancestors:
                raise ValueError(f'Unsupported schema reference: {uri}')
            target = (ROOT/address.path.lstrip('/')).resolve()
            target.relative_to(ROOT)
            value = json.loads(target.read_bytes())
            for segment in address.fragment.split('/')[1:]:
                value = value[segment.replace('~1', '/').replace('~0', '~')]
            resolved = expand(value, uri.partition('#')[0], ancestors | {uri})
            return {'allOf': [resolved], **result} if result else resolved
        return result

    uri = 'https://vln.local/' + path.relative_to(ROOT).as_posix()
    return expand(json.loads(path.read_bytes()), uri, {uri})

def core_library(role, profile):
    """Load and validate a dataset's immutable ten-example Core in explicit order."""
    if role not in ('generator', 'reviewer'):
        raise ValueError('Unknown semantic role')
    if profile not in ('r2r-en', 'rxr-en-us'):
        raise ValueError('Unsupported dataset profile')
    if profile == 'rxr-en-us':
        dataset, prefix, language = 'RxR', 'RXR', 'en-US'
    else:
        dataset, prefix, language = 'R2R', 'R2R', 'en'
    folder = ROOT/role/'templates'/dataset/'core'
    if not folder.is_dir():
        raise ValueError(f'{dataset} {role} fixed core directory is missing: {folder}')
    files = sorted(folder.glob('*.json'))
    rows = [json.loads(path.read_bytes()) for path in files]
    if len(rows) != 10:
        raise ValueError(f'{dataset} {role} fixed core must contain exactly 10 templates; found {len(rows)}')
    expected_ids = ([f'{prefix}-CORE-G{i:02d}' for i in range(1, 11)]
                    if role == 'generator' else
                    [f'{prefix}-CORE-R{i:02d}' for i in range(1, 11)])
    if [row.get('template_id') for row in rows] != expected_ids:
        raise ValueError(f'{dataset} {role} fixed core IDs/order must be exactly 01-10')
    if len({row.get('template_id') for row in rows}) != 10:
        raise ValueError(f'{dataset} {role} fixed core contains duplicate template IDs')
    for row in rows:
        scope = row.get('dataset_scope')
        allowed_scope = (dataset, f'{dataset}_prompt_teaching_example')
        if (row.get('role') != role or scope not in allowed_scope or
                row.get('language') != language):
            raise ValueError(f'Invalid {dataset} {role} core identity: {row.get("template_id")}')
        if profile == 'r2r-en':
            notes = row.get('teaching_notes') or {}
            for field in ('semantic_pattern', 'decision_reason', 'transfer_rule', 'anti_pattern'):
                if not isinstance(notes.get(field), str) or not notes[field].strip():
                    raise ValueError(f'R2R {role} Core {row["template_id"]} missing teaching_notes.{field}')
    if role == 'reviewer':
        pairs = [row.get('pair_id') for row in rows]
        expected_pairs = [f'{prefix}-CORE-G{i:02d}' for i in range(1, 11)]
        if len(set(pairs)) != 10 or set(pairs) != set(expected_pairs):
            raise ValueError(f'{dataset} Reviewer Core pair_id values must uniquely cover all Generator Core IDs')
        gen_folder = ROOT/'generator'/'templates'/dataset/'core'
        gen_rows = [json.loads(path.read_bytes()) for path in sorted(gen_folder.glob('*.json'))]
        gen_ids = [row.get('template_id') for row in gen_rows]
        if set(pairs) != set(gen_ids):
            raise ValueError(f'{dataset} Reviewer Core pair IDs must cover Generator Core IDs exactly once')
        if profile == 'rxr-en-us' and pairs != gen_ids:
            raise ValueError('RxR Reviewer Core pair IDs must retain the frozen G01-G10 order')
    return rows


def transfer_checks(text):
    """Ask about scope without supplying a new instruction or choosing a boundary."""
    questions = []
    if len(re.findall(r"\b(?:stop|wait|stand|stay|remain)\b", text, re.I)) > 1:
        questions.append("Compare two readings of the stop clauses: one destination refined by a "
                         "more precise position, or two distinct stops. What source event requires "
                         "motion between them? If uncertain, preserve the source relationship.")
    if re.search(r",\s*(?:veering|turning|keeping|facing|passing)\b", text, re.I):
        questions.append("Compare the timing of the participial action before and after a proposed "
                         "cut. Does the source actually authorize turning an ongoing action into "
                         "an action beginning only AFTER the prior stage? Retain the original scope "
                         "where an example's handoff would impose a new order.")
    return questions


def runtime_review_output(example):
    """Convert authored teaching evidence to the active Reviewer Runtime v2 wire shape.

    Historical template files retain their original teaching representation. The
    compiler performs this lossless, source-grounded projection only at prompt
    assembly time; it never invents a stage index.
    """
    audit = json.loads(canonical(example["expected_review"]))
    stages = example["review_input"]["candidate"].get("subtasks", [])

    def convert(rows, path):
        converted = []
        for row_index, row in enumerate(rows or []):
            if isinstance(row, dict):
                item = dict(row)
                evidence = item.get("candidate_evidence", [])
                mapped = []
                for evidence_index, evidence_item in enumerate(evidence):
                    if isinstance(evidence_item, dict):
                        stage_index = evidence_item.get("subtask_index")
                        quote = evidence_item.get("quote")
                        if (type(stage_index) is not int or not 0 <= stage_index < len(stages)
                                or not isinstance(quote, str) or not quote
                                or quote not in stages[stage_index]):
                            raise ValueError(
                                f"Reviewer teaching evidence has invalid stage/quote at "
                                f"{path}/{row_index}/{evidence_index}: {evidence_item!r}"
                            )
                        mapped.append(evidence_item)
                        continue
                    if not isinstance(evidence_item, str) or not evidence_item:
                        raise ValueError(f"Invalid Reviewer teaching evidence at {path}/{row_index}/{evidence_index}")
                    matches = [i for i, stage in enumerate(stages) if evidence_item in stage]
                    if not matches:
                        raise ValueError(
                            f"Reviewer teaching evidence is not grounded in a candidate stage at "
                            f"{path}/{row_index}/{evidence_index}: {evidence_item!r}"
                        )
                    if len(matches) != 1:
                        raise ValueError(
                            f"Ambiguous Reviewer teaching evidence must declare subtask_index at "
                            f"{path}/{row_index}/{evidence_index}: {evidence_item!r}; "
                            f"matches stages {matches}"
                        )
                    mapped.append({"subtask_index": matches[0], "quote": evidence_item})
                item["candidate_evidence"] = mapped
                converted.append(item)
            else:
                converted.append(row)
        return converted

    audit["source_coverage"] = convert(audit.get("source_coverage", []), "/source_coverage")
    audit["findings"] = convert(audit.get("findings", []), "/findings")
    audit["prior_finding_reviews"] = convert(audit.get("prior_finding_reviews", []), "/prior_finding_reviews")
    audit.setdefault("prior_finding_reviews", [])
    # Map the legacy source-limited disposition to the active Runtime v2
    # source-ambiguity state without changing its evidence or verdict.
    for row in audit["source_coverage"]:
        if row.get("status") == "source_limited":
            row["status"] = "requires_review"
    for finding in audit["findings"]:
        if finding.get("code") == "UNRESOLVED_ROUTE_CHOICE" or (
                audit.get("verdict") == "unresolved" and not finding.get("code")):
            finding["code"] = "SOURCE_AMBIGUITY"
        if audit.get("verdict") == "unresolved":
            finding.setdefault("dimension", "source_fidelity")
            finding.setdefault("related_dimensions", [])
            finding.setdefault(
                "affected_subtask_indices",
                finding.get("repair", {}).get("affected_stage_indices", [])
            )
            repair = finding.get("repair", {})
            if repair.get("operation") == "retain_source_ambiguity_and_request_resolution":
                repair["operation"] = "preserve_uncertainty"
            repair.setdefault(
                "affected_subtask_indices",
                repair.get("affected_stage_indices", finding.get("affected_subtask_indices", []))
            )
            repair.pop("affected_stage_indices", None)
            if finding.get("c_check") == "C2_SUPPORT":
                finding["c_check"] = "C05"
    # Runtime v2 requires every L0-L6 row to explicitly link its findings.
    # Preserve authored links when present; otherwise derive only the direct
    # failed_layer relation from the authored finding records.
    for layer in audit.get("layer_checks", []):
        # v1 teaching used not_assessable when no rendered artifact existed.
        # Runtime v2 names that same non-applicable condition explicitly.
        if layer.get("status") == "not_assessable":
            layer["status"] = "not_applicable"
        if not layer.get("finding_indices"):
            layer["finding_indices"] = [
                i for i, finding in enumerate(audit["findings"])
                if finding.get("failed_layer") == layer.get("layer")
            ]
    return audit


def teaching_card(example, role, detailed):
    """Show the authored decision and its textual evidence in a compact demonstration."""
    notes = example["teaching_notes"]
    if role == "generator":
        out = example["output"]
        card = dict(source=example["input"]["original_instruction"], decision=example["decision"],
                    stages=out["subtasks"], handoffs=out["handoffs"], issues=out["issues"])
        # Every fixed core card carries the complete five-element stage audit.
        # Dynamic cards may use the compact form selected by the caller.
        if detailed:
            card["stage_evidence"] = out["stage_audit"]
        lesson = notes.get("reusable_rule") or notes.get("why_this_case_matters")
    else:
        audit = runtime_review_output(example)
        card = dict(review_case=example["review_input"], verdict=audit["verdict"],
                    dimensions=audit["dimensions"], findings=audit["findings"])
        if detailed:
            card["coverage_evidence"] = audit["source_coverage"]
            card["stage_checks"] = audit.get("stage_checks", [])
            card["layer_checks"] = audit.get("layer_checks", [])
            card["handoffs"] = audit["handoffs"]
        lesson = notes.get("case_specific_focus") or notes.get("review_principle") or notes.get("reuse_rule")
    return dict(template_id=example["template_id"], teaching=card, applicable_lesson=lesson,
                avoid=notes.get("anti_pattern"))


def compile_prompt(role,phase='initial',*,profile,examples=True,
                   original_instruction=None,example_count=DEFAULT_EXAMPLES,
                   selected_ids=None,selection_mode='adaptive'):
    if role not in ('generator','reviewer'):raise ValueError('Unknown semantic role')
    if profile not in PROFILES:raise ValueError('Unsupported dataset profile')
    if role=='reviewer' and phase not in ('review','recheck'):raise ValueError('Unsupported review phase')
    if role=='generator' and phase not in ('initial','repair'):raise ValueError('Unsupported generator phase')
    d=ROOT/role;repair=role=='generator' and phase=='repair'
    # Keep the R2R system prompt byte-for-byte free of RxR profile messaging.
    # RxR-only claims belong exclusively to the RxR profile branch below.
    build_message = (
        'BUILD: Selected examples are source-feature-matched and frozen per record. The original instruction is the only route authority.'
        if profile == 'r2r-en' else
        'BUILD: The shared semantic contract is supplemented by the RxR en-US guidance below. '
        'The original instruction is the only route authority; ten fixed RxR core examples '
        'and source-feature-matched dynamic examples are frozen per record.'
    )
    parts=[build_message,
            (d/'prompt.md').read_text(encoding='utf-8'),(ROOT/'shared/semantic_contract.md').read_text(encoding='utf-8')]
    if profile == 'r2r-en':
        parts.append('R2R DATASET-SPECIFIC RULES [shared/dataset_rules/r2r_en.md]:\\n' +
                     (ROOT/'shared/dataset_rules/r2r_en.md').read_text(encoding='utf-8'))
    if profile == 'rxr-en-us':
        parts.append('RXR SHARED SEMANTIC RULES [shared/dataset_rules/rxr_en_us.md]:\n' +
                     (ROOT/'shared/dataset_rules/rxr_en_us.md').read_text(encoding='utf-8'))
        parts.append(f'RXR ROLE GUIDANCE [{role}/dataset_rules/rxr_en_us.md]:\n' +
                     (d/'dataset_rules/rxr_en_us.md').read_text(encoding='utf-8'))
    if role=='reviewer':parts.append((d/'checklist.md').read_text(encoding='utf-8'))
    if repair:parts.append((d/'repair.md').read_text(encoding='utf-8'))
    schema=wire_schema(d/('repair.schema.json' if repair else 'output.schema.json'))
    parts.append('ACTIVE OUTPUT SCHEMA for this phase (JSON only):\n'+canonical(schema))
    if examples:
        rows=library(role,profile)
        fixed=core_library(role,profile)
        if selected_ids is None:
            chosen=select_examples(role,profile,original_instruction or '',count=example_count,mode=selection_mode)
        else:
            chosen=list(selected_ids)
            if len(chosen)!=len(set(chosen)):raise ValueError('Duplicate selected template IDs')
        byid={r['template_id']:r for r in rows}
        if any(x not in byid for x in chosen):raise ValueError('Selected dynamic template ID not in this dataset/role library')
        if fixed:
            core_ids=[r['template_id'] for r in fixed]
            parts.append(f'FIXED {profile.upper()} {role.upper()} CORE: exactly 10 fixed examples, always loaded in this stable order and never subject to retrieval or replacement: '+', '.join(core_ids))
            for position, example in enumerate(fixed):
                parts.append(canonical(teaching_card(example, role, detailed=True)))
        if profile == 'r2r-en':
            parts.append(f'CURATED {profile.upper()} {role.upper()} EXAMPLES: {len(chosen)} selected from {len(rows)} curated teaching cases. Teaching annotations are evidence demonstrations, not navigation ground truth. Teaching field names differ from the active response schema; use the active schema for your response. Copy no scene facts into the current task. Selected example IDs in order: '+', '.join(chosen))
        else:
            parts.append(f'DYNAMIC {profile.upper()} {role.upper()} EXAMPLES: {len(chosen)} selected from {len(rows)} dynamic teaching cases. These supplement, and never replace, the fixed core. Teaching annotations are evidence demonstrations, not navigation ground truth. Teaching field names differ from the active response schema; use the active schema for your response. Copy no scene facts into the current task. Selected dynamic example IDs in order: '+', '.join(chosen))
        for position, eid in enumerate(chosen):
            example = byid[eid]
            parts.append(canonical(teaching_card(example, role, detailed=(position == 0))))
        if repair:
            parts.append('TWO REPAIR-ENVELOPE EXAMPLES — active repair Schema, unlike initial-output examples. They teach accepting supported critique and rejecting unsupported advice.')
            parts.extend(canonical(e) for e in json.loads((ROOT/'generator/repair_examples.json').read_text(encoding='utf-8')))
        parts.append(
            "APPLY THE EXAMPLES TO THE CURRENT SOURCE. Compare the closest example's decision with "
            "the current action order, reference frame, and completion event. Transfer its rule only "
            "when the current wording supports the same relation. A different relation can require "
            "the opposite decision. " +
            ("Check whether a later location refines the same endpoint or starts a new objective."
             if role == "generator" else
             "Judge this candidate from its source and stage quotations; a paired example's pass "
             "or diagnostic example's revise is not a vote. Check that any alleged defect is present.")
            + " Express the result through the existing schema; do not output a template commentary."
        )
        checks = transfer_checks(original_instruction or "")
        if checks:
            parts.append("When comparing the cases above with this instruction, check: " + " ".join(checks))
    parts.append('ACTUAL INPUT: process only the current independent user message. Do not import a training example into this route. Return the ACTIVE schema JSON object.')
    return '\n\n'.join(parts)+'\n',schema

def build():
    out={}
    for role in ("generator","reviewer"):
        write_type_index(role)
    for profile in PROFILES:
        for role,phase,file in [('generator','initial','compiled_'+profile+'.txt'),('reviewer','review','compiled_'+profile+'.txt'),('generator','repair','compiled_repair_'+profile+'.txt')]:
            selected=select_examples(role,profile,'',count=DEFAULT_EXAMPLES)
            text,schema=compile_prompt(role,phase,profile=profile,selected_ids=selected)
            (ROOT/role/file).write_bytes(text.encode())
            out[f'{role}/{file}']={'compiled_sha256':text_hash(text),'schema_sha256':text_hash(canonical(schema)),
                                     'bytes':len(text.encode()),'default_examples':len(selected),'library_count':len(library(role,profile)),
                                     'fixed_core_count':len(core_library(role,profile)),
                                     'fixed_core_ids':[x['template_id'] for x in core_library(role,profile)],
                                     'profile':profile,'example_ids':selected,
                                     'runtime_note':'Actual per-task prompt selected by deterministic source features; record chosen IDs and full prompt hash per call.'}
    (ROOT/'provenance/build_manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    return out
if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False,indent=2))
