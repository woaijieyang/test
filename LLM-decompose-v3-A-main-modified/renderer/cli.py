"""Prepare frozen text without running a language model or navigator."""
from __future__ import annotations
from pathlib import Path
from dataclasses import asdict
import argparse
from adapter import ingest
from contracts.common import read_json,canonical_json,require
from .freeze import prepare

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--maps',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();source=ingest(read_json(a.source));candidate=read_json(a.candidate)
    f=prepare(source,candidate,explicit_maps=read_json(a.maps) if a.maps else None)
    require(not a.output.exists(),'Refuse to overwrite an existing frozen candidate');a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('xb') as stream:stream.write((canonical_json(asdict(f))+'\n').encode())
    print(f'Prepared {f.mode}; candidate is NOT yet approved. Output: {a.output}')
if __name__=='__main__':main()
