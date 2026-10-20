"""Attribute all Xc task connectivity losses to the observed native construction stages."""
import os,sys,json,ast,hashlib,datetime
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION')
R=Path.cwd();sys.path[:0]=[str(R/'scripts'),str(R/'.cache/geometry-tools')]
from workspace import atomic_json,digest
import numpy as np,collections
O=R/'outputs/landmark-connectivity/native-stage-trace-xc-v3';out=O/'stage-loss-v2';out.mkdir(exist_ok=False)
v=json.loads((O/'validation.json').read_text());cs,ch,H,climb,radius,region,bx,by,bz=v['native_build_config'];H=int(H);climb=int(climb)
helper=R/'tests/landmark_diagnostics/analyze_native_stage_graphs.py';code=helper.read_text();tree=ast.parse(code);functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['read','reconstruct']];ns={'np':np,'collections':collections,'O':O,'H':H,'climb':climb,'directions':[(-1,0),(0,1),(1,0),(0,-1)],'struct':__import__('struct')};exec(compile(ast.Module(body=functions,type_ignores=[]),str(helper),'exec'),ns)
base=R/'tests/landmark_diagnostics/screen_native_components_whole_scene.py';source=base.read_text()
needle="raw=(O/'native-1-regions-graph.bin').read_bytes();n=struct.unpack('<i',raw[:4])[0];g=np.frombuffer(raw,dtype='<i4',offset=4).reshape(n,11)"
assert source.count(needle)==1
stages=[('before_ledge',ns['reconstruct'](ns['read']('native-1-low_hanging-raw.bin',5))),('after_ledge',ns['reconstruct'](ns['read']('native-1-ledge-raw.bin',5))),('before_erosion',ns['read']('native-1-compacted-graph.bin',11)),('after_erosion',ns['read']('native-1-regions-graph.bin',11))]
reports={}
try:
 for stage,g in stages:
  atomic_json(out/'state.json',{'status':'RUNNING','stage':stage})
  transformed=source.replace(needle,'g=_provided_graph;n=len(g)',1).replace("O/'whole-scene-component-screen.json'","O/'stage-loss-v2/"+stage+".json'").replace("digest(O/'native-1-regions-graph.bin')","_graph_identity")
  inputs={'before_ledge':'native-1-low_hanging-raw.bin','after_ledge':'native-1-ledge-raw.bin','before_erosion':'native-1-compacted-graph.bin','after_erosion':'native-1-regions-graph.bin'}
  env={'__name__':'stage_screen','__file__':str(base),'_provided_graph':g,'_graph_identity':digest(O/inputs[stage])}
  exec(compile(transformed,str(base)+'['+stage+']','exec'),env)
  p=out/(stage+'.json');report=json.loads(p.read_text());report.update(stage=stage,generated_execution_sha256=hashlib.sha256(transformed.encode()).hexdigest(),wrapper_sha256=digest(__file__),reconstruction_source_sha256=digest(helper));atomic_json(p,report);assert not report['old_pass_control_misses'];reports[stage]=report
 keys={r['task_key'] for r in reports['after_erosion']['tasks_results']};assert len(keys)==663;lookup={stage:{r['task_key']:r for r in report['tasks_results']} for stage,report in reports.items()};rows=[];counts=collections.Counter()
 for key in sorted(keys):
  base_row=lookup['after_erosion'][key];flags=[bool(lookup[s][key]['common_components']) for s,_ in stages]
  if base_row['prior_native_ready']:assert all(flags);label='PRIOR_NATIVE_PASS_CONTROL'
  elif flags==[False]*4:label='NO_COMMON_COMPONENT_BEFORE_LEDGE'
  elif flags==[True,False,False,False]:label='LOST_AT_LEDGE_FILTER'
  elif flags==[True,True,False,False]:label='LOST_AT_LOW_HEIGHT_FILTER'
  elif flags==[True,True,True,False]:label='LOST_AT_RADIUS_EROSION'
  else:label='NON_MONOTONE_OR_OTHER_NEEDS_REVIEW'
  counts[label]+=1;rows.append({'task_key':key,'held114':base_row['held114'],'common_component_by_stage':dict(zip([s for s,_ in stages],flags)),'classification':label})
 atomic_json(out/'validation.json',{'status':'COMPLETE_STAGE_ATTRIBUTION_NOT_ACCEPTANCE','time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scene':'XcA2TqTSSAj','records':663,'counts':dict(counts),'rows':rows,'stage_receipts':{s:digest(out/(s+'.json')) for s,_ in stages},'wrapper_sha256':digest(__file__),'limits':'Attributes disappearance of a generous graph necessary condition, not physical impossibility or proof that a filter is wrong. No numerical acceptance threshold, mesh, task or runtime changed.'});atomic_json(out/'state.json',{'status':'COMPLETE_STAGE_ATTRIBUTION_NOT_ACCEPTANCE','counts':dict(counts)});print(dict(counts))
except Exception as e:atomic_json(out/'state.json',{'status':'FAILED','error':repr(e)});raise
