"""Apply the explicitly approved 106-task expansion to new, immutable derivatives."""
import copy,datetime,json,math,os,sys
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R/'scripts'))
from workspace import atomic_json,digest
from preflight import SPECS,dataset_base,load,task_key
from build_derived_annotations import diff,compressed

def apply_fields(record, changes):
    result=copy.deepcopy(record)
    seen=set()
    for change in changes:
        field=change['field']
        if field in seen:raise ValueError('Duplicate field')
        seen.add(field);parts=field.strip('/').split('/');node=result
        for part in parts[:-1]:node=node[int(part)] if isinstance(node,list) else node[part]
        key=int(parts[-1]) if isinstance(node,list) else parts[-1]
        if node[key]!=change['before']:raise ValueError('Input value drift: '+field)
        node[key]=change['after']
    if diff(record,result)!=changes:raise ValueError('Unexpected field differences')
    return result

def main():
    assert os.environ.get('CASE1_PROTECTION')
    preview=R/'outputs/connectivity/formal-endpoint-repair-preview-v2'
    pins={'validation.json':'b5ce427a24b750e539b6f7e26d21893a75f5df42d0ac8b73a15aa8c9d2f39057','field-diff.json':'f5064172a32451cf6c7afc11ff6510d3cd4fbf0d4ce1c2d9df8685e432abceb2','independent-field-prospective-validation.json':'0974456da986b9d9113436109cf271d01262521738f6db8b306c734f26577889'}
    assert all(digest(preview/n)==sha for n,sha in pins.items())
    proposal=json.loads((preview/'validation.json').read_text());fields=json.loads((preview/'field-diff.json').read_text());check=json.loads((preview/'independent-field-prospective-validation.json').read_text())
    assert check['status']=='PASS_ALL_PROSPECTIVE_ENDPOINTS_NOT_APPLIED'
    assert digest(proposal['profile_path'])==proposal['profile_sha256']
    assert all(digest(row['path'])==row['sha256'] for row in fields['source_files'])
    changes={r['task_key']:r for r in fields['changes']};coordinates={r['task_key']:r for r in proposal['changes']};assert len(changes)==len(coordinates)==106
    out=R/'data/derived/annotations/awarevln-endpoint115-v1';receipt=R/'outputs/connectivity/endpoint115-materialized-v1'
    assert not out.exists() and not receipt.exists(), 'Immutable destination already exists'
    planned=[];reports=[];inputs={};counts={};raw_changes={};records=[]
    for ds,spec in SPECS.items():
        base=dataset_base(ds);ap=base/spec[1];gp=base/spec[2]
        original=load(ap);gt_original=load(gp);annotations=copy.deepcopy(original);gt=copy.deepcopy(gt_original)
        rawbase=R/'data/datasets'/spec[0]/'val_unseen';raw=load(rawbase/spec[1]);rawgt=load(rawbase/spec[2])
        for p in [ap,gp,rawbase/spec[1],rawbase/spec[2]]:inputs[str(p)]=digest(p)
        selected=[]
        for i,before in enumerate(original['episodes']):
            if ds=='rxr' and before['instruction']['language']!='en-US':continue
            key=task_key(ds,before);eid=str(before['episode_id'])
            if key in changes:
                row=changes[key];assert row['dataset']==ds and row['episode_id']==eid
                annotations['episodes'][i]=apply_fields(before,row['annotation_changes']);gt[eid]=apply_fields(gt_original[eid],row['gt_changes'])
                c=coordinates[key];position=next(p for p in proposal['positions'] if p['scene']==c['scene'] and p['old_position']==c['old'])
                reports.append({**row,'original_position':c['old'],'derived_position':c['proposed'],'displacement_m':math.dist(c['old'],c['proposed']),'reason':'Original endpoint intersects fixed source cylinder; bounded native projection is source-clear and connected. Exact matching reference node and start GT only.','position_evidence':position,'proposal_sha256':pins['validation.json']});selected.append(key)
            after=annotations['episodes'][i]
            records.append({'task_key':key,'dataset':ds,'episode_id':eid,'instruction_id':after.get('instruction',{}).get('instruction_id'),'scene_id':after['scene_id'],'start_position':after['start_position'],'start_rotation':after['start_rotation'],'goals':after['goals'],'reference_path':after.get('reference_path',[])})
        assert set(selected)=={k for k,v in changes.items() if v['dataset']==ds}
        assert len(original['episodes'])==len(raw['episodes'])
        raw_changes[ds]=[]
        for before,after in zip(raw['episodes'],annotations['episodes']):
            delta=diff(before,after)
            if delta:raw_changes[ds].append({'task_key':task_key(ds,after),'annotation_changes':delta,'gt_changes':diff(rawgt[str(after['episode_id'])],gt[str(after['episode_id'])])})
        counts[ds]={'new_changes':len(selected),'total_changes_from_original':len(raw_changes[ds]),'all_episodes':len(annotations['episodes']),'selected_episodes':sum(r['dataset']==ds for r in records)}
        assert counts[ds]['total_changes_from_original']=={'r2r':45,'rxr':70}[ds]
        root=out/spec[0]/'val_unseen';planned.extend([(root/spec[1],annotations),(root/spec[2],gt)])
    assert len(reports)==106 and len(records)==3062 and len({r['task_key'] for r in records})==3062
    assert sum(bool(r['gt_changes']) for r in reports)==63
    assert all(digest(p)==sha for p,sha in inputs.items())
    out.mkdir(parents=True);receipt.mkdir(parents=True)
    for p,data in planned:p.parent.mkdir(parents=True,exist_ok=True);compressed(p,data);assert not diff(data,load(p))
    follower=dataset_base('rxr')/'val_unseen_follower_gt.json.gz';inputs[str(follower)]=digest(follower)
    link=out/SPECS['rxr'][0]/'val_unseen'/follower.name;link.symlink_to(follower.resolve())
    protocol={'protocol_id':'awarevln-endpoint115-v1','parent_protocol_sha256':digest(R/'configs/annotation-protocol.json'),'profile_path':proposal['profile_path'],'profile_sha256':proposal['profile_sha256'],'dataset_roots':{ds:str((out/spec[0]).relative_to(R)) for ds,spec in SPECS.items()},'newly_authorized_tasks':106,'total_changed_tasks':115,'authorization':'User explicitly approved new106 derived annotation repairs on2026-10-17; originals unchanged; all strict validation before new formal identity/push.','status':'MATERIALIZED_PENDING_FULL_MOTION_AND_INDEPENDENT_VALIDATION','active_formal_configuration_changed':False}
    atomic_json(out/'protocol.json',protocol);atomic_json(out/'changes.json',{'new106':reports,'all115_against_original':raw_changes});atomic_json(out/'tasks.json',records)
    outputs={str(p):digest(p) for p,_ in planned};outputs[str(link)]=digest(link)
    assert all(digest(p)==sha for p,sha in inputs.items())
    result={'status':protocol['status'],'protocol_path':str(out/'protocol.json'),'protocol_sha256':digest(out/'protocol.json'),'changes_path':str(out/'changes.json'),'changes_sha256':digest(out/'changes.json'),'tasks_path':str(out/'tasks.json'),'tasks_sha256':digest(out/'tasks.json'),'source_files_unchanged':inputs,'derived_files':outputs,'counts':counts,'preview_bindings':pins,'builder_sha256':digest(__file__),'time':datetime.datetime.now().astimezone().isoformat()}
    atomic_json(out/'manifest.json',result);atomic_json(receipt/'validation.json',result);print(json.dumps(counts))
if __name__=='__main__':main()
