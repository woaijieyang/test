"""Recompute each dynamic record from retained primitive packets, camera images and traces."""
from pathlib import Path
from collections import Counter
import json,hashlib,gzip,tarfile,io,sys,math
import numpy as np
from PIL import Image
from graphAdapter.interfaces.host_slots import native_slot_indices
from graphAdapter.map_memory.storage.store import clip_detection_box
from graphAdapter.evaluation.retrieval_audit_utils import hash_pixels,rows,index

def audit_plan_queries(flow,calls,requests,instruction,vocab):
    """Require a positive object cue in the actual host-extracted plan even when the read misses."""
    from .native_control_audit import _question_builder
    from graphAdapter.map_memory.retrieval.evidence import landmark_query_cues
    _,extract=_question_builder()
    reasons=index(flow,'MemoryReasoningAvailable','event_seq')
    queries=index(flow,'LandmarkQuery','request_id')
    for rid,request in requests.items():
        event=request.get('reasoning_event')
        if type(event) is not int or event not in reasons:
            raise ValueError('Photo request without a native plan')
        history=reasons[event]
        if (event>=request['decision_event_seq'] or history['episode_uid']!=request['episode_uid']
                or history['call_id']>=request['decision_id']):
            raise ValueError('Native plan is outside the photo request history')
        text=calls[history['call_id']]['normalized_output']
        if not text.startswith('<BEGIN_OF_REASONING>'):
            raise ValueError('Landmark request used a non-reasoning output')
        cues=landmark_query_cues(instruction,extract(text),vocab)
        if not cues:
            raise ValueError('Photo request without a matching native plan cue')
        if rid in queries and (queries[rid]['categories']!=list(cues) or queries[rid]['reasoning_event']!=event):
            raise ValueError('Recorded landmark query differs from the native plan')


def audit_episode(d,e,*,instruction=None):
    if not __debug__:raise RuntimeError('Evidence checks require standard execution')
    profile=json.loads((d.parents[3]/'control/effective-profile.json').read_bytes())
    plan_photo=profile['map_memory']['retrieval'].get('context_admission')=='native_plan_photo'
    f,t,p=(rows(d/n)for n in ('flow.jsonl.gz','trace.jsonl.gz','observation_packets.jsonl.gz'))
    assert t[0]['episode_scope']['member']==e['member'] and t[-1]['kind']=='terminal'
    pk={x['frame_uid']:x for x in p};byseq={x['capture_seq']:x for x in p}
    calls=index(t,'model_call','call_id');dec=index(f,'decision','decision_id')
    compiled=index(f,'DynamicContextCompiled','request_id');mats=index(f,'MemoryMaterialized','request_id')
    au=index(f,'HostInputAudit','call_id');ret=index(f,'MemoryGenerateReturned','call_id')
    req=index(f,'MemoryReadRequested','request_id');pub=index(f,'PublishedSnapshot','snapshot_id')
    fall=index(f,'MemoryReadFallback','decision_id')
    assert set(ret)==set(au) and set(compiled)=={a['request_id']for a in au.values()}
    assert set(calls)==set(dec) and set(au).isdisjoint(fall) and set(au)|set(fall)==set(dec)
    assert set(au)=={r['decision_id'] for r in au.values()}
    retention=json.loads((d/'retention.json').read_bytes())
    object_stream=retention['evidence_streams'].get('object_reads')
    if object_stream is not None:
        material=d/'object_reads.jsonl.gz'
        if hashlib.sha256(material.read_bytes()).hexdigest()!=object_stream['sha256']:
            raise ValueError('Retained object evidence checksum differs')
        center_pins={}
        for row in rows(material):
            rid=row['request_id']
            if rid in center_pins or rid not in req or row['decision_id']!=req[rid]['decision_id'] or row['epoch']!=req[rid]['episode_uid']:
                raise ValueError('Unbound or duplicate retained object evidence')
            center_pins[rid]=row
        expected={rid for rid,c in compiled.items() if c['attachment_frame']}
        expected.update(x['request_id'] for x in f if x['kind']=='LandmarkInNativeSlot')
        if set(center_pins)!=expected or len(center_pins)!=object_stream['rows']:
            raise ValueError('Retained object requests differ from decision history')
    else:
        if retention.get('object_read_contract')=='pinned-object-reads-v1' and (
                any(c['attachment_frame'] for c in compiled.values()) or any(x['kind']=='LandmarkInNativeSlot' for x in f)):
            raise ValueError('Retained object evidence missing for a claimed decision')
        legacy=d.parents[3]/'control/center-pins.json'
        center_pins=json.loads(legacy.read_bytes()) if legacy.exists() else {}
    # WindowCursor advances at materialization, including decisions later reverted by the token budget.
    windows={};previous_frame=None;previous_end=0;start=0
    for row in f:
        if row['kind']!='MemoryMaterialized':continue
        read=req[row['request_id']];end=read['cutoff']['capture_seq']
        assert end>=previous_end
        if previous_frame!=row['frame_uid']:start=previous_end
        windows[row['request_id']]=(max(1,start),end)
        previous_frame=row['frame_uid'];previous_end=end
    hashes={};detect={};anchors={x['attachment_frame']for x in compiled.values()if x['attachment_frame']}
    native_hits=index(f,'LandmarkInNativeSlot','decision_id')
    for hit in native_hits.values():
        anchors.update(ref.rpartition(':d')[0] for ref in (hit['source']['member'],hit['native']['member']))
    with tarfile.open(d/'final-map.tar.gz','r|gz')as ar:
        for item in ar:
            if item.name.endswith('.rgb.png'):
                data=ar.extractfile(item).read()
                with Image.open(io.BytesIO(data))as pic:h,ph=hash_pixels(pic.convert('RGB'));dim=pic.size
                hashes[Path(item.name).name[:-len('.rgb.png')]]=(h,ph,hashlib.sha256(data).hexdigest(),dim)
            elif item.name.startswith('detections/')and Path(item.name).stem in anchors:
                with np.load(io.BytesIO(ar.extractfile(item).read()),allow_pickle=False)as z:detect[Path(item.name).stem]=(z['class_id'].copy(),z['xyxy'].copy())
    vocab=list(dict.fromkeys(x.strip() for x in Path('vendor_sources/EvoMemNav/data/scannet200_classes.txt').read_text().splitlines()if x.strip()and x.strip()!='unknown'))
    if plan_photo:
        if not isinstance(instruction,str) or not instruction:raise ValueError('Sealed instruction required for native plan audit')
        audit_plan_queries(f,calls,req,instruction,vocab)
    blank=hash_pixels(Image.new('RGB',(512,512)))[0]
    edge_id=lambda kind,pre,post:hashlib.sha256((kind+'|'+pre+'|'+post).encode()).hexdigest()
    totals=Counter(); examples=[];last_anchor=None
    for k,x in calls.items():
        n=x['frame']+1
        native=[byseq[i+1]['frame_uid']if i is not None else None for i in native_slot_indices(n,8)]
        assert [a['pixel_sha256']for a in x['images'][:8]]==[hashes[uid][0]if uid else blank for uid in native]
        totals['native_slots']+=8
        if k in native_hits:
            hit=native_hits[k];rid=hit['request_id'];src=hit['source'];seen=hit['native'];read=req[rid]
            pin=center_pins[rid]
            assert pin['pin']==read['snapshot_id']==hit['snapshot_id'] and pin['cutoff']==read['cutoff']
            assert hit['frame_uid']==read['frame_uid']==byseq[n]['frame_uid'] and read['decision_id']==k
            assert pub[hit['snapshot_id']]['event_seq']<read['event_seq']<hit['event_seq']
            if rid in mats:
                assert hit['event_seq']<mats[rid]['event_seq']
            else:
                assert plan_photo and k in fall and fall[k]['reason']=='no_eligible_plan_photo'
                assert hit['event_seq']<fall[k]['event_seq'] and rid not in compiled
            assert len(x['images'])==8 and (rid not in compiled or compiled[rid]['attachment_frame'] is None)
            assert 1<=seen['slot']<=8
            uid,idx=seen['member'].rsplit(':d',1);old,ordinal=src['member'].rsplit(':d',1)
            assert native[seen['slot']-1]==uid and old not in native and pk[uid]['capture_seq']<=pin['cutoff']['capture_seq']
            assert pk[uid]['env_step']==seen['step'] and [old,src['object_id']] in pin['visibility']
            owners=[obj for obj in pin['entities'] if obj['id']==src['object_id'] and obj['epoch']==src['epoch']]
            assert len(owners)==1 and {src['member'],seen['member']}<=set(owners[0]['members'])
            cl,boxes=detect[uid];w,h=hashes[uid][3]
            assert vocab[int(cl[int(idx)])]==hit['source_class']==vocab[int(detect[old][0][int(ordinal)])]
            assert list(clip_detection_box(boxes[int(idx)],(h,w)))==seen['box_xyxy']
            totals['native_object_matches']+=1
        if k not in au:
            assert len(x['images'])==8 and 'Graph memory for this decision:' not in x['prompt']
            if last_anchor:totals['photo_withdrawals']+=1
            last_anchor=None
            continue
        a=au[k];rid=a['request_id'];c=compiled[rid];q=req[rid];m=mats[rid];fields=c['model_fields'];source=c['source']
        assert len({z['snapshot_id']for z in (m,c,q,a,ret[k])})==1 and source['history_snapshot']==q['snapshot_id']
        assert len({item['decision_id']for item in (q,m,c,a,ret[k])})==1
        assert len({item['frame_uid']for item in (q,m,c,a,ret[k])})==1
        assert a['frame_uid']==byseq[n]['frame_uid']
        cp=pub[q['snapshot_id']]
        assert q['cutoff']==dict(capture_seq=cp['capture_seq'],event_seq=cp['cutoff_event_seq'])
        assert pub[q['snapshot_id']]['event_seq']<q['event_seq']<m['event_seq']<c['event_seq']<a['event_seq']<ret[k]['event_seq']
        assert m['native_slots']==m['selected']==native and not m['replaced_slots']
        suffix=c['model_suffix'];assert suffix in x['prompt'] and json.loads(suffix.splitlines()[2])==fields
        ids=np.asarray(x['input_ids'],np.int64)
        header=json.dumps(dict(dtype='torch.int64',shape=list(ids.shape)),sort_keys=True,separators=(',',':')).encode()
        assert hashlib.sha256(header+ids.tobytes()).hexdigest()==a['token_ids_sha256'] and hashlib.sha256(x['prompt'].encode()).hexdigest()==a['prompt_sha256']
        assert fields['as_of_step']==x['frame'] and source['cutoff']==q['cutoff']['capture_seq']
        cap=source['cutoff'];cur=byseq[n];assert cap<=n
        start,window_end=windows[rid];assert window_end==cap
        if plan_photo:
            assert c['attachment_frame'] and 'recent_path' not in fields
            reason,=[z for z in f if z['kind']=='LandmarkQuery' and z['request_id']==rid]
            assert type(reason['reasoning_event']) is int and reason['categories']
            assert any(z['kind']=='MemoryReasoningAvailable' and z['event_seq']==reason['reasoning_event']
                       and z['episode_uid']==q['episode_uid'] and z['event_seq']<q['event_seq'] for z in f)
            start=cap
        dist=0.;turns=[];collided=0;refs=[]
        for j in range(start+1,cap+1):
            pre,post=byseq[j-1],byseq[j];act=post['action'];refs.append(edge_id('temporal_next',pre['frame_uid'],post['frame_uid']))
            A,B=pre['pose_record'],post['pose_record']
            supported=A['valid'] and B['valid'] and A['episode_instance']==B['episode_instance'] and act['collision'] is False and act['action_id']==1
            length=float(np.linalg.norm(np.asarray(A['T_odom_base'])[:3,3]-np.asarray(B['T_odom_base'])[:3,3])) if supported else None
            if supported and .03<length<=.5:
                refs.append(edge_id('traversed',pre['frame_uid'],post['frame_uid']));dist+=length
            if act['collision'] is True:collided+=1
            if act['collision'] is False and act['action_id'] in (2,3):turns.append({2:'left',3:'right'}[act['action_id']])
        assert refs==source['edges']
        if turns or dist or collided:
            expected={'from_step':byseq[start]['env_step'],'to_step':byseq[cap]['env_step']}
            if turns:expected['executed_turn_primitives']=turns
            if dist:expected['recorded_forward_m']=round(dist,1)
            if collided:expected['recorded_collisions']=collided
            assert expected==fields['recent_path'];totals['path_records']+=1
        else:assert 'recent_path' not in fields
        label=fields.get('historical_landmark');extra=int(label is not None)
        assert a['native_image_slots']==8 and a['current_native_image_index']==8 and a['memory_attachment_slots']==extra
        assert c['native_slots']==8 and c['attachment_slots']==extra
        assert set(fields)<={'as_of_step','recent_path','historical_landmark','distance_to_historical_camera_m_estimate'}
        if not extra:
            assert 'distance_to_historical_camera_m_estimate' not in fields and 'anchor' not in source and c['attachment_frame'] is None
        assert ret[k]['projector_batches']==([[8,196,4096],[1,196,4096]]if extra else [[8,196,4096]])
        assert len(x['images'])==int((ids==-200).sum())==8+extra and a['expanded_input_tokens']==ids.size+195*(8+extra)
        if label:
            uid=c['attachment_frame'];s=a['slots'][-1];assert uid==s['frame_uid']==source['anchor'] and uid not in native
            assert x['images'][8]['pixel_sha256']==hashes[uid][0] and hashes[uid][2]==s['source_image_hash']
            assert label['observed_step']==pk[uid]['env_step'] and label['current_step']==x['frame'] and label['historical_photo_slot']==9
            frame,ix=s['evidence_group'][0].rsplit(':d',1);assert frame==uid;cl,xy=detect[uid];i=int(ix);w,h=hashes[uid][3]
            assert vocab[int(cl[i])]==label['instruction_landmark'] and label['detector_region_xyxy_pixels']==list(clip_detection_box(xy[i],(h,w)))
            if object_stream is not None:
                pin=center_pins[rid];ref=source['anchor_object']
                assert pin['pin']==q['snapshot_id'] and pin['cutoff']==q['cutoff'] and [uid,ref['object_id']] in pin['visibility']
                owner,=[o for o in pin['entities'] if o['epoch']==ref['epoch'] and o['id']==ref['object_id']]
                assert ref['member']==s['evidence_group'][0] and ref['member'] in owner['members']
            coords=label.get('object_center_estimate_current_camera')
            assert (coords is None)==('object_position' not in source)
            if coords is not None:
                from graphAdapter.map_memory.geometry.core import Q
                proof=source['object_position'];pin=center_pins[rid]
                assert proof['member']==s['evidence_group'][0] and proof['source_snapshot']==pin['pin']==q['snapshot_id']
                assert proof['current_snapshot']==m['current_source_snapshot_id'] and pin['cutoff']==q['cutoff']
                owner,=[entity for entity in pin['entities'] if proof['member'] in entity['members']]
                assert (owner['epoch'],owner['id'])==(proof['epoch'],proof['object_id']) and [uid,owner['id']] in pin['visibility']
                assert owner['label']==label['instruction_landmark'] and set(owner['classes'])=={int(cl[i])}
                assert proof['pose_version']==owner['version']==cur['pose_record']['map_version']==source['map_version']
                box=owner['bbox']
                center=(np.asarray(box['center']) if box['kind']=='obb' else
                        (np.asarray(box['minimum'])+np.asarray(box['maximum']))/2)
                assert center.tolist()==proof['center_G']
                optical=np.linalg.solve(Q@np.asarray(cur['pose_record']['T_map_camera_cv']),np.r_[center,1])
                assert coords=={'right_m':round(float(optical[0]),1),'forward_m':round(float(optical[2]),1)}
                totals['object_centers_verified']+=1
            pos=lambda packet:np.asarray(packet['pose_record']['T_map_camera_cv'])[:3,3]
            can_locate=(pk[uid]['pose_record']['valid'] and cur['pose_record']['valid']
                and pk[uid]['pose_record']['episode_instance']==cur['pose_record']['episode_instance']
                and pk[uid]['pose_record']['map_version']==cur['pose_record']['map_version']==source['map_version'])
            if can_locate:
                assert round(float(np.linalg.norm(pos(pk[uid])-pos(cur))),1)==fields['distance_to_historical_camera_m_estimate']
                totals['photos_distance_and_labels']+=1
            else:assert 'distance_to_historical_camera_m_estimate' not in fields
            totals['attachments']+=1
        totals['readbacks']+=1
        anchor=c['attachment_frame']
        if last_anchor and not anchor:totals['photo_withdrawals']+=1
        if anchor and anchor!=last_anchor:totals['photo_appearances_or_changes']+=1
        last_anchor=anchor;examples.append((k,x['frame'],cap,anchor,fields))
    return dict(member=e['member'],calls=len(calls),retained_object_reads=len(center_pins) if object_stream is not None else 0,**totals,terminal=t[-1]['native_metrics'],fallbacks={k:v['reason']for k,v in fall.items()},examples=examples)
