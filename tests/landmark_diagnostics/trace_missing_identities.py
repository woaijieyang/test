import gzip,json,collections,sys,zipfile,datetime
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'scripts'))
from workspace import ROOT,atomic_json,digest
raw=Path('/data/zy/vln/data/raw_data/landmark-rxr');ce=Path('/data/zy/vln/data/raw_data/eval_annotations/rxr_vlnce_v0');report={'splits':{},'missing_records':[],'text_differences':[],'sources':[]}
for split in ('train','val_seen','val_unseen'):
 source=raw/f'LandmarkRxR_{split}.json';guide=ce/split/f'{split}_guide.json.gz';follower=ce/split/f'{split}_follower.json.gz';rows=json.loads(source.read_text());eps=json.load(gzip.open(guide,'rt'))['episodes'];byid={str(e['instruction']['instruction_id']):e for e in eps};bypath=collections.defaultdict(list)
 for e in eps:bypath[str(e['trajectory_id'])].append(e)
 followers=json.load(gzip.open(follower,'rt'))['episodes'] if follower.exists() else [];byf=collections.defaultdict(list)
 for e in followers:byf[str(e['instruction']['instruction_id'])].append(e)
 counts=collections.Counter()
 for row in rows:
  key=str(row['instruction_id']);e=byid.get(key);counts['raw']+=1
  if e is None:
   siblings=bypath.get(str(row['path_id']),[]);fs=byf.get(key,[]);counts['missing_guide_id']+=1;counts['missing_id_with_same_guide_path']+=bool(siblings);counts['missing_id_with_follower']+=bool(fs)
   report['missing_records'].append({'split':split,'instruction_id':key,'path_id':str(row['path_id']),'scene':row['scan'],'guide_trajectory_matches':[str(x['episode_id']) for x in siblings],'follower_matches':[{'episode_id':str(x['episode_id']),'reference_path':x['reference_path'],'scene_id':x['scene_id']} for x in fs]})
  elif row['instruction']!=e['instruction']['instruction_text']:
   a=row['instruction'];b=e['instruction']['instruction_text'];kind='boundary_quotes_only' if a.strip().strip('"').strip()==b.strip().strip('"').strip() else 'whitespace_only' if ' '.join(a.split())==' '.join(b.split()) else 'other_text_difference';counts[kind]+=1
   report['text_differences'].append({'split':split,'instruction_id':key,'kind':kind,'landmark_text':a,'ce_text':b})
 report['splits'][split]=dict(counts);print(split,dict(counts),flush=True)
 for q in (source,guide,follower):
  if q.exists():report['sources'].append({'path':str(q),'sha256':digest(q)})
native=json.loads(Path('outputs/landmark-connectivity/native-mapping.json').read_text());known={(r['scene'],r['node']) for r in native['nodes']};audit=json.loads(Path('outputs/landmark-connectivity/published-graphs-audit.json').read_text());report['missing_viewpoints']=[{'scene':s['scene'],'node':n,'has_official_guide_reference':(s['scene'],n) in known} for s in audit['scenes'] for n in s['missing_required_ids']];report['missing_viewpoint_counts']={'total':len(report['missing_viewpoints']),'has_official_guide_reference':sum(x['has_official_guide_reference'] for x in report['missing_viewpoints'])};report['auditor_sha256']=digest(__file__);report['status']='TRACE_COMPLETE_NOT_REPAIR_ACCEPTANCE';atomic_json(ROOT/'outputs/landmark-connectivity/missing-identities.json',report);print(report['missing_viewpoint_counts'])
