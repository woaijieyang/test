"""Audit Follower coverage and strict float32 camera-XZ correspondences; never adopt inferred identities."""
import os,sys,json,gzip,struct,collections,datetime,hashlib
from pathlib import Path
assert os.environ.get('CASE1_PROTECTION');os.environ['CUDA_VISIBLE_DEVICES']='';os.nice(15)
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
B=R/'outputs/landmark-connectivity';O=B/'follower-source-correspondence-v1';O.mkdir(exist_ok=False);atomic_json(O/'process.json',{'pid':os.getpid(),'start_ticks':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]});identity_path=B/'published-identity-nodes.json';identity=json.loads(identity_path.read_text())['nodes'];native_path=B/'native-mapping.json';native={(r['scene'],r['node']):r['native_candidates'] for r in json.loads(native_path.read_text())['nodes']};old_path=B/'official-GT-alignment-v3.json';old=json.loads(old_path.read_text());missing={(r['split'],str(int(r['instruction_id']))) for r in old['records'] if r['status']=='NO_OFFICIAL_PATH'};assert len(missing)==8034
f32=lambda x:struct.unpack('<f',struct.pack('<f',float(x)))[0]
by_camera=collections.defaultdict(list)
for r in identity:
 c=r['camera_position'];by_camera[(r['scene'],f32(c[0]),f32(c[2]))].append(r)
sources=[];summaries=[];matches={};ambiguous=0;direct_missing=set();known_equal=known_different=0;all_follower_ids_in_guide=True
for split in ['train','val_seen','val_unseen']:
 guide_path=R/'data/datasets/RxR_VLNCE_v0'/split/(split+'_guide.json.gz');follower_path=guide_path.with_name(split+'_follower.json.gz');guides=json.load(gzip.open(guide_path,'rt'))['episodes'];guide_ids={str(int(e['instruction']['instruction_id'])):e for e in guides};followers=json.load(gzip.open(follower_path,'rt'))['episodes'];ids=set();missing_guide_ids=set();text_or_scene_conflicts=[];refcount=0
 for e in followers:
  iid=str(int(e['instruction']['instruction_id']));ids.add(iid);scene=Path(e['scene_id']).stem
  if (split,iid) in missing:direct_missing.add(split+':'+iid)
  if iid not in guide_ids:missing_guide_ids.add(iid)
  else:
   g=guide_ids[iid]
   if g['scene_id']!=e['scene_id'] or g['instruction']['instruction_text'].strip().strip('"').strip()!=e['instruction']['instruction_text'].strip().strip('"').strip():text_or_scene_conflicts.append({'instruction_id':iid,'follower_episode_id':e['episode_id']})
  for index,q in enumerate(e.get('reference_path',[])):
   refcount+=1;candidates=[r for r in by_camera.get((scene,f32(q[0]),f32(q[2])),[]) if 0<=r['camera_position'][1]-q[1]<=2]
   if len(candidates)>1:ambiguous+=1;continue
   if not candidates:continue
   r=candidates[0];point=[float(x) for x in q];key=(scene,r['node'],tuple(point));entry=matches.setdefault(key,{'scene':scene,'node':r['node'],'position':point,'camera_position':r['camera_position'],'previous_identity_method':r['method'],'has_guide_native_mapping':(scene,r['node']) in native,'occurrences':0,'examples':[]});entry['occurrences']+=1
   if len(entry['examples'])<3:entry['examples'].append({'split':split,'follower_episode_id':str(e['episode_id']),'instruction_id':iid,'reference_index':index})
   if (scene,r['node']) in native:
    equal=any(tuple(f32(x) for x in a)==tuple(f32(x) for x in q) for a in native[(scene,r['node'])]);known_equal+=equal;known_different+=not equal;entry['matches_known_guide_position']=equal
  if len(ids)%5000==0:atomic_json(O/'state.json',{'status':'READING_FOLLOWER_REFERENCES','split':split,'unique_instruction_ids_seen':len(ids),'unique_coordinate_matches':len(matches)})
 all_follower_ids_in_guide &= not missing_guide_ids;summaries.append({'split':split,'guide_episodes':len(guides),'follower_episodes':len(followers),'follower_instruction_ids':len(ids),'follower_ids_absent_from_guide':sorted(missing_guide_ids),'instruction_text_or_scene_conflicts':text_or_scene_conflicts,'follower_reference_points':refcount});sources.extend([{'path':str(guide_path),'sha256':digest(guide_path)},{'path':str(follower_path),'sha256':digest(follower_path)}]);del guides,followers,guide_ids
new=[r for r in matches.values() if not r['has_guide_native_mapping']];unresolved=[r for r in new if r['previous_identity_method']=='UNRESOLVED_no_direct_identity'];atomic_json(O/'candidate-correspondences.json',{'records':list(matches.values()),'limits':'Exactfloat32 cameraXZ plus0..2m downward range correspondence is an inferred geometric candidate, not author-provided viewpointID. No source anchor/target identity is upgraded or changed.'});report={'status':'COMPLETE_FOLLOWER_SOURCE_COVERAGE_AND_GEOMETRIC_CORRESPONDENCE_AUDIT_NOT_REPAIR','missing_guide_instruction_records':8034,'direct_missing_guide_records_found_in_follower':sorted(direct_missing),'all_follower_instruction_ids_present_in_guide':all_follower_ids_in_guide,'splits':summaries,'sources':sources,'unique_coordinate_matches':len(matches),'known_guide_reference_occurrences_equal':known_equal,'known_guide_reference_occurrences_different':known_different,'ambiguous_camera_xz_occurrences':ambiguous,'new_relative_to_guide_mapping_nodes':len({(r['scene'],r['node']) for r in new}),'previous_unresolved_nodes_matched':len({(r['scene'],r['node']) for r in unresolved}),'new_candidates':new,'identity_sha256':digest(identity_path),'guide_mapping_sha256':digest(native_path),'old_alignment_sha256':digest(old_path),'candidate_table_sha256':digest(O/'candidate-correspondences.json'),'script_sha256':digest(__file__),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limits':'Follower episodes have no trajectory_id field; do not invent a direct path-ID match. Even matching instructions/references does not prove original landmark order, sourcebody clearance or native motion. Geometry correspondences remain proposals under existing bounds, not new trusted anchors or formal evaluation data.'};atomic_json(O/'validation.json',report);atomic_json(O/'state.json',{'status':'COMPLETE','direct_missing_matches':len(direct_missing),'new_nodes':report['new_relative_to_guide_mapping_nodes'],'unresolved_nodes':report['previous_unresolved_nodes_matched']});print({k:report[k] for k in ['all_follower_instruction_ids_present_in_guide','unique_coordinate_matches','known_guide_reference_occurrences_equal','known_guide_reference_occurrences_different','new_relative_to_guide_mapping_nodes','previous_unresolved_nodes_matched']})
