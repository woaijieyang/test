"""Reproducible protected summary of the four missing-node stage proxies."""
import os,sys,json,struct
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION')
R=Path.cwd();sys.path.insert(0,str(R/'scripts'));from workspace import atomic_json,digest
import numpy as np
B=R/'outputs/landmark-connectivity';O=B/'pRbA3pwrgk9-native-default-stage-v1';v=json.loads((O/'validation.json').read_text());assert v['stage_control_match'];cs,ch,H,climb,radius,region,bx,by,bz=v['native_build_config'];nodes=[r for r in json.loads((B/'pRbA3pwrgk9-bounded-source-native-default-v1/validation.json').read_text())['nodes'] if not r['components']];stages={};inputs={}
for name in ['low_hanging','ledge','low_height','compacted','eroded','regions']:
 israw=name in ['low_hanging','ledge','low_height'];path=O/('native-1-'+name+('-raw.bin' if israw else '-graph.bin'));blob=path.read_bytes();n=struct.unpack('<i',blob[:4])[0];a=np.frombuffer(blob,dtype='<i4',offset=4).reshape(n,5 if israw else 11);inputs[path.name]=digest(path)
 if israw:
  top=np.full(n,65535);same=np.all(a[:-1,:2]==a[1:,:2],axis=1);top[:-1]=np.where(same,a[1:,2],65535);pos=np.column_stack((bx+(a[:,0]+.5)*cs,by+a[:,3]*ch,bz+(a[:,1]+.5)*cs));clearance=top-a[:,3]
 else:pos=np.column_stack((bx+(a[:,1]+.5)*cs,by+a[:,3]*ch,bz+(a[:,2]+.5)*cs));clearance=a[:,4]
 stages[name]=(a,pos,clearance,israw)
rows=[]
for node in nodes:
 anchor=np.array(node['anchor']);r={'node':node['node'],'anchor':node['anchor'],'stages':{}}
 for name,(a,pos,clearance,israw) in stages.items():
  delta=np.maximum(abs(pos-anchor)-np.array([3*cs,2*ch,3*cs]),0);mask=(np.sum(delta**2,axis=1)<=.25)&(a[:,4 if israw else 5]!=0);r['stages'][name]={'candidate_spans':int(mask.sum()),'clearance_lt_H':int(np.sum(mask&(clearance<H))),'clearance_eq_H':int(np.sum(mask&(clearance==H))),'clearance_gt_H':int(np.sum(mask&(clearance>H)))}
  if name=='regions':r['stages'][name]['nonzero_region']=int(np.sum(mask&(a[:,6]!=0)))
 rows.append(r)
prior=json.loads((O/'missing-node-stage-summary.json').read_text());assert rows==prior['rows'];atomic_json(O/'missing-node-stage-summary-protected.json',{'status':'PASS_REPRODUCED_STAGE_PROXY_COUNTS_NOT_ACCEPTANCE','rows':rows,'config':v['native_build_config'],'native_control_receipt_sha256':digest(O/'validation.json'),'raw_input_hashes':inputs,'script_sha256':digest(__file__),'protection':json.loads(os.environ['CASE1_PROTECTION']),'limits':'Analytical padded envelope only, not relaxed source bounds or accepted positions. Surviving spans without retained regions do not prove that deleting region filters would reconnect them.'});print('PASS',len(rows))
