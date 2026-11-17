"""Reconcile all33954 exact-source rows and independently recompute recorded contact witnesses."""
import os,sys,json,gzip,hashlib,math,collections,datetime,struct
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1';os.nice(15)
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'tests/landmark_diagnostics')]
from workspace import atomic_json,digest
from swept_cylinder_reference import triangle_linear_sweep_distance
import numpy as np,psutil
u=psutil.cpu_percent(interval=1,percpu=True);eligible=[i for i in sorted(os.sched_getaffinity(0))[:64] if i not in [1,7,15,16]];os.sched_setaffinity(0,[min(eligible,key=lambda i:u[i])])
B=R/'outputs/landmark-connectivity';O=B/'full-native-source-exact-v1';out=O/'independent-coverage.json';assert not out.exists();atomic_json(O/'coverage-process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});summary=json.loads((O/'validation.json').read_text());manifest=json.loads((O/'manifest.json').read_text());parent=B/'full-native-v11';m=json.loads((parent/'manifest.json').read_text());assert digest(parent/'manifest.json')==manifest['parent_manifest_sha256'] and summary['manifest_sha256']==digest(O/'manifest.json');assert manifest['settings']=={'height':1.5,'radius':.1,'foot_epsilon':1e-5,'radial_threshold':.1-1e-6,'continuous_interpretation':'exact_continuous_linear','deduplication':'exact coordinate tuples, no rounding'};tasks={t['task_key']:t for t in m['tasks']};assert len(tasks)==33954;seen=set();counts=collections.Counter();cross=collections.Counter();actions=examples=0;scenes=set()
try:
 for receipt in summary['scene_receipts']:
  p=Path(receipt['path']);assert p.resolve().is_relative_to((O/'scenes').resolve()) and digest(p)==receipt['sha256'];d=json.loads(p.read_text());sc=d['scene'];assert sc not in scenes;scenes.add(sc);assert d['manifest_sha256']==digest(O/'manifest.json') and d['worker_sha256']==manifest['worker_sha256'];expected={k for k,t in tasks.items() if t['scene']==sc};assert {r['task_key'] for r in d['rows']}==expected and len(d['rows'])==len(expected)
  native=manifest['native_geometry'][sc];assert digest(native['native_geometry_path'])==native['native_geometry_sha256']==d['native_geometry_sha256'];raw=Path(native['native_geometry_path']).read_bytes();nv,nt=struct.unpack('<ii',raw[:8]);verts=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=8).reshape(nv,3);indices=np.frombuffer(raw,dtype='<i4',count=nt*3,offset=8+nv*12).reshape(nt,3);tri=verts[indices].astype(float);cache={};old=manifest['old_screen_receipts'][sc];assert digest(old['path'])==old['sha256'];old_data=json.loads(Path(old['path']).read_text());oldrows={r['task_key']:r for r in old_data['rows']}
  def dist(j,a,b):
   key=(j,tuple(a),tuple(b))
   if key not in cache:cache[key]=triangle_linear_sweep_distance(tri[j],np.array(a),np.array(b))
   return cache[key]
  for row in d['rows']:
   key=row['task_key'];assert key not in seen;seen.add(key);task=tasks[key];assert row['source_record_sha256']==task['source_record_sha256'];rp=Path(row['result_path']);assert rp.resolve().is_relative_to(parent.resolve()) and digest(rp)==row['result_sha256'];result=json.loads(rp.read_text());assert result['task_key']==key and result['source_record_sha256']==task['source_record_sha256'] and result['status']==row['native_status'];assert row['old_sampled_status']==oldrows[key]['status'] and row['old_geometry_kind']==old_data['geometry_kind']
   if task['status']=='STATIC_BLOCKED_PRESERVED':assert row['status']=='STATIC_BLOCKED_PRESERVED' and row['actions']==0 and result['status']=='STATIC_BLOCKED_PRESERVED'
   else:
    tp=Path(row['trace_path']);assert tp.resolve().is_relative_to(parent.resolve()) and digest(tp)==row['trace_sha256']==result['trace_sha256'];trace=json.load(gzip.open(tp,'rt'));assert trace['task_key']==key and trace['targets']==task['targets'] and trace['manifest_sha256']==manifest['parent_manifest_sha256'];positions=trace['positions'];assert len(positions)==len(trace['actions'])+1==row['positions_checked'] and row['actions']==len(trace['actions']);actions+=row['actions'];assert 0<=row['actual_position_contacts']<=len(positions) and 0<=row['continuous_segment_contacts']<=row['actions'];expected_status='ACTUAL_POSITION_SOURCE_CONTACT' if row['actual_position_contacts'] else 'CONTINUOUS_INTERIOR_SOURCE_CONTACT' if row['continuous_segment_contacts'] else 'EXACT_LINEAR_SOURCE_CLEAR';assert row['status']==expected_status and (expected_status!='EXACT_LINEAR_SOURCE_CLEAR')==bool(row['contact_examples'])
    for sample in row['contact_examples']:
     j=sample['native_triangle'];assert 0<=j<nt and sample['distance']<.1-1e-6
     if sample['kind']=='ACTUAL_POSITION':
      q=positions[sample['position_index']];assert math.dist(q,sample['position'])<1e-12;values=[dist(j,q,q)]
     else:
      i=sample['action_index'];assert 1<=i<len(positions);a,b=positions[i-1],positions[i];assert math.dist(a,sample['start'])<1e-12 and math.dist(b,sample['end'])<1e-12
      if sample['kind']=='ENDPOINT_CONTACT_WITNESS':values=[dist(j,a,a),dist(j,b,b)]
      else:assert sample['kind']=='EXACT_CONTINUOUS_INTERIOR';values=[dist(j,a,b)]
     assert min(abs(value-sample['distance']) for value in values)<1e-10 and min(values)<.1-1e-6;examples+=1
   counts[row['status']]+=1;cross[row['old_sampled_status']+' -> '+row['status']]+=1
  atomic_json(O/'coverage-state.json',{'status':'RUNNING','scenes':len(scenes),'tasks':len(seen),'witnesses_recomputed':examples})
 assert seen==set(tasks) and len(scenes)==71 and dict(counts)==summary['counts'] and dict(cross)==summary['old_sampled_to_new_exact'] and actions==summary['actions'];assert counts['STATIC_BLOCKED_PRESERVED']==3411;atomic_json(out,{'status':'PASS_FULL_COVERAGE_IDENTITIES_AND_RECORDED_NATIVE_CONTACT_WITNESSES_NOT_ACCEPTANCE','tasks':33954,'scenes':71,'counts':dict(counts),'old_sampled_to_new_exact':dict(cross),'actions_bound':actions,'recorded_contact_witnesses_independently_recomputed':examples,'summary_sha256':digest(O/'validation.json'),'script_sha256':digest(__file__),'sweep_helper_sha256':digest(R/'tests/landmark_diagnostics/swept_cylinder_reference.py'),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'All row/trace identities and complete counts reconciled; each stored positive witness independently recalculated from native triangle geometry. Not a second exhaustive all-triangle search of every clear segment, not new native replay, not dataset acceptance or physical impossibility proof.'});atomic_json(O/'coverage-state.json',{'status':'COMPLETE','tasks':33954,'scenes':71,'witnesses_recomputed':examples});print(out)
except Exception as e:atomic_json(O/'coverage-state.json',{'status':'FAILED','error':repr(e),'tasks':len(seen)});raise
