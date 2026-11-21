"""Compare actual R2R compilation and retrieval in independent Python processes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

PROGRAM = r'''
import hashlib,json
from host.compile import core_library,compile_prompt
from host.template_selector import library,source,select_examples
from shared.identity import canonical
texts=sorted(set(['', 'Walk to the second door and stop.', 'If you look left, you see two doors. Return through the same door.'] + [source(r) for r in library('generator','r2r-en')] + [source(r) for r in core_library('generator','r2r-en')]))
out={}
for text in texts:
    selected={role:select_examples(role,'r2r-en',text) for role in ('generator','reviewer')}
    rows={}
    for role,phase in [('generator','initial'),('reviewer','review'),('generator','repair'),('reviewer','recheck')]:
        prompt,schema=compile_prompt(role,phase,profile='r2r-en',original_instruction=text,selected_ids=selected[role])
        rows[role+'/'+phase]={'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'schema':schema}
    out[hashlib.sha256(text.encode()).hexdigest()]={'selected':selected,'compiled':rows}
print(canonical(out))
'''


def snapshot(root):
    result=subprocess.run([sys.executable,'-B','-c',PROGRAM],cwd=root,text=True,capture_output=True,check=True)
    return json.loads(result.stdout)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline',required=True,type=Path)
    parser.add_argument('--current',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    before,after=snapshot(args.baseline),snapshot(args.current)
    if before!=after:
        changed=[key for key in sorted(set(before)|set(after)) if before.get(key)!=after.get(key)]
        raise SystemExit('R2R isolation regression: '+json.dumps(changed))
    print(json.dumps({'r2r_inputs_compared':len(before),'phases_per_input':4,'exact_model_prompt_and_schema_match':True,'selection_match':True}))
    protected=['shared/semantic_contract.md','generator/prompt.md','generator/acceptance.md','generator/repair.md','reviewer/prompt.md','reviewer/checklist.md','generator/output.schema.json','generator/repair.schema.json','reviewer/output.schema.json','adapter/source.py','renderer/freeze.py','shared/dataset_rules/r2r_en.md','shared/dataset_rules/r2r_fragments.json','generator/dataset_rules/r2r_en.md','reviewer/dataset_rules/r2r_en.md']
    for path in protected:
        if (args.baseline/path).read_bytes()!=(args.current/path).read_bytes():
            raise SystemExit('Protected common/R2R asset changed: '+path)
    for role in ('generator','reviewer'):
        folder=Path(role)/'templates'/'R2R'
        for path in (args.baseline/folder).rglob('*.json'):
            rel=path.relative_to(args.baseline)
            if path.read_bytes()!=(args.current/rel).read_bytes():
                raise SystemExit('R2R template changed: '+str(rel))
    print(json.dumps({'protected_common_and_r2r_assets_unchanged':True}))

if __name__=='__main__':
    main()
