"""Explicit additional integration for authored R2R contrasts; RxR is unchanged."""
import json

def extend(outputs):
    name='host/template_selector.py';s=outputs[name]
    s=s.replace("    if profile == 'rxr-en-us':\n        dynamic_dirs += ('train',)","    if profile == 'rxr-en-us':\n        dynamic_dirs += ('train',)\n    elif profile == 'r2r-en':\n        dynamic_dirs += ('authored',)")
    s=s.replace("('R2R', 'generator'): 25, ('R2R', 'reviewer'): 55,","('R2R', 'generator'): 27, ('R2R', 'reviewer'): 59,")
    s=s.replace("        if dataset == 'RxR':\n            expected_pairs", "        if dataset == 'R2R':\n            expected_pairs.update({'R2R-GEN-036','R2R-GEN-037'})\n        if dataset == 'RxR':\n            expected_pairs")
    s=s.replace("expected_paired = 29 if dataset == 'R2R' else 43","expected_paired = 31 if dataset == 'R2R' else 43")
    s=s.replace("expected_diagnostics = 26 if dataset == 'R2R' else 37","expected_diagnostics = 28 if dataset == 'R2R' else 37")
    s=s.replace("        if profile == \"rxr-en-us\":\n            allowed += (\"train\",)","        if profile == \"rxr-en-us\":\n            allowed += (\"train\",)\n        elif profile == \"r2r-en\":\n            allowed += (\"authored\",)")
    outputs[name]=s
    for role in ('generator','reviewer'):
        name=role+'/templates_manifest.json';m=json.loads(outputs[name]);profile=m['dataset_profiles']['r2r-en']
        profile.update(authored_directory='templates/R2R/authored',authored_count=2 if role=='generator' else 4,
            authored_source_type='synthetic semantic teaching, not official dataset records',runtime_dynamic_count=27 if role=='generator' else 59)
        if role=='reviewer':profile.update(runtime_paired_dynamic_count=31,runtime_diagnostics_count=28)
        outputs[name]=json.dumps(m,ensure_ascii=False,indent=2)+'\n'
    name='host/compile.py'
    anchor="    if profile == 'r2r-en':\n        parts.append('ACTIVE OUTPUT SCHEMA for this phase (JSON only):\\n'+canonical(schema))"
    block="    if examples and profile == 'r2r-en' and phase in ('repair', 'recheck'):\n        filename = 'r2r_repair_examples.json' if role == 'generator' else 'r2r_recheck_examples.json'\n        parts.append('R2R PHASE-SPECIFIC ADVICE CONTRASTS: prior R0 advice below is intentionally fallible. Transfer the independent source check, not the mistaken advice; expected_output obeys the current phase schema.')\n        parts.extend(canonical(e) for e in json.loads((d/'dataset_rules'/filename).read_text(encoding='utf-8')))\n"
    if outputs[name].count(anchor)!=1:raise ValueError('Phase-lesson integration anchor drift')
    outputs[name]=outputs[name].replace(anchor,block+anchor)
    return outputs


def extend_tests(name,text):
    """Approved count expectations only; all semantic assertions are preserved."""
    for old,new in [
        ('("reviewer", 55)','("reviewer", 59)'),('("generator", 25)','("generator", 27)'),
        ("('r2r-en',(25,55))","('r2r-en',(27,59))"),
        ('sum(not x.get("pair_id") for x in rows), 26','sum(not x.get("pair_id") for x in rows), 28'),
        ("sum(not r.get('pair_id') for r in library('reviewer',profile)),26","sum(not r.get('pair_id') for r in library('reviewer',profile)),28"),
        ('len(rows), 25','len(rows), 27'),('len(rows), 55','len(rows), 59'),
        ('self.assertEqual(len(paired),29)','self.assertEqual(len(paired),31)'),
        ('dynamic_kinds = ("val_seen",) if role == "generator" else ("paired", "diagnostics")',
         'dynamic_kinds = (("val_seen",) if role == "generator" else ("paired", "diagnostics")) + ("authored",)'),
    ]:text=text.replace(old,new)
    return text
