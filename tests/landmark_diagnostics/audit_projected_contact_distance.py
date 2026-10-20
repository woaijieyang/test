"""Audit recorded source-contact claims against exact convex-hull orientation."""
import os,sys,json,math,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.nice(15)
sys.path[:0]=[str(Path.cwd()/'scripts'),str(Path.cwd()/'tests/landmark_diagnostics')]
from workspace import ROOT,atomic_json,digest
from projected_distance_reference import projected_distance
import numpy as np,psutil
usage=psutil.cpu_percent(interval=1,percpu=True);os.sched_setaffinity(0,[min(sorted(os.sched_getaffinity(0))[:64],key=lambda i:usage[i])])
helper=ROOT/'tests/landmark_diagnostics/audit_remaining_body_clearance.py';s=helper.read_text();exec(s[s.index('def clip('):s.index('records=[]')])
p=np.array([.11,0.,.11]);poly=[np.array([0.,0.,0.]),np.array([.02,0.,.02]),np.array([.02,1.5,.02])];old=distance(poly,p);new=projected_distance(poly,p);assert old==0 and abs(new-math.hypot(.09,.09))<1e-12
B=ROOT/'outputs/landmark-connectivity';entries=[];checked=set();files=[]
for f in (B/'recast626-unresolved-paired-v1').glob('train-*.json'):
 d=json.loads(f.read_text());files.append({'path':str(f),'sha256':digest(f)});groups=[('probe',probe['bad_samples']) for probe in d['probes']]
 if 'old_plan_new_mesh' in d:groups += [('old_plan',step['samples']) for step in d['old_plan_new_mesh']['bad_steps']]
 for kind,samples in groups:
  for sample in samples:
   q=np.array(sample['position'])
   for c in sample['contacts']:
    key=(d['task_key'],kind,tuple(q),c['triangle'])
    if key in checked:continue
    checked.add(key);poly=clip([np.array(x) for x in c['triangle_vertices']],q[1]+1e-5,True)
    if len(poly)<3:continue
    poly=clip(poly,q[1]+1.5,False)
    if len(poly)<3:continue
    prior=distance(poly,q);exact=projected_distance(poly,q)
    if prior<.1-1e-6 and exact>=.1-1e-6:entries.append({'task_key':d['task_key'],'kind':kind,'position':q.tolist(),'actual_endpoint':sample['endpoint'],'triangle':c['triangle'],'triangle_vertices':c['triangle_vertices'],'prior_distance':prior,'exact_distance':exact})
atomic_json(B/'projected-distance-contact-audit-v1.json',{'status':'GEOMETRY_HELPER_DIAGNOSTIC','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'synthetic_counterexample':{'prior':old,'exact':new,'expected':math.hypot(.09,.09)},'recorded_contacts_checked':len(checked),'false_contact_claims':entries,'helper_sha256':digest(helper),'oracle_sha256':digest(ROOT/'tests/landmark_diagnostics/projected_distance_reference.py'),'script_sha256':digest(__file__),'inputs':files,'limits':'Exact orientation fixes degenerate/near-degenerate projection point-in-polygon semantics, not a tolerance change. A false individual contact does not make a whole pose/path valid; other contacts and actual motion remain to check.'});print('checked',len(checked),'false',len(entries),'tasks',sorted({r['task_key'] for r in entries}))
