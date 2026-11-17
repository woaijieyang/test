"""Explain an existing actual contact without changing trajectories or gates."""
from collections import Counter
import json
import math
import os
from pathlib import Path
import time
from oracle.adapters.habitat.assets import resolve
from oracle.common.artifacts import content_digest, digest, owned_output, write_json, package_sources, freeze_sources
from oracle.verification.source_scene import SourceScene


def contact_category(before, after, sweep):
    if before: return 'actual_before_state_contact'
    if after: return 'actual_after_state_contact'
    if sweep: return 'linear_sweep_only_contact'
    return 'contact_not_reproduced'


def diagnose(case_root, run_path, output):
    import psutil
    usage=psutil.cpu_percent(interval=1,percpu=True)
    cpus=[i for i in sorted(os.sched_getaffinity(0))[:64] if usage[i]<15]
    if not cpus:raise RuntimeError('No idle CPU')
    os.sched_setaffinity(0,[min(cpus,key=lambda i:usage[i])]);os.nice(10)
    started=time.perf_counter();root=Path(case_root).resolve();run=owned_output(root,run_path);output=owned_output(root,output)
    manifest=json.loads((run/'manifest.json').read_text());validation=json.loads((run/'validation.json').read_text())
    if not validation['complete'] or digest(run/'manifest.json')!=validation['manifest_sha256']:raise ValueError('Incomplete or changed run')
    tasks={t['task_key']:t for t in manifest['tasks']};selected=[]
    for row in validation['results']:
        if row['status']=='PASS_ORDERED_NATIVE_AND_RATIONAL_REPLAY':continue
        item=tasks[row['task_key']]
        if digest(item['path'])!=item['sha256']:raise ValueError('Task drift')
        task=json.loads(Path(item['path']).read_text());selected.append((task['scene'],task,row))
    output.mkdir(parents=True,exist_ok=False);_,sources=package_sources();freeze_sources(output,sources)
    scene=None;last_scene=None;records=[];queries=checks=0
    for scene_id,task,row in sorted(selected,key=lambda x:(x[0],x[1]['task_key'])):
        if digest(row['result_path'])!=row['result_sha256'] or digest(row['audit_path'])!=row['audit_sha256']:raise ValueError('Evidence drift')
        record=json.loads(Path(row['result_path']).read_text());audit=json.loads(Path(row['audit_path']).read_text())
        if record['task_sha256']!=content_digest(task) or audit['task_sha256']!=record['task_sha256']:raise ValueError('Binding mismatch')
        entry={'task_key':task['task_key'],'failure':record['failure'],'detail':record['detail'],
               'source_result_sha256':row['result_sha256'],'source_audit_sha256':row['audit_sha256'],
               'original_acceptance_unchanged':True,'native_actions_run_in_this_diagnostic':0}
        alert=next(iter(audit['physical_alerts']),None)
        if alert is None:
            entry['category']='no_physical_alert_in_existing_audit';records.append(entry);continue
        i=alert['index'];before=record['positions'][max(0,i-1)];after=record['positions'][i]
        entry.update(action_index=i,action=record['actions'][i-1] if i else None,before=before,after=after,
                     delta_height_m=after[1]-before[1],horizontal_displacement_m=math.hypot(after[0]-before[0],after[2]-before[2]))
        if record['failure']!='source_geometry_contact':
            entry['category']='native_motion_limit';entry['audit_alert']=alert;records.append(entry);continue
        if last_scene!=scene_id:
            if scene is not None:queries+=scene.queries;checks+=scene.triangle_checks
            _,geometry=resolve(root,task);scene=SourceScene(geometry['receipt_path'],geometry['receipt_sha256'],record['protocol'],catalog=geometry);last_scene=scene_id
        at_before=scene.contact(before,before,arithmetic='rational_hull')
        at_after=scene.contact(after,after,arithmetic='rational_hull')
        swept=scene.contact(before,after,arithmetic='rational_hull')
        entry.update(category=contact_category(at_before,at_after,swept),before_contact=at_before,after_contact=at_after,sweep_contact=swept,
                     geometry_sha256=scene.geometry_sha256,
                     interpretation='Endpoint contact concerns an actually recorded state; sweep-only contact depends on the unchanged straight interpolation model. Neither proves all routes impossible; no alternate step curve adopted.')
        records.append(entry)
    if scene is not None:queries+=scene.queries;checks+=scene.triangle_checks
    if len(records)!=len(selected) or len({r['task_key'] for r in records})!=len(records):raise ValueError('Failure coverage incomplete')
    write_json(output/'failure-contact-causes.json',records)
    summary={'status':'CONTACT_EXPLANATIONS_COMPLETE_GATES_UNCHANGED','failed_tasks':len(records),
             'categories':dict(Counter(r['category'] for r in records)),
             'primitive_categories':dict(Counter(str(r.get('action'))+':'+r['category'] for r in records)),
             'positive_contact_reproduction_disagreements':sum(r['category']=='contact_not_reproduced' for r in records),
             'queries':queries,'triangle_checks':checks,'wall_seconds':time.perf_counter()-started,
             'native_actions':0,'source_validation_sha256':digest(run/'validation.json'),
             'ledger_sha256':digest(output/'failure-contact-causes.json'),'diagnoser_sha256':digest(__file__),
             'limitations':'Same native geometry and straight cylinder model as the independent audit, endpoint/sweep distinction only; physical support interpretation may remain unknown.'}
    write_json(output/'validation.json',summary);return summary
