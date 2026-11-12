"""Provider-neutral request preparation. Does not invoke any API."""
from __future__ import annotations
import argparse
from pathlib import Path
from adapter import ingest
from renderer.freeze import FrozenCandidate
from contracts.common import read_json,canonical_json,require
from .requests import RuntimeConfig,ModelSpec,build_request

def main():
    p=argparse.ArgumentParser();p.add_argument('--role',choices=['generator','reviewer','repair'],required=True)
    p.add_argument('--record',type=Path,required=True);p.add_argument('--frozen',type=Path);p.add_argument('--review',type=Path)
    p.add_argument('--model',required=True);p.add_argument('--effort',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();s=ingest(read_json(a.record));spec=ModelSpec(a.model,a.effort);cfg=RuntimeConfig(spec,spec)
    if a.role=='generator':payload=s.model_input()
    else:
        require(a.frozen is not None,'review/repair require a frozen candidate')
        f=FrozenCandidate(**read_json(a.frozen));f.verify()
        if a.role=='reviewer':payload=f.review_payload(s)
        else:
            require(a.review is not None,'repair requires independent reviewer feedback')
            f.review_payload(s) # source/task binding
            payload={'original_instruction':s.original_instruction,'candidate':f.candidate(),'reviewer_feedback':read_json(a.review)}
    req=build_request(a.role,payload,cfg);require(not a.output.exists(),'Refuse to overwrite an existing request');a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('xb') as stream:stream.write((canonical_json(req)+'\n').encode())
    print(f'Request written, not executed: {a.output}')
if __name__=='__main__':main()
