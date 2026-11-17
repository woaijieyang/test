"""Verify complete scoped task retention and immutable controls after projection batch."""
import os,sys,json,time,datetime,collections,fcntl
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'));from workspace import atomic_json,digest
B=R/'outputs/landmark-connectivity';O=B/'bounded-component-surface-batch-v2';lock=(O/'independent.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);source=json.loads((O/'process.json').read_text());atomic_json(O/'independent-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]})
def state(status,**kw):atomic_json(O/'independent-state.json',{'status':status,'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw})
try:
 state('WAITING_FOR_COMPLETE_BATCH')
 while not (O/'validation.json').exists():
  p=Path('/proc',str(source['pid']),'stat');v=p.read_text().rsplit(')',1)[1].split() if p.exists() else [];assert v and v[19]==str(source['start_ticks']) and v[0] not in 'ZX','Source batch incomplete';time.sleep(60)
 report=json.loads((O/'validation.json').read_text());manifest=json.loads((O/'manifest.json').read_text());assert report['manifest_sha256']==digest(O/'manifest.json');parent=B/'full-native-v11/manifest.json';assert digest(parent)==manifest['parent_manifest_sha256'];m=json.loads(parent.read_text());prior={t['task_key']:t for t in m['tasks']};held=set(json.loads((B/'constraint-blockers.json').read_text())['task_keys']);seen=set();total=collections.Counter();positive=[];receipts=[]
 for record in report['scene_receipts']:
  vp=Path(record['path']);assert digest(vp)==record['sha256'];v=json.loads(vp.read_text());assert v['parent_manifest_sha256']==manifest['parent_manifest_sha256'] and v['script_sha256']==manifest['sources'][str(R/'tests/landmark_diagnostics/probe_component_surface_scene_v2.py')];assert v['projection_helper_sha256']==manifest['sources'][str(R/'tests/landmark_diagnostics/bounded_triangle_projection.py')];cp=vp.parent/'candidate_tasks.json';candidates={t['task_key']:t for t in json.loads(cp.read_text())['tasks']};rows={r['task_key']:r for r in v['rows']};expected={k for k,t in prior.items() if t['scene']==record['scene']};assert len(rows)==len(v['rows'])==len(candidates)==v['tasks'] and set(rows)==set(candidates)==expected and not seen.intersection(expected);seen.update(expected)
  for key,row in rows.items():
   t=prior[key];new=candidates[key];total[row['status']]+=1
   if row['status'] in ['UNCHANGED_READY_CONTROL','BLOCKED_PRESERVED','HELD114_UNMODIFIED']:assert new==t
   else:
    assert row['status']=='RECOVERED_STATIC_CANDIDATE_NOT_ACCEPTED' and key not in held and t['status']=='STATIC_BLOCKED_PRESERVED';assert {k:v for k,v in new.items() if k not in ['targets','status']}=={k:v for k,v in t.items() if k not in ['targets','status']};assert len(new['targets'])==len(t['targets'])==len(row['choices']);positive.append({'scene':record['scene'],'task_key':key,'candidate_path':str(cp)})
   if key in held:assert row['status']=='HELD114_UNMODIFIED'
  receipts.append({'validation_path':str(vp),'validation_sha256':digest(vp),'candidate_tasks_path':str(cp),'candidate_tasks_sha256':digest(cp)})
 assert len(report['scene_receipts'])==len(manifest['scenes'])==44 and set(record['scene'] for record in report['scene_receipts'])==set(manifest['scenes']);assert dict(total)==report['counts'];state('PASS_SCOPED_COVERAGE_IDENTITIES_CONTROLS_NOT_ADOPTION',scene_count=44,task_count=len(seen),positive_candidates=len(positive));atomic_json(O/'independent-validation.json',{'status':'PASS_SCOPED_COVERAGE_IDENTITIES_CONTROLS_NOT_ADOPTION','scene_count':44,'scoped_task_count':len(seen),'counts':dict(total),'positive_candidates':positive,'scene_receipts':receipts,'source_validation_sha256':digest(O/'validation.json'),'script_sha256':digest(__file__),'limits':'Checks complete declared scene coverage, immutable previous controls/blocked/held rows and exact code/input binding. It does not replace independent geometry/body/semantics/native-motion verification of any recovered candidate.'});print(dict(total))
except Exception as e:state('FAILED',error=repr(e));raise
