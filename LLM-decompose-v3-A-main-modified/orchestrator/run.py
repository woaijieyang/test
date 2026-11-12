"""Sequential JSONL runner with atomic results, replay protection and explicit resume.

Examples:
 python -m orchestrator.run --records examples/batch.jsonl --config examples/config.fixture.json \
   --output-dir /tmp/vln-demo --transport python -m examples.fixture_transport

Replace --transport with YOUR existing Codex/API bridge for model runs. This command
may incur costs when that bridge is real. It never executes navigation.
"""
from __future__ import annotations
import argparse,json,os,sys,uuid
from pathlib import Path
from dataclasses import asdict
from typing import Callable
from adapter import ingest
from contracts.common import ContractError,canonical_json,parse_json,read_json,require,sha_obj,sha_text
from .requests import RuntimeConfig
from .engine import run_record,experiment_identity
from .transport import command_transport

def atomic_new(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('xb') as f:
            f.write((json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8'));f.flush();os.fsync(f.fileno())
        # Hard link is atomic and refuses overwrite. Root/output must be on one filesystem.
        os.link(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()

def load_records(path: Path) -> list[dict]:
    data=path.read_bytes().decode('utf-8')
    if path.suffix.lower()=='.json':
        parsed=parse_json(data);rows=parsed if isinstance(parsed,list) else [parsed]
    else:rows=[parse_json(line) for line in data.split('\n') if line.strip()]
    require(bool(rows),'Input batch has no records')
    seen=set()
    for row in rows:
        source=ingest(row)
        require(source.task_key not in seen,'Duplicate task_key in batch; include dataset/split/scene/instruction identity in the key')
        seen.add(source.task_key)
    return rows

def run_batch(rows: list[dict], config: RuntimeConfig, transport: Callable, output_dir: Path, *,
              resume: bool=False,retry_incomplete: bool=False) -> dict:
    lock=experiment_identity(config)
    sources=[ingest(row) for row in rows]
    require(bool(sources) and len({s.task_key for s in sources})==len(sources),'Empty/duplicate batch')
    run_identity={'version':'v1.3-static.2','experiment_lock':lock,'ordered_record_identities':[s.record_identity_sha256 for s in sources]}
    run_identity['run_identity_sha256']=sha_obj(run_identity)
    output_dir.mkdir(parents=True,exist_ok=True)
    lockfile=output_dir/'.runner.lock'
    # Prevent parallel workers from creating different manifest/result combinations.
    try:fd=os.open(str(lockfile),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:raise ContractError('Runner lock exists. Verify no process is active before removing a stale lock.')
    try:
        os.write(fd,str(os.getpid()).encode());os.close(fd)
        manifest=output_dir/'RUN_MANIFEST.json'
        if manifest.exists():
            require(resume,'Output run already exists; use --resume with the identical record set and configuration')
            require(read_json(manifest)==run_identity,'Resume source/order/model/prompt/schema/version identity mismatch')
        else:
            require(not any(output_dir.iterdir()) or set(x.name for x in output_dir.iterdir())=={'.runner.lock'},'Nonempty output directory has no valid run manifest')
            atomic_new(manifest,run_identity)
        counts={};completed=0;skipped=0
        for row,source in zip(rows,sources):
            key=sha_text(source.task_key)
            result_path=output_dir/'records'/(key+'.json');log_path=output_dir/'logs'/(key+'.jsonl')
            if result_path.exists():
                saved=read_json(result_path);stored=saved.pop('stored_result_sha256',None)
                require(stored==sha_obj(saved),'Saved result altered')
                require(saved['record_identity_sha256']==source.record_identity_sha256 and saved['experiment_lock_sha256']==lock['experiment_sha256'],'Stale saved record')
                state=saved['result']['state'];counts[state]=counts.get(state,0)+1;skipped+=1;continue
            if log_path.exists() and log_path.stat().st_size:
                require(retry_incomplete,'Incomplete journal exists; an interrupted API call may have incurred cost. Explicit --retry-incomplete is required')
            log_path.parent.mkdir(parents=True,exist_ok=True)
            def journal(event):
                with log_path.open('ab') as f:
                    f.write((canonical_json(event)+'\n').encode());f.flush();os.fsync(f.fileno())
            if log_path.exists() and log_path.stat().st_size:
                journal({'event':'explicit_incomplete_retry','note':'Prior incomplete invocation may have incurred external cost'})
            out=run_record(row,transport,config,journal=journal)
            out['stored_result_sha256']=sha_obj(out)
            atomic_new(result_path,out)
            state=out['result']['state'];counts[state]=counts.get(state,0)+1;completed+=1
        summary={'run_identity_sha256':run_identity['run_identity_sha256'],'records':len(rows),'newly_completed':completed,'resumed_existing':skipped,
                 'states':counts,'run_kind':config.run_kind,'navigation_run':False}
        # Summary is derived only, immutable record files are authoritative.
        tmp=output_dir/('SUMMARY.'+uuid.uuid4().hex+'.tmp');tmp.write_bytes((json.dumps(summary,ensure_ascii=False,indent=2)+'\n').encode());os.replace(tmp,output_dir/'SUMMARY.json')
        return summary
    finally:
        if lockfile.exists():lockfile.unlink()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--records',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--resume',action='store_true');p.add_argument('--retry-incomplete',action='store_true');p.add_argument('--timeout-seconds',type=float,default=300)
    p.add_argument('--transport',nargs=argparse.REMAINDER,required=True)
    a=p.parse_args();require(bool(a.transport),'Transport command required')
    summary=run_batch(load_records(a.records),RuntimeConfig.from_dict(read_json(a.config)),command_transport(a.transport,timeout_seconds=a.timeout_seconds),a.output_dir,resume=a.resume,retry_incomplete=a.retry_incomplete)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 2 if summary['states'].get('fallback_technical_failure',0) else 0
if __name__=='__main__':
    try:sys.exit(main())
    except (ContractError,KeyError,ValueError,TypeError,OSError) as exc:
        print(f'Run refused: {type(exc).__name__}: {exc}',file=sys.stderr);sys.exit(2)
