from __future__ import annotations
import json,sys
from pathlib import Path
from shared.identity import canonical,text_hash
ROOT=Path(__file__).resolve().parents[1]
def compile_prompt(role,phase='initial',*,examples=True):
    if role not in ('generator','reviewer'): raise ValueError(role)
    d=ROOT/role;repair=role=='generator' and phase=='repair';parts=['BUILD: final-best-v1 | v1.3-derived semantic baseline with evidence-backed refinements.',(d/'prompt.md').read_text(),(ROOT/'shared/semantic_contract.md').read_text()]
    if role=='reviewer':parts.append((d/'checklist.md').read_text())
    if repair:parts.append((d/'repair.md').read_text())
    schema=json.loads((d/('repair.schema.json' if repair else 'output.schema.json')).read_bytes());parts.append('OUTPUT SCHEMA (JSON only):\n'+canonical(schema))
    if examples:
        parts.append('CONTRASTIVE TEACHING NOTES: acceptable alternatives and pitfalls, not unique gold outputs. Use the schema above for live replies. The examples are not facts about the current route.')
        for p in sorted((ROOT/'templates').glob('[0-9][0-9].json')):
            e=json.loads(p.read_bytes());f={'topic':e['title'],'source':e['source'],'acceptable_candidate':e['acceptable'],'contrast':e['contrast']['subtasks'],'difference':e['execution_or_focus_difference'],'other_valid_choices_or_limits':e['alternative_or_limit']}
            if role=='reviewer': f.update(check=e['check'],axis=e['dimension'],source_evidence=e['source_quote'],contrast_evidence=e['candidate_contrast_quote'])
            parts.append(canonical(f))
    parts+=['ACTUAL INPUT: process only the record in the user message.'];return '\n\n'.join(parts)+'\n',schema

def build():
    out={}
    for role,phase,file in [('generator','initial','compiled.txt'),('reviewer','review','compiled.txt'),('generator','repair','compiled_repair.txt')]:
        text,schema=compile_prompt(role,phase);(ROOT/role/file).write_bytes(text.encode());out[f'{role}/{file}']={'compiled_sha256':text_hash(text),'schema_sha256':text_hash(canonical(schema)),'bytes':len(text.encode()),'examples':15}
    (ROOT/'provenance/build_manifest.json').write_text(json.dumps(out,indent=2)+'\n');return out
if __name__=='__main__': print(json.dumps(build(),indent=2))
