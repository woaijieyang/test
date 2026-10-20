"""New-identity continuation after the diagnosed receipt-interface failure.

Completed ordinary failures and successes stay under their original identity.
Only unfinished tasks execute again; the parent scope and total budget persist.
"""
from collections import Counter
import ast
import json
import math
from pathlib import Path
import zipfile

from oracle.common.artifacts import digest,content_digest,owned_output,write_json,package_sources,freeze_sources,timestamp
from oracle.common.task_index import merkle_index
from oracle.research.cohort_review import read_prefix,review as review_snapshot
from oracle.research.full_run import live


FINAL_STATUSES={'PASS_CONTINUOUS_REFERENCE_AND_ENDPOINT_GATES','FAILURE_PRESERVED',
                'STATIC_FAILURE_PRESERVED','ROUTE_WITNESS_ONLY_ENDPOINT_SOURCE_GATE_FAIL'}


def partition_entries(entries,completed):
    keys=[e['record']['task_key'] for e in entries];done=[r['task_key'] for r in completed]
    if len(set(keys))!=len(keys) or len(set(done))!=len(done) or not set(done).issubset(keys):
        raise ValueError('Duplicate or unexpected task identity')
    if any(r['status'] not in FINAL_STATUSES for r in completed):raise ValueError('Infrastructure stop is not a completed navigation result')
    done=set(done)
    return [e for e in entries if e['record']['task_key'] not in done]


def remaining_cpu_seconds(hours,charged):
    if not math.isfinite(hours) or not math.isfinite(charged) or hours<=0 or charged<0 or charged>=hours*3600:
        raise ValueError('Invalid/exhausted cumulative CPU budget')
    return math.floor(hours*3600-charged)


def verify_compatibility(parent,package):
    m=json.loads((parent/'manifest.json').read_text())
    unchanged=['planners/action_space.py','adapters/habitat/native.py','common/identity.py','contracts.py',
        'portfolio/guarded_prefix.py','verification/linear_sweep.py','verification/projected_distance.py',
        'verification/contact_certificate.py','configs/protocols/current_linear.json','research/full_run.py']
    for name in unchanged:
        if digest(package/name)!=m['sources'][name]:raise ValueError('Unrelated execution change: '+name)
    class RemoveCatalogArgument(ast.NodeTransformer):
        def visit_Call(self,node):
            self.generic_visit(node)
            if isinstance(node.func,ast.Name) and node.func.id=='SourceScene':
                for keyword in node.keywords:
                    if keyword.arg=='catalog' and not (isinstance(keyword.value,ast.Name) and keyword.value.id=='geometry'):
                        raise ValueError('Unexpected catalog argument')
                node.keywords=[k for k in node.keywords if k.arg!='catalog']
            return node
    changed=['teachers/ordered.py','teachers/official.py','research/full_worker.py',
             'verification/route_replay.py','verification/alias_probe.py','verification/contact_causes.py']
    with zipfile.ZipFile(parent/'source.zip') as source:
        for name in changed:
            old=ast.parse(source.read(name));new=RemoveCatalogArgument().visit(ast.parse((package/name).read_bytes()))
            if ast.dump(old)!=ast.dump(new):raise ValueError('Caller changed beyond geometry binding: '+name)
        def contact(tree):
            cls=next(n for n in ast.parse(tree).body if isinstance(n,ast.ClassDef) and n.name=='SourceScene')
            return ast.dump(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='contact'))
        name='verification/source_scene.py'
        if contact(source.read(name))!=contact((package/name).read_bytes()):raise ValueError('Collision predicate changed')
    return dict(unchanged_sha256_files=unchanged,catalog_only_callers=changed,contact_predicate_ast_equal=True,
                scope='Only constructor receipt adaptation; no action search, motion, collision or budget predicate change')


def prepare(case_root,parent_path,geometry_audit_path,output):
    import fcntl
    root=Path(case_root).resolve();parent=owned_output(root,parent_path);output=owned_output(root,output)
    if output.exists():raise FileExistsError(output)
    package,sources=package_sources();config_path=package/'configs/experiments/full_continuation.json'
    policy=json.loads(config_path.read_text());m=json.loads((parent/'manifest.json').read_text());msha=digest(parent/'manifest.json')
    if msha!=policy['parent_manifest_sha256'] or m['task_count']!=policy['original_task_count'] or m['datasets']!=policy['original_datasets']:
        raise ValueError('Unapproved parent experiment identity')
    lock=(parent/'controller.lock').open('r');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        process=json.loads((parent/'controller-process.json').read_text())
        if live(process):raise ValueError('Parent controller is still alive')
        state=json.loads((parent/'state.json').read_text());freeze=json.loads((parent/'source-freeze.json').read_text())
        if state['status']!='STOPPED_RESUMABLE_AFTER_REVIEW' or freeze['status']!='CLOSED':raise ValueError('Parent not cleanly stopped')
        for name in ('start.json','spawn.json'):
            for p in (parent/'jobs').glob('*/*/*/'+name):
                if live(json.loads(p.read_text())):raise ValueError('Old owned phase remains alive')
        stops=[json.loads(p.read_text()) for p in parent.glob('stop-*.json')]
        if not stops or any(policy['allowed_incident'] not in r['error'] for r in stops):raise ValueError('Other incident needs separate review')
        audit_path=owned_output(root,geometry_audit_path);audit=json.loads(audit_path.read_text())
        if (audit['status']!='ALL71_NATIVE_GEOMETRY_SCHEMA_AND_BYTE_CONTROLS_PASS_NOT_MOTION' or audit['scenes']!=71
            or any(not r['arrays_byte_identical'] for r in audit['records'])
            or audit['startup']['modules']['oracle.verification.source_scene']['sha256']!=digest(package/'verification/source_scene.py')):
            raise ValueError('Full geometry schema controls missing or stale')
        compatibility=verify_compatibility(parent,package)
        if digest(parent/'tasks.jsonl')!=m['tasks_file_sha256'] or digest(parent/'index.json')!=m['index_sha256']:
            raise ValueError('Parent input drift')
        completed,seq,previous=read_prefix(sorted((parent/'journal').glob('segment-*.jsonl')))
        if len(completed)!=state['completed']:raise ValueError('Stopped journal/state disagree')
        entries=json.loads((parent/'index.json').read_text());remaining=partition_entries(entries,list(completed.values()))
        support=output.with_name(output.name+'-preparation');support.mkdir()
        snapshot=support/'parent-snapshot';snapshot.mkdir()
        for p in sorted((parent/'journal').glob('segment-*.jsonl')):(snapshot/(p.name+'.snapshot')).write_bytes(p.read_bytes())
        write_json(snapshot/'selected-results.json',list(completed.values()))
        scope=dict(mode='sealed_completed_prefix',parent_manifest_sha256=msha,parent_task_count=m['task_count'],
                   datasets=dict(Counter(r['dataset'] for r in completed.values())),selection_keys=sorted(completed))
        write_json(snapshot/'scope.json',scope)
        write_json(snapshot/'snapshot.json',dict(source_run_root=str(parent),parent_manifest_sha256=msha,
            journal_frames=seq,journal_last_hash=previous,records=len(completed),datasets=scope['datasets'],
            files_sha256={str((parent/name).relative_to(root)):digest(parent/name) for name in ('manifest.json','index.json','tasks.jsonl','source.zip')}))
        review=review_snapshot(root,snapshot,support/'parent-prefix-review',scope=scope)
        seconds=remaining_cpu_seconds(m['config']['total_cpu_budget_hours'],state['charged_cpu_upper_bound_seconds'])
        output.mkdir();new_entries=[];selection=[];counts=Counter();branches=Counter();source_sha=content_digest(sources)
        with (parent/'tasks.jsonl').open('rb') as src,(output/'tasks.jsonl').open('xb') as dest:
            for entry in remaining:
                e=entry['record'];src.seek(e['offset']);raw=src.read(e['bytes'])
                if __import__('hashlib').sha256(raw).hexdigest()!=e['sha256']:raise ValueError('Parent task changed')
                task=json.loads(raw);before={k:v for k,v in task.items() if k!='module_source_sha256'}
                old_sha=content_digest(task);task['module_source_sha256']=source_sha
                if before!={k:v for k,v in task.items() if k!='module_source_sha256'}:raise ValueError('Task meaning changed')
                encoded=(json.dumps(task,ensure_ascii=False,separators=(',',':'),allow_nan=False)+chr(10)).encode()
                offset=dest.tell();dest.write(encoded)
                new_entries.append({**e,'offset':offset,'bytes':len(encoded),'sha256':__import__('hashlib').sha256(encoded).hexdigest()})
                selection.append(dict(task_key=task['task_key'],parent_task_sha256=old_sha,new_task_sha256=content_digest(task),
                                      unchanged_task_meaning_sha256=content_digest(before)))
                counts[task['dataset']]+=1;branches[task['cohort']]+=1
        merkle,proofs=merkle_index(new_entries);write_json(output/'index.json',proofs);write_json(output/'parent-task-correspondence.json',selection)
        config={**m['config'],'expected':dict(counts),'total_cpu_budget_hours':seconds/3600,
                'maximum_infrastructure_attempts':policy['new_execution_attempts_per_remaining_phase']}
        child={**m,'status':'FROZEN_COMPATIBILITY_CONTINUATION_NOT_NEW_ALGORITHM','created_at':timestamp(),
               'config':config,'sources':sources,'task_count':len(new_entries),'datasets':dict(counts),
               'information_branches':dict(branches),'task_merkle_root':merkle,
               'tasks_file_sha256':digest(output/'tasks.jsonl'),'index_sha256':digest(output/'index.json'),
               'launchers':{str(root/'oracleAdapter/run.py'):digest(root/'oracleAdapter/run.py'),str(root/'scripts/with_runtime.sh'):digest(root/'scripts/with_runtime.sh')},
               'scope':'Remaining tasks only; combine with sealed parent results to assess original37016. No parent result is rerun or relabelled.',
               'continuation':dict(parent_run=str(parent),parent_manifest_sha256=msha,parent_task_count=m['task_count'],
                  parent_datasets=m['datasets'],retained_completed=len(completed),remaining=len(new_entries),
                  parent_prefix_review=str(support/'parent-prefix-review/validation.json'),
                  parent_prefix_review_sha256=digest(support/'parent-prefix-review/validation.json'),
                  parent_charged_cpu_upper_bound_seconds=state['charged_cpu_upper_bound_seconds'],remaining_cpu_seconds=seconds,
                  original_total_cpu_budget_hours=m['config']['total_cpu_budget_hours'],geometry_audit_path=str(audit_path),
                  geometry_audit_sha256=digest(audit_path),compatibility=compatibility,retry_policy=policy['retry_note'])}
        if len(completed)+len(new_entries)!=m['task_count']:raise ValueError('Logical full denominator changed')
        write_json(output/'manifest.json',child);freeze_sources(output,sources)
        write_json(output/'state.json',dict(status='PREPARED_NOT_RUN',expected=len(new_entries),completed=0))
        return child
    finally:
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
