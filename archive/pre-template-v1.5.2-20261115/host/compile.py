"""Compile source-specific, role-specific examples into a single active prompt.

35 curated examples per role/profile are stored; default 8 (3 stable + 5 adaptive)
are chosen once per task. Source-only deterministic selection prevents prompt drift
between G0/G1 and R0/R1. No added model/agent for example retrieval.
"""
from __future__ import annotations
import json
from pathlib import Path
from shared.identity import canonical,text_hash
from host.template_selector import select_examples,library,DEFAULT_EXAMPLES,PROFILES
ROOT=Path(__file__).resolve().parents[1]

def compile_prompt(role,phase='initial',*,profile,examples=True,
                   original_instruction=None,example_count=DEFAULT_EXAMPLES,
                   selected_ids=None,selection_mode='adaptive'):
    if role not in ('generator','reviewer'):raise ValueError('Unknown semantic role')
    if profile not in PROFILES:raise ValueError('Unsupported dataset profile')
    if role=='reviewer' and phase not in ('review','recheck'):raise ValueError('Unsupported review phase')
    if role=='generator' and phase not in ('initial','repair'):raise ValueError('Unsupported generator phase')
    d=ROOT/role;repair=role=='generator' and phase=='repair'
    parts=['BUILD: final-best-v1 / roles-closed-loop-35. Selected few-shot examples are source-feature-matched and frozen per record; the source instruction remains the only route authority.',
            (d/'prompt.md').read_text(encoding='utf-8'),(ROOT/'shared/semantic_contract.md').read_text(encoding='utf-8')]
    if role=='reviewer':parts.append((d/'checklist.md').read_text(encoding='utf-8'))
    if repair:parts.append((d/'repair.md').read_text(encoding='utf-8'))
    schema=json.loads((d/('repair.schema.json' if repair else 'output.schema.json')).read_bytes())
    parts.append('ACTIVE OUTPUT SCHEMA for this phase (JSON only):\n'+canonical(schema))
    if examples:
        rows=library(role,profile)
        if selected_ids is None:
            chosen=select_examples(role,profile,original_instruction or '',count=example_count,mode=selection_mode)
        else:
            chosen=list(selected_ids)
            if len(chosen)!=len(set(chosen)) or not chosen:raise ValueError('Empty or duplicate selected template IDs')
        byid={r['example_id']:r for r in rows}
        if any(x not in byid for x in chosen):raise ValueError('Selected template ID not in this dataset/role library')
        parts.append(f'CURATED {profile.upper()} {role.upper()} EXAMPLES: {len(chosen)} selected from 35 training-source cases. Teaching annotations are evidence demonstrations, not navigation ground truth. Copy no scene facts into the current task. Selected example IDs in order: '+', '.join(chosen))
        for eid in chosen:
            example=byid[eid]
            if repair:
                # References to the SAME selected source cases, but never teach an
                # initial-output object as the active repair-envelope response.
                parts.append(canonical({'example_id':eid,'source':example['input']['original_instruction'],
                                        'reference_accepted_candidate':example['output'],
                                        'note':'Reference plan only; actual repair response must use candidate + responses schema.'}))
            elif role=='generator':
                # The initial-output schema already contains the five-element
                # audit: do not duplicate five_element_evidence/provenance in prompt.
                compact={k:example[k] for k in ('example_id','topic','input','output','lesson')}
                if example.get('counterexample'):
                    compact['contrast']={'candidate':example['counterexample']['candidate'],
                                         'defect':example['counterexample']['defect'],
                                         'safe_local_fix':example['counterexample']['safe_local_fix']}
                parts.append(canonical(compact))
            else:
                # Reviewer output is a complete schema instance; omit only
                # transport metadata/provenance not needed for its judgments.
                parts.append(canonical({k:example[k] for k in ('example_id','topic','input','output','lesson')}))
        if repair:
            parts.append('TWO REPAIR-ENVELOPE EXAMPLES — active repair Schema, unlike initial-output examples. They teach accepting supported critique and rejecting unsupported advice.')
            parts.extend(canonical(e) for e in json.loads((ROOT/'generator/repair_examples.json').read_text(encoding='utf-8')))
    parts.append('ACTUAL INPUT: process only the current independent user message. Do not import a training example into this route. Return the ACTIVE schema JSON object.')
    return '\n\n'.join(parts)+'\n',schema

def build():
    out={}
    for profile in PROFILES:
        for role,phase,file in [('generator','initial','compiled_'+profile+'.txt'),('reviewer','review','compiled_'+profile+'.txt'),('generator','repair','compiled_repair_'+profile+'.txt')]:
            selected=select_examples(role,profile,'',count=DEFAULT_EXAMPLES)
            text,schema=compile_prompt(role,phase,profile=profile,selected_ids=selected)
            (ROOT/role/file).write_bytes(text.encode())
            out[f'{role}/{file}']={'compiled_sha256':text_hash(text),'schema_sha256':text_hash(canonical(schema)),
                                     'bytes':len(text.encode()),'default_examples':len(selected),'library_count':len(library(role,profile)),
                                     'profile':profile,'example_ids':selected,
                                     'runtime_note':'Actual per-task prompt selected by deterministic source features; record chosen IDs and full prompt hash per call.'}
    (ROOT/'provenance/build_manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    return out
if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False,indent=2))
