"""Auditable one-time integration against the immutable parent.

Every replacement is explicit and scoped to R2R. A file must match either the
parent or this expected result; concurrent edits are never overwritten. The
resulting runtime files are committed and subsequently verified directly.
"""
from pathlib import Path
import argparse,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
PARENT='081db4b9ea0712ff720c137fe96c240c26f7b15c'

def base(path):return subprocess.check_output(['git','show',PARENT+':'+path],cwd=ROOT).decode()
def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('Integration anchor not unique: '+old[:120])
    return text.replace(old,new,1)

def expected():
    out={}
    p='host/compile.py';s=base(p)
    s=replace(s,'    notes = example["teaching_notes"]\n','    if example.get("dataset_scope") == "R2R":\n        from r2r.teaching import card\n        return card(example, role, detailed)\n    notes = example["teaching_notes"]\n')
    anchor="        if any(x not in byid for x in chosen):raise ValueError('Selected dynamic template ID not in this dataset/role library')"
    s=replace(s,anchor,anchor+"\n        if profile == 'r2r-en':\n            from r2r.selection import validate_selection\n            validate_selection(role, chosen, selection_mode)")
    out[p]=s
    p='host/template_selector.py';s=base(p)
    s=replace(s,"('R2R', 'generator'): 25, ('R2R', 'reviewer'): 52,","('R2R', 'generator'): 25, ('R2R', 'reviewer'): 55,")
    s=replace(s,"expected_diagnostics = 23 if dataset == 'R2R' else 37","expected_diagnostics = 26 if dataset == 'R2R' else 37")
    anchor='    if mode != "adaptive":\n        raise ValueError("Unknown example selection mode")\n'
    s=replace(s,anchor,anchor+'    if profile == "r2r-en":\n        from r2r.selection import select_bundle\n        return select_bundle(source_text, count=count)[role]\n')
    s=s.replace('R2R 6-8; RxR 2-4','R2R 4-6; RxR 2-4')
    out[p]=s
    p='host/run.py';s=base(p)
    s=replace(s,'def request(role, phase, payload, pin, profile, selected_ids):','def request(role, phase, payload, pin, profile, selected_ids, *, selection_mode="adaptive"):')
    s=replace(s,'original_instruction=payload.get("original_instruction")','original_instruction=payload.get("original_instruction"), selection_mode=selection_mode')
    s=replace(s,'req = request(role, phase, payload, pins[role], src.profile, selections[role])','req = request(role, phase, payload, pins[role], src.profile, selections[role], selection_mode=selection_mode)')
    anchor='''        paths.extend([
            root/"shared/dataset_rules/r2r_en.md",
            root/role/"dataset_rules/r2r_en.md",
        ])'''
    s=replace(s,anchor,anchor+'''
        paths.extend([root/"r2r/selection.py", root/"r2r/teaching.py",
                      root/"shared/dataset_rules/r2r_teaching_index.json",
                      root/"generator/templates_manifest.json", root/"reviewer/templates_manifest.json"])''')
    old='''        selections = {
            role: select_examples(role, src.profile, src.raw,
                                  count=example_count, mode=selection_mode)
            for role in ("generator", "reviewer")
        }
        retrieval_evidence = {role: selection_evidence(role, src.profile, src.raw, ids)
                              for role, ids in selections.items()}'''
    new='''        if src.profile == "r2r-en" and selection_mode == "adaptive":
            from r2r.selection import select_bundle
            plan = select_bundle(src.raw, count=example_count)
            selections = {role: plan[role] for role in ("generator", "reviewer")}
            retrieval_evidence = plan["evidence"]
        else:
            selections = {
                role: select_examples(role, src.profile, src.raw,
                                      count=example_count, mode=selection_mode)
                for role in ("generator", "reviewer")
            }
            retrieval_evidence = {role: selection_evidence(role, src.profile, src.raw, ids)
                                  for role, ids in selections.items()}'''
    s=replace(s,old,new);out[p]=s
    for role in ('generator','reviewer'):
        p=role+'/templates_manifest.json';m=json.loads(base(p));policy=m['runtime_policy']['r2r-en']
        if role=='generator':policy['dynamic_generator_examples']=[4,6]
        else:
            policy.update(paired_dynamic_examples=[4,6],diagnostic_dynamic_examples=[2,3])
            m['dataset_profiles']['r2r-en'].update(diagnostics_count=29,runtime_diagnostics_count=26,runtime_dynamic_count=55)
        out[p]=json.dumps(m,ensure_ascii=False,indent=2)+'\n'
    # Prevent an RxR authoring job from rewriting assets on a pure R2R change.
    # Its validation steps and runtime behavior remain unchanged.
    p='.github/workflows/rxr-development.yml';s=base(p)
    s=replace(s,"      - 'tools/**'\n      - 'host/**'", "      - 'tools/rxr*'\n      - 'tools/build_rxr*'\n      - 'host/rxr*'")
    s=replace(s,"      - 'tests/**'", "      - 'tests/test_rxr*'")
    out[p]=s
    p='README.md';s=base(p);lines=s.splitlines();lines[0]='# LLM-decompose-v6.6.4';s='\n'.join(lines)+'\n'
    for old,new in [('| Generator Dynamic per task | 6–8 |','| Generator Dynamic per task | 4–6 |'),('| Reviewer Paired per task | 6–8 |','| Reviewer Paired per task | 4–6 |'),('| Reviewer Diagnostics Eligible | 23 |','| Reviewer Diagnostics Eligible | 26 |'),('| Reviewer Diagnostics per task | 2–4 |','| Reviewer Diagnostics per task | 2–3 |')]:s=replace(s,old,new)
    s+='\nR2R 新实现、父分支差异和验证边界见 `docs/R2R_IMPLEMENTATION.md`。完整作者资产用 `python -B -m r2r_authoring.build --check` 校验；当前模型和导航性能仍需独立实验。\n'
    out[p]=s
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--write',action='store_true');args=p.parse_args();changed=[]
    for rel,text in expected().items():
        path=ROOT/rel;current=path.read_text()
        if current==text:continue
        if current!=base(rel):raise ValueError('Unexpected concurrent content: '+rel)
        changed.append(rel)
        if args.write:path.write_text(text)
    print(json.dumps({'integration_changed':changed,'write':args.write}))
    if changed and not args.write:raise SystemExit(1)
if __name__=='__main__':main()
