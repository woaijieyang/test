"""Audit return memory against live historical pins, RGB archives, primitive traces and genuine hook-off controls."""
from pathlib import Path
from collections import Counter
import hashlib,json,gzip,tarfile,io
import numpy as np
from PIL import Image
from graphAdapter.evaluation.retrieval_audit_utils import hash_pixels
from graphAdapter.interfaces.host_slots import native_slot_indices

def rows(path):
    with gzip.open(path,'rt')as f:return [json.loads(l)for l in f]

def _audit_shared_depth(rec, support, packet_by_uid, depths, voxel_size):
    """Independently unproject the archived grid with K inverse and packet FLU poses."""
    source, target = rec["source"]["before"], rec["frame_uid"]
    assert (support["source_frame"],support["current_frame"],support["source_snapshot"])==(source,target,rec["snapshot_id"])
    old,new = packet_by_uid[source],packet_by_uid[target]
    assert old["capture_seq"] < new["capture_seq"] and old["episode_uid"] == new["episode_uid"] == rec["episode_uid"]
    if support["status"] in ("rgbd_unavailable","pose_version_unavailable"):
        assert support["shared_samples"]==0 and rec["attachment_frame"] is None
        return
    assert support["sampling_stride"]==4 and support["tolerance_m"]==voxel_size
    assert old["pose_record"]["valid"] and new["pose_record"]["valid"]
    assert old["pose_record"]["episode_instance"]==new["pose_record"]["episode_instance"]
    assert old["pose_record"]["map_version"]==new["pose_record"]["map_version"]==support["pose_map_version"]
    depth,mask=depths[source];target_z,target_mask=depths[target]
    y,x=np.where(mask[::4,::4] & np.isfinite(depth[::4,::4]) & (depth[::4,::4]>0))
    x*=4;y*=4;z=depth[y,x].astype(float)
    rays=np.linalg.solve(np.asarray(old["K"]),np.vstack((x,y,np.ones(len(z)))))
    world=np.asarray(old["pose_record"]["T_map_camera_cv"])@np.vstack((rays*z,np.ones(len(z))))
    camera=np.linalg.solve(np.asarray(new["pose_record"]["T_map_camera_cv"]),world)[:3]
    camera=camera[:,camera[2]>1.e-5]
    uvz=np.asarray(new["K"])@camera
    uv=uvz[:2]/uvz[2]
    cols,rows=np.floor(uv+.5).astype(np.int64)
    h,w=target_z.shape
    keep=(cols>=0)&(cols<w)&(rows>=0)&(rows<h)
    zz=target_z[rows[keep],cols[keep]]
    valid=target_mask[rows[keep],cols[keep]] & np.isfinite(zz) & (zz>0)
    count=int((valid & (np.abs(zz-camera[2,keep])<=voxel_size)).sum())
    assert [len(z),int(keep.sum()),int(valid.sum()),count]==[
        support[k]for k in ("source_samples","projected_pixels","comparable_depths","shared_samples")]
    assert support["status"]==("shared_surface_samples" if count else "no_shared_surface_samples")
    if count==0:assert rec["attachment_frame"] is None


def audit_approach(folder,prior):
    """Rebuild accepted history and final input from retained artifacts for a paired run."""
    run=folder.parents[3]
    old=rows(prior/'trace.jsonl.gz');new=rows(folder/'trace.jsonl.gz')
    f=rows(folder/'flow.jsonl.gz');packets=rows(folder/'observation_packets.jsonl.gz')
    def filt(trace,kind):return [z for z in trace if z['kind']==kind]
    def calls(trace):return {z['call_id']:z for z in filt(trace,'model_call')}
    base,cand=calls(old),calls(new)
    cmp={x['decision_id']:x for x in filt(f,'ApproachCompiled')};falls={x['decision_id']:x for x in filt(f,'MemoryReadFallback')}
    receipt=json.loads((folder/'retention.json').read_bytes())
    proof=receipt.get('evidence_streams',{}).get('approach_reads')
    if proof is not None:
        file=folder/'approach_reads.jsonl.gz'
        if hashlib.sha256(file.read_bytes()).hexdigest()!=proof['sha256']:
            raise ValueError('Historical approach evidence checksum differs')
        records=rows(file)
        pins={p['request_id']:p for p in records}
        if (len(records)!=len(pins) or len(pins)!=proof['rows'] or len(pins)!=len(cmp)
                or any(pins.get(rec['request_id'],{}).get('decision_id')!=i for i,rec in cmp.items())):
            raise ValueError('Historical approach evidence differs from decision requests')
    elif receipt.get('approach_read_contract')=='pinned-approach-reads-v1':
        if cmp:raise ValueError('Missing sealed approach evidence')
        pins={}
    else:
        path=run/'control/approach-pins.json'
        pins=json.loads(path.read_bytes()) if path.exists() else {}
    assert set(cand)==set(cmp)|set(falls) and not set(cmp)&set(falls)
    assert len(cmp)==len(filt(f,'HostInputAudit'))==len(filt(f,'MemoryGenerateReturned'))
    profile=json.loads((run/'control/effective-profile.json').read_bytes())['map_memory']
    gated=profile['retrieval'].get('approach_photo_support')=='shared_depth'
    need={uid for rec in cmp.values() if rec.get('photo_support') for uid in (rec['frame_uid'],rec['source']['before'])}
    depths={};packet_by_uid={p['frame_uid']:p for p in packets}
    pixels={}
    with tarfile.open(folder/'final-map.tar.gz','r|gz')as ar:
        for m in ar:
            if m.name.startswith('observations/') and m.name.endswith('.depth.npz'):
                uid=Path(m.name).name[:-len('.depth.npz')]
                if uid in need:
                    with np.load(io.BytesIO(ar.extractfile(m).read()),allow_pickle=False) as z:
                        depths[uid]=z['aligned_depth'],z['valid_mask']
            if m.name.endswith('.rgb.png'):
                with Image.open(io.BytesIO(ar.extractfile(m).read()))as image:
                    pixels[Path(m.name).name[:-8]]=hash_pixels(image.convert('RGB'))[0]
    blank=hash_pixels(Image.new('RGB',(512,512)))[0]
    receipts=[]
    for i,x in cand.items():
        n=x['frame'];native=[packets[j]['frame_uid'] if j is not None else None for j in native_slot_indices(n+1,8)]
        assert [im['pixel_sha256']for im in x['images'][:8]]==[pixels[u] if u else blank for u in native]
        if i in falls:
            assert len(x['images'])==8 and 'Historical approach observations:' not in x['prompt'];continue
        rec=cmp[i];sid=rec['snapshot_id'];rid=rec['request_id'];pin=pins[rid];assert pin['pin']==sid and pin['epoch']==rec['episode_uid']
        req=next(t for t in f if t['kind']=='MemoryReadRequested' and t['request_id']==rid)
        rt=next(t for t in f if t['kind']=='MemoryGenerateReturned' and t['request_id']==rid);au=next(t for t in f if t['kind']=='HostInputAudit' and t['request_id']==rid)
        ev=next(t for t in f if t['kind']=='MemoryReasoningAvailable' and t['event_seq']==rec['reasoning_event'])
        mat,=[t for t in f if t['kind']=='MemoryMaterialized' and t['request_id']==rid]
        publication,=[t for t in f if t['kind']=='PublishedSnapshot' and t['snapshot_id']==sid]
        assert all(v['episode_uid']==pin['epoch'] and v['frame_uid']==packets[n]['frame_uid']
                   and v['decision_id']==i and v['snapshot_id']==sid for v in (req,mat,rec,au,rt))
        assert au['call_id']==rt['call_id']==i and publication['episode_uid']==pin['epoch']
        assert publication['event_seq']<req['event_seq']<mat['event_seq']<rec['event_seq']
        assert req['cutoff']==dict(capture_seq=publication['capture_seq'],event_seq=publication['cutoff_event_seq'])
        assert mat['native_slots']==mat['selected']==native and not mat['replaced_slots']
        assert req['cutoff']==pin['cutoff'] and req['snapshot_id']==sid==rt['snapshot_id']==au['snapshot_id']
        assert ev['event_seq']<req['event_seq']<rec['event_seq']<au['event_seq']<rt['event_seq'] and rt['projector_shape'][0]==len(x['images']) and au['native_image_slots']==8
        source=rec['source'];fields=rec['fields'];suffix=rec['model_suffix']
        assert suffix in x['prompt'] and json.loads(suffix.splitlines()[2])==fields and au['prompt_sha256']==hashlib.sha256(x['prompt'].encode()).hexdigest()
        ids=np.asarray(x['input_ids'],dtype=np.int64)
        token_header=json.dumps(dict(dtype='torch.int64',shape=list(ids.shape)),sort_keys=True,separators=(',',':')).encode()
        assert hashlib.sha256(token_header+ids.tobytes()).hexdigest()==au['token_ids_sha256']
        assert int((ids==-200).sum())==len(x['images'])
        a,b=(next(v for v in pin['anchors']if v['frame']==source[k])for k in ['before','inside'])
        assert 0<a['seq']<b['seq']<=pin['cutoff']['capture_seq'] and b['seq']<=n
        assert a['room']!=b['room']==fields['later_room_visual_hint']
        local=sorted((v for v in pin['anchors'] if a['seq']<=v['seq']<=b['seq']),key=lambda r:r['seq']);assert local==[a,b]
        relevant=sorted((v for v in pin['anchors'] if b['seq']<=v['seq']<=n),key=lambda v:v['seq'])
        assert relevant and all(v['room']==b['room'] for v in relevant)
        assert all(packets[v['seq']-1]['frame_uid']==v['frame'] for v in [a,*relevant])
        ids=[]
        for e in pin['edges']:
            j=int(e['dst'].rsplit(':f',1)[1])
            if a['seq']<j<=b['seq']:
                assert packets[j-1]['action']['action_id']==1 and packets[j-1]['action']['collision'] is False
                assert packets[j-1]['frame_uid']==e['dst'] and packets[j-2]['frame_uid']==e['src'];ids.append((j,e['id']))
        assert [e[1]for e in sorted(ids)]==source['traversed_edges'] and len(ids)==fields['recorded_forward_movements']
        verified_destinations={j for j,_ in ids}
        missing_steps=[j-1 for j in range(a['seq']+1,b['seq']+1)
                       if packets[j-1]['action']['action_id']==1 and j not in verified_destinations]
        # Older sealed inputs predate the gap field. Report the actual disclosure for either format.
        field='forward_steps_without_traversal_evidence'
        if 'unverified_forward_steps' in source or field in fields:
            assert source['unverified_forward_steps']==missing_steps
            assert fields.get(field,[])==missing_steps and (field in fields)==bool(missing_steps)
        assert fields['earlier_view_step']==a['seq']-1 and fields['later_view_step']==b['seq']-1
        for name,view in [('earlier',a),('later',b)]:
            assert fields.get(name+'_image_slot')==(native.index(view['frame'])+1 if view['frame'] in native else None)
        support=rec.get('photo_support')
        if gated and a['frame'] not in native:
            assert support and support['current_snapshot']==next(v['current_source_snapshot_id']for v in f if v['kind']=='MemoryMaterialized' and v['request_id']==rid)
            _audit_shared_depth(rec,support,packet_by_uid,depths,profile['geometry']['voxel_size'])
        else:assert support is None
        photo=rec.get('attachment_frame')
        assert len(x['images'])==8+int(photo is not None) and au['memory_attachment_slots']==int(photo is not None)
        if photo:
            assert photo==a['frame'] and photo not in native
            assert x['images'][-1]['pixel_sha256']==pixels[photo] and au['slots'][-1]['frame_uid']==photo
            assert [g[0] for g in rt['projector_batches']]==[8,1]
            assert suffix.endswith('Earlier source view at step '+str(a['seq']-1)+': <image>')
        receipts.append(dict(photo_support=support,photo=photo,call=i,step=n,reasoning_call=ev['call_id'],
                             independently_missing_forward_steps=missing_steps,gaps_disclosed_in_prompt=field in fields,fields=fields,original_output=base[i]['normalized_output']if i in base else None,candidate_output=x['normalized_output']))
    acts=lambda tr:[p['action']for p in filt(tr,'primitive_action')]
    oldact,newact=acts(old),acts(new)
    def first_diff(left,right):
        return next((i for i,(a,b) in enumerate(zip(left,right),1)if a!=b),None if len(left)==len(right) else min(len(left),len(right))+1)
    for k in sorted(set(base) & set(cand)):
        earlier,later=base[k],cand[k]
        if earlier['frame']!=later['frame'] or earlier['output_ids']!=later['output_ids']:
            break
        extra=cmp[k]['model_suffix'] if k in cmp else ''
        recovered=later['prompt'].replace(extra,'',1) if extra else later['prompt']
        assert recovered==earlier['prompt']
        if len(later['images'])==8:assert earlier['processed_image_sha256']==later['processed_image_sha256']
    first_diff_call=first_diff([v['output_ids']for v in base.values()],[v['output_ids']for v in cand.values()])
    if first_diff_call is not None and first_diff_call in cmp and first_diff_call in base:
        x,y=base[first_diff_call],cand[first_diff_call]
        assert [im['pixel_sha256']for im in x['images']]==[im['pixel_sha256']for im in y['images'][:8]] and x['frame']==y['frame']
        assert y['prompt'].replace(cmp[first_diff_call]['model_suffix'],'',1)==x['prompt']
    return dict(retained_approach_reads=len(pins) if proof is not None else 0,raw_native_slots=8*len(cand),calls=[len(base),len(cand)],reads=len(filt(f,'MemoryReadRequested')),injections=receipts,
                fallback_reasons=dict(Counter(v['reason'] for v in falls.values())),first_action_difference=first_diff(oldact,newact),
                first_output_difference=first_diff([v['output_ids']for v in base.values()],[v['output_ids']for v in cand.values()]),
                stop=[old[-1]['stop_source'],new[-1]['stop_source']],metrics={k:[old[-1]['native_metrics'][k],new[-1]['native_metrics'][k]] for k in ['success','spl','ndtw','steps_taken','distance_to_goal']})
