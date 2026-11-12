"""Reproducibly compile actual files. Baseline snapshots are never model input."""
from pathlib import Path
import argparse, json, hashlib
ROOT=Path(__file__).resolve().parents[1]

def sha(b: bytes) -> str:return hashlib.sha256(b).hexdigest()
def _read(path: Path) -> str:return path.read_bytes().decode('utf-8')
def assemble() -> tuple[dict[str,bytes],dict]:
    common_path=ROOT/'contracts/execution_standard.md'; common=_read(common_path)
    files:dict[str,bytes]={};report={}
    for role in ['generator','reviewer']:
        d=ROOT/role;m=json.loads(_read(d/'manifest.json'))
        def safe(rel):
            p=(d/rel).resolve()
            if not p.is_relative_to(d.resolve()):raise ValueError('Unsafe compiled component path')
            return p
        core_path=safe(m['core']);schema_path=safe(m['schema'])
        inputs=[core_path,common_path,schema_path,d/'manifest.json']
        parts=[_read(core_path),'\n',common,'\nOUTPUT SCHEMA\n',json.dumps(json.loads(_read(schema_path)),ensure_ascii=False,separators=(',',':')),
               '\nTEACHING EXAMPLES. These demonstrate acceptable organization and defects; they are not unique gold stage counts. Host frozen_render metadata is omitted from teaching examples only.\n']
        for rel in m['templates']:
            p=safe(rel);inputs.append(p);e=json.loads(_read(p))
            parts += ['\n'+e['id']+'\nInput:\n',json.dumps(e['input'],ensure_ascii=False,separators=(',',':')),'\nOutput:\n',json.dumps(e['output'],ensure_ascii=False,separators=(',',':')),'\n']
            if role=='generator':
                parts += ['Contrast for diagnosis (NOT an instruction to execute):\n',json.dumps(e['contrast'],ensure_ascii=False,separators=(',',':')),'\n',e['allowed_granularity'],'\n']
            else:parts += [e['teaching_note'],'\n']
        parts += ['\nProcess only ACTUAL INPUT in the separate user message. Return schema JSON, not private deliberation.\n']
        blob=''.join(parts).encode('utf-8'); files[role+'/compiled.txt']=blob
        report[role]={'sha256':sha(blob),'bytes':len(blob),'words':len(blob.decode().split()),'templates':len(m['templates']),
                      'shared_standard_sha256':sha(common.encode()),'components':{str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in inputs}}
    d=ROOT/'generator';inputs=[d/'prompt.md',common_path,d/'repair.md',d/'repair.schema.json',d/'repair_examples.json']
    repair=''.join([_read(d/'prompt.md'),'\n',common,'\n',_read(d/'repair.md'),
                    '\nACTIVE REPAIR OUTPUT SCHEMA (use this envelope instead of the initial-output schema):\n',json.dumps(json.loads(_read(d/'repair.schema.json')),ensure_ascii=False,separators=(',',':')),
                    '\nREPAIR EXAMPLES (generator judges advice independently):\n',json.dumps(json.loads(_read(d/'repair_examples.json')),ensure_ascii=False,separators=(',',':')),
                    '\nProcess the actual repair input now. Return only the active repair JSON.'])
    files['generator/compiled_repair.txt']=repair.encode()
    report['repair']={'sha256':sha(repair.encode()),'bytes':len(repair.encode()),'components':{str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in inputs}}
    return files,report

def compile_all(check: bool=False) -> dict:
    files,report=assemble()
    manifest=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode()
    files['orchestrator/COMPILED_MANIFEST.json']=manifest
    for rel,blob in files.items():
        p=ROOT/rel
        if check:
            if not p.exists() or p.read_bytes()!=blob:raise ValueError(f'Stale/missing compiled file: {rel}; compile explicitly before an experiment')
        else:p.write_bytes(blob)
    return report
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
    print(json.dumps(compile_all(args.check),ensure_ascii=False,indent=2))
