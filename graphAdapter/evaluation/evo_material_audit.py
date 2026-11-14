"""Independently reconstruct photo/crop bytes, temporal facts, native slots and final input receipts."""
from collections import Counter
from pathlib import Path
import hashlib,io,json,tarfile
import numpy as np
from PIL import Image
from graphAdapter.map_memory.geometry.core import Q
from graphAdapter.map_memory.retrieval.protocol import native_slot_indices
from .retrieval_audit_utils import hash_pixels,index,rows


def audit_evo(folder,instruction):
    profile=json.loads((folder.parents[3]/'control/effective-profile.json').read_bytes())
    relation_mode=profile['map_memory']['retrieval'].get('topology_relations',True)
    flow=rows(folder/'flow.jsonl.gz');trace=rows(folder/'trace.jsonl.gz')
    packets=rows(folder/'observation_packets.jsonl.gz')
    by_id={p['frame_uid']:p for p in packets}
    calls=index(trace,'model_call','call_id');dec=index(flow,'decision','decision_id')
    comp=index(flow,'EvoTopologyCompiled','decision_id');fallback=index(flow,'MemoryReadFallback','decision_id')
    audit=index(flow,'HostInputAudit','call_id');ret=index(flow,'MemoryGenerateReturned','call_id')
    feature_reuse=index(flow,'AttachmentFeatureReuse','call_id')
    req=index(flow,'MemoryReadRequested','request_id');pub=index(flow,'PublishedSnapshot','snapshot_id')
    retention=json.loads((folder/'retention.json').read_bytes())
    proof_info=retention['evidence_streams'].get('evo_reads')
    witnesses={}
    if comp:
        if proof_info is None:raise ValueError('No independently sealed historical Evo evidence')
        path=folder/'evo_reads.jsonl.gz'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=proof_info['sha256']:raise ValueError('Evo witness drift')
        entries=rows(path)
        witnesses={row['request_id']:row for row in entries}
        if len(witnesses)!=len(entries) or len(entries)!=proof_info['rows'] or set(witnesses)!={row['request_id'] for row in comp.values()}:
            raise ValueError('Evo witnesses differ from compiled requests')
    require(set(calls)==set(dec)==set(comp)|set(fallback) and not set(comp)&set(fallback),'Decision coverage')
    require(set(comp)==set(audit)==set(ret),'Generate consumption')
    # Keep only the derived pixel hashes requested by actual calls (one streaming archive pass).
    sizes={};source_pixels={};source_files={};derived={};labels={};wanted={}
    door_frames={g['frame_uid'] for e in comp.values() for g in e.get('door_regions',[])}
    original_doors={}
    for e in comp.values():
        for a in e['anchors']:
            wanted.setdefault(a['uid'],set()).update(tuple(x['box_xyxy']) for x in a['evidence'])
    with tarfile.open(folder/'final-map.tar.gz','r|gz') as archive:
        for item in archive:
            if item.name.endswith('.rgb.png'):
                data=archive.extractfile(item).read()
                u=Path(item.name).name[:-8]
                with Image.open(io.BytesIO(data)) as file:pic=file.convert('RGB')
                source_files[u]=hashlib.sha256(data).hexdigest();sizes[u]=pic.size
                source_pixels[u]=hash_pixels(pic)[0]
                if u not in wanted:continue
                derived[(u,None)]=hash_pixels(pic.resize((360,360)))[0]
                for box in wanted[u]:
                    piece=pic.crop(box);scale=min(120/piece.width,120/piece.height)
                    derived[(u,box)]=hash_pixels(piece.resize((max(1,int(piece.width*scale)),max(1,int(piece.height*scale)))))[0]
            elif item.name.startswith('detections/') and Path(item.name).stem in wanted:
                uid=Path(item.name).stem
                data=archive.extractfile(item).read()
                with np.load(io.BytesIO(data),allow_pickle=False) as z:
                    labels[uid]=(z['class_id'].copy(),z['xyxy'].copy())
                    if uid in door_frames:
                        original_doors[uid]=(hashlib.sha256(data).hexdigest(),z['door_proposal_indices'].tolist(),z['door_xyxy'].tolist())
    vocabulary=list(dict.fromkeys(s.strip() for s in Path('vendor_sources/EvoMemNav/data/scannet200_classes.txt').read_text().splitlines() if s.strip() and s.strip()!='unknown'))
    black=hash_pixels(Image.new('RGB',(512,512)))[0]
    from .native_control_audit import _question_builder
    from llava.conversation import conv_templates
    native_question,extract_reasoning=_question_builder()
    reason='';reason_frame=0
    totals=Counter()
    for cid,call in calls.items():
        frame=call['frame']
        context=dict(reasoning_context=reason,frame_id=frame,last_reason_step=reason_frame,
                     instruction=instruction,interleaved_images='<image>\n'*7)
        exec(native_question,{},context)
        convo=conv_templates['llama_3'].copy()
        suffix=comp[cid]['model_suffix'] if cid in comp else ''
        convo.append_message(convo.roles[0],context['question']+suffix)
        convo.append_message(convo.roles[1],None)
        require(convo.get_prompt()==call['prompt'],'Original instruction, reasoning or previous memory leaked across calls')
        totals['native_question_verified']+=1
        previous_reason=reason
        if call['normalized_output'].startswith('<BEGIN_OF_REASONING>'):
            reason=extract_reasoning(call['normalized_output']);reason_frame=frame
        n=call['frame'];native=[packets[j]['frame_uid'] if j is not None else None for j in native_slot_indices(n+1,8)]
        photos=call['images']; ids=np.array(call['input_ids'],np.int64)
        require([z['pixel_sha256'] for z in photos[:8]]==[source_pixels[u] if u else black for u in native],'Native pixel mismatch')
        totals['native_slots_verified']+=8
        if cid not in comp:
            require(len(photos)==8 and 'Historical graph memory through observation step' not in call['prompt'],'Fallback material leak')
            continue
        e=comp[cid];a=audit[cid];z=ret[cid];rid=e['request_id'];request=req[rid];pin=pub[e['snapshot_id']]
        require(all(t['decision_id']==cid and t['request_id']==rid and t['snapshot_id']==pin['snapshot_id']
                    and t['episode_uid']==pin['episode_uid'] and t['frame_uid']==packets[n]['frame_uid'] for t in [request,e,a,z]),'Crossed material binding')
        require(pin['event_seq']<dec[cid]['event_seq']<request['event_seq']<e['event_seq']<a['event_seq']<z['event_seq'],'Publication/decision clock')
        witness=witnesses[rid]
        require(witness['pin']==pin['snapshot_id'] and witness['request_id']==rid and witness['decision_id']==cid
                and witness['episode_uid']==pin['episode_uid']
                and witness['cutoff']==request['cutoff'] and witness['event_seq']==e['event_seq'],'Witness binding')
        require(len(witness['anchors'])==len(e['anchors']) and witness['attachment_slots']==e['attachment_slots'],'Witness anchor counts')
        for expected,actual in zip(witness['anchors'],e['anchors']):
            require(all(expected[key]==actual[key] for key in ('uid','step','room','native_slot')),'Witness selected source mismatch')
            require(len(expected['evidence'])==len(actual['evidence']),'Witness crop count')
            for row,det in zip(expected['evidence'],actual['evidence']):
                require(all(row[key]==det[key] for key in ('member','index','label','aggregate_label','object_id',
                        'object_epoch','box_xyxy','prompt_row','kind')),'Witness crop claim mismatch')
                cl,boxes=labels[actual['uid']]
                require(int(cl[det['index']])==row['source_class_id'] and boxes[det['index']].tolist()==row['raw_xyxy'],'Witness raw crop mismatch')
        # Canonical JSON sorts room keys; equal-count room tie order is verified at seal.
        parts=[line for line in e['summary'].splitlines() if line.startswith('Rooms(now):')]
        expected_counts={f"{room}:A{n['A']}/F0/O{n['O']}" for room,n in witness['room_counts'].items()}
        require(not parts and not expected_counts or len(parts)==1 and set(parts[0].removeprefix('Rooms(now): ').split('; '))<=expected_counts,'Room summary count mismatch')
        caption=e['model_suffix']
        if 'caption_bindings' in e:
            bindings=e['caption_bindings']
            require(len(bindings)==e['attachment_slots'] and caption.count('<image>')==len(bindings),'Caption/photo count')
            ends=[];pos=0
            for j,bind in enumerate(bindings,8):
                slot=a['slots'][j];line=bind['caption'];start=caption.find(line,pos)
                require(start>=pos and line.count('<image>')==1 and caption[:start].count('<image>')==j-8 and bind['slot']==j+1
                    and bind['role']==slot['source_kind'] and bind['frame_uid']==slot['frame_uid']
                    and bind['source_ref']==slot['evidence_group'],'Misbound ordered image caption')
                pos=start+len(line);ends.append(pos)
            totals['caption_pairs_verified']+=len(ends)
        require(caption in call['prompt'] and e['summary'] in caption and call['prompt'].count(caption)==1,'Compiled summary missing')
        require(a['prompt_sha256']==hashlib.sha256(call['prompt'].encode()).hexdigest(),'Final prompt hash')
        dtype=json.dumps(dict(dtype='torch.int64',shape=list(ids.shape)),sort_keys=True,separators=(',',':')).encode()
        require(hashlib.sha256(dtype+ids.tobytes()).hexdigest()==a['token_ids_sha256'],'Final token IDs')
        visual=[];offsets=[]
        query_schema=e.get('crop_query_schema')
        if query_schema is not None:
            require(type(query_schema) is int and query_schema in (1,2),'Unsupported crop query provenance schema')
            from graphAdapter.map_memory.retrieval.evidence import match_category_cues
            instruction_cues=match_category_cues(instruction,vocabulary)
            reason_cues=match_category_cues(previous_reason,vocabulary) if previous_reason else ()
            if query_schema==2:
                audit_query_sources(e.get('query_sources'),instruction,previous_reason,vocabulary)
                totals['query_span_tables_verified']+=1
            else:require('query_sources' not in e,'Unexpected lexical source table on legacy event')
        for j,anchor in enumerate(e['anchors']):
            u=anchor['uid'];old=by_id[u];step=anchor['step']
            require(old['env_step']==step<n and old['capture_seq']<=pin['capture_seq'],'Future anchor')
            native_slot=None
            if u in native:
                si=native.index(u)
                if a['slots'][si]['raw_pixel_hash']==a['slots'][si]['host_pixel_hash']:
                    native_slot=si+1
            require(native_slot==anchor['native_slot'],'Incorrect native reference')
            offsets.append(caption.index(f"Anchor View {j} (room: {anchor['room']}; observed at step {step};"))
            rel=anchor['relative_camera']
            if rel is not None:
                left,right=old['pose_record'],packets[n]['pose_record']
                require(left['map_version']==right['map_version'] and left['episode_instance']==right['episode_instance'],'Mixed pose')
                v=np.linalg.solve(np.asarray(right['T_map_camera_cv']),np.asarray(left['T_map_camera_cv']))[:3,3]
                require(rel==[round(float(x),2) for x in v],'Relative camera differs')
                require(f"Earlier camera relative to the current camera in metres [right, down, forward]: {rel}." in caption,'Spatial field omitted from final text')
            if native_slot is None:visual.append((u,None,u))
            for det in anchor['evidence']:
                if query_schema is not None or 'query_match' in det:
                    require(query_schema in (1,2),'Crop provenance without declared schema')
                    label=det['aggregate_label'].strip().lower()
                    expected_match={'instruction':[word for word in instruction_cues if word and word in label],
                                    'reasoning':[word for word in reason_cues if word and word in label]}
                    require(det.get('query_match')==expected_match,'Crop lexical priority not bound to actual instruction and prior REASON')
                    totals['crop_query_matches_verified']+=1
                cl,boxes=labels[u];i=det['index'];w,h=sizes[u]
                require(det['member']==f'{u}:d{i:05d}' and det['label']==vocabulary[int(cl[i])],'Wrong camera member')
                x,y,X,Y=boxes[i].astype(int)
                expected=[max(0,x),max(0,y),min(w,max(x+1,X)),min(h,max(y+1,Y))]
                require(expected==det['box_xyxy'],'Wrong source crop')
                require(f"Anchor View {j} detail from step {step}, possible {det['label']}" in caption,'Lost region text')
                visual.append((u,tuple(expected),det['member']))
        require(offsets==sorted(offsets) and len(offsets)==len(set(offsets)),'Anchor order')
        regions=e.get('door_regions',[])
        require(regions==witness.get('door_regions',[]),'Unsealed door region sources')
        if regions:
            require(profile['map_memory']['retrieval'].get('structural_door_regions') is True and query_schema==2
                    and ('door' in instruction_cues or 'door' in reason_cues),'Unrequested structural door regions')
            for region in regions:
                uid=region['frame_uid']
                if 'current_support' in region:
                    support=region['current_support']
                    require(profile['map_memory']['retrieval'].get('locate_door_regions') is True
                            and support['current_snapshot']==a['slots'][7]['source_snapshot_id']
                            and support['current_uid']==packets[n]['frame_uid'] and support['current_step']==n
                            and support['decision_event']==dec[cid]['event_seq']
                            and support['current_hw']==list(reversed(sizes[packets[n]['frame_uid']])),
                            'Door projection differs from final current image')
                check_archived_door_boxes(region,original_doors.get(uid),sizes[uid])
                require(region['caption'] in caption and sizes[uid]==tuple(reversed(region['image_hw'])),
                        'Door region caption or original grid omitted')
            totals['structural_door_views']+=len(regions)
        ctx=e.get('context_groups',[])
        require(ctx==witness.get('context_groups',[]) and all(section['text'] in caption for section in ctx),'Context evidence not bound to generated input')
        totals['context_groups']+=len(ctx)
        if not relation_mode:
            require(not e['relations'] and all(a['relative_camera'] is None for a in e['anchors'])
                    and 'Recorded steps ' not in caption and 'Earlier camera relative' not in caption,'Disabled enhancement leaked')
        named=e.get('anchor_routes',[])
        require(named==witness.get('anchor_routes',[]) and (not named or profile['map_memory']['retrieval'].get('anchor_routes') is True),
                'Unexpected or unsealed named route')
        for route in [*e['relations'],*named]:
            start,end=route['from_step'],route['to_step'];rebuild=[];refs=[]
            require(0<=start<end<n and end+1<=pin['capture_seq'],'Future segment')
            for j in range(start+1,end+1):
                left,right=packets[j-1],packets[j];op=right['action'];pre,post=left['frame_uid'],right['frame_uid']
                edge=lambda kind:hashlib.sha256((kind+'|'+pre+'|'+post).encode()).hexdigest()
                refs.append(edge('temporal_next'))
                label={0:'stop',1:'forward',2:'left turn',3:'right turn'}.get(op['action_id'],'other action')
                if op['collision'] is True:label+=' (collision)'
                elif op['collision'] is None:label+=' (feedback unknown)'
                elif op['action_id']==1:
                    A,B=left['pose_record'],right['pose_record']
                    valid=A['valid'] and B['valid'] and A['episode_instance']==B['episode_instance'] and A['map_version']==B['map_version']
                    dist=np.linalg.norm(np.asarray(A['T_odom_base'])[:3,3]-np.asarray(B['T_odom_base'])[:3,3]) if valid else 0.
                    if .03<dist<=.5:refs.append(edge('traversed'));label+=' (measured)'
                    else:label+=' (no measured traversal)'
                if rebuild and rebuild[-1][0]==label:rebuild[-1][1]+=1
                else:rebuild.append([label,1])
            require(rebuild==route['runs'] and refs==route['edge_ids'],'Lost turn/collision/gap in segment')
            sentence=', '.join(f'{count} {act}' for act,count in rebuild)
            if route in named:
                from graphAdapter.map_memory.retrieval.evo_host import anchor_route_caption
                text=anchor_route_caption(dict(from_step=start,to_step=end,runs=rebuild))
            else:text=f"Recorded steps {start} to {end} in order: {sentence}."
            require(text in caption,'Validated execution absent from prompt')
        map_proof=e.get('map_image')
        if map_proof is not None:
            require(witness.get('map_image')==map_proof and map_proof['manifest']['snapshot_id']==pin['snapshot_id']
                    and map_proof['manifest']['episode_uid']==pin['episode_uid'],'Map witness crossed publication')
            global_mode=map_proof.get('role')=='global'
            map_index=8 if global_mode else -1
            slot=a['slots'][map_index]
            map_sources=[pin['snapshot_id']]
            if global_mode and 'camera_overlay' in map_proof['manifest']:
                map_sources.append(map_proof['manifest']['camera_overlay']['snapshot_id'])
            require(slot['source_kind']==('evo_global_map' if global_mode else 'evo_topology_map')
                    and slot['host_pixel_hash']==map_proof['pixel_hash'] and slot['source_snapshot_id']==pin['snapshot_id']
                    and slot['evidence_group']==map_sources and photos[map_index]['pixel_sha256']==witness['map_trace_digest'],
                    'Derived map tensor/role missing')
            if global_mode:
                overlay=map_proof['manifest'].get('camera_overlay')
                if overlay is not None:
                    audit_camera_overlay(overlay,src=a['slots'][7]['source_snapshot_id'],current=packets[n],
                        pub=pub,pin=pin,clock=map_proof['decision_event'],decision_event=dec[cid]['event_seq'],
                        enabled=profile['map_memory']['retrieval'].get('current_camera_overlay'))
                    totals['current_camera_overlays']+=1
                if profile['map_memory']['retrieval'].get('source_node_labels'):
                    require(map_proof['manifest'].get('label_scheme')=='source_identity_v1'
                            and map_proof['manifest']['schema_version']==5,'Source map label scheme missing')
                    verify_source_node_references(caption,e['anchors'],map_proof['manifest']['object_epoch'])
                if profile['map_memory']['retrieval'].get('grounded_node_summary'):
                    require(map_proof['manifest'].get('node_summary')=='grounded' and map_proof['manifest']['schema_version'] in (4,5),
                        'Grounded node descriptions missing from requested profile')
                require(map_proof['caption'] in caption and all(v in caption for v in map_proof['node_captions']),'Map title or node descriptions missing')
            else:require('Observed top-down map' in caption,'Missing BEV caption')
            totals['topology_maps']+=1
        extra=len(visual)+int(map_proof is not None)
        require(len(photos)==len(a['slots'])==int((ids==-200).sum())==8+extra and a['current_native_image_index']==8,'Final slot layout')
        for j,(u,box,ref) in enumerate(visual,8+int(map_proof is not None and map_proof.get('role')=='global')):
            slot=a['slots'][j];require(slot['frame_uid']==u and slot['source_snapshot_id']==pin['snapshot_id']
                and slot['source_image_hash']==source_files[u] and slot['evidence_group']==[ref]
                and photos[j]['pixel_sha256']==derived[(u,box)],'Delivered crop/view differs from archived RGB')
        cache_limit=profile['map_memory']['retrieval'].get('attachment_feature_cache_bytes',0)
        if extra and cache_limit:
            reuse=feature_reuse.get(cid)
            require(reuse is not None and reuse['request_id']==rid and reuse['decision_id']==cid
                and reuse['snapshot_id']==pin['snapshot_id'] and reuse['frame_uid']==a['frame_uid']
                and a['event_seq']<reuse['event_seq']<z['event_seq'],'Unbound attachment cache receipt')
            require(all(type(reuse[k]) is int and reuse[k]>=0 for k in ('encodes','hits','bypassed','resident_bytes'))
                and reuse['hits']+reuse['encodes']+reuse['bypassed']==extra
                and reuse['resident_bytes']<=cache_limit,'Attachment feature reuse counts or capacity differ')
            totals['attachment_tower_encodes']+=reuse['encodes']+reuse['bypassed']
            totals['attachment_features_reused']+=reuse['hits']
        else:require(cid not in feature_reuse,'Unexpected attachment cache receipt')
        require(z['projector_batches']==[[8,196,4096]]+[[1,196,4096]]*extra,'Original/extra projector grouping')
        require(a['expanded_input_tokens']==ids.size+195*len(photos) and a['expanded_input_tokens']+a['reserved_generation_tokens']<=4096,'Expanded budget')
        totals['compiled']+=1;totals['photos']+=extra;totals['segments']+=len(e['relations'])
    require(set(feature_reuse)<=set(comp),'Cache use on an uncompiled decision')
    return dict(calls=len(calls),sealed_historical_reads=len(witnesses),fallbacks=dict(Counter(r['reason'] for r in fallback.values())),**totals)


def require(condition,message):
    if not condition:raise ValueError(message)


def audit_camera_overlay(overlay,*,src,current,pub,pin,clock,decision_event,enabled):
    pose=current['pose_record'];n=current['env_step']
    require(enabled is True
        and src==overlay['snapshot_id'] and src!=pin['snapshot_id'] and src in pub
        and pub[src]['frame_uid']==current['frame_uid']
        and pub[src]['episode_uid']==current['episode_uid']
        and pub[src]['source_packet_event_seq']==current['event_seq']
        and overlay['capture_seq']==current['capture_seq']==n+1 and overlay['step']==n
        and overlay['frame_uid']==current['frame_uid'] and overlay['source_event']==current['event_seq']
        and overlay['episode_instance']==pose['episode_instance']
        and overlay['sensor_timestamp_ns']==current['sensor_timestamp_ns']
        and overlay['calibration_hash']==current['calibration_hash']
        and overlay['pose_map_version']==pose['map_version']
        and clock==decision_event
        and overlay['source_event']<decision_event,'Unbound current camera overlay')
    if overlay['status']=='known':
        camera=Q@np.asarray(pose['T_map_camera_cv'])
        axis=camera[[0,2],2];norm=np.linalg.norm(axis)
        require(pose['valid'] and pose['map_version']==pin['versions']['pose_map_version']
            and np.allclose(overlay['xz'],camera[[0,2],3],rtol=0,atol=1e-9)
            and (overlay['heading_xz'] is None if norm<=1e-8 else
                 np.allclose(overlay['heading_xz'],axis/norm,rtol=0,atol=1e-9)),
            'Camera marker differs from packet transform')


def audit_query_sources(actual,instruction,reason,vocabulary):
    from graphAdapter.map_memory.retrieval.evidence import category_source_spans
    require(isinstance(actual,dict) and set(actual)=={'instruction','reasoning'},'Missing query source table')
    for key,text in [('instruction',instruction),('reasoning',reason or '')]:
        expected=category_source_spans(text,vocabulary)
        require(actual[key]==expected,'Lexical source spans differ from the causal input')
        for occurrences in actual[key].values():
            for item in occurrences:
                start,end=item['start'],item['end']
                require(type(start) is int and type(end) is int and 0<=start<end<=len(text)
                        and text[start:end]==item['text'],'Invalid source span coordinates')


def check_archived_door_boxes(group,source,image_size):
    """Match pre-filter identities and clipped bounds independently of fused camera rows."""
    from graphAdapter.map_memory.storage.store import clip_detection_box
    require(source is not None and source[0]==group['source_ref'],'Structural region detector archive differs')
    width,height=image_size
    require(group['image_hw']==[height,width],'Structural region image grid differs')
    _,indices,raw=source
    require(len(indices)==len(raw) and len(set(indices))==len(indices),'Invalid detector proposal rows')
    boxes=[]
    for idx,box in zip(indices,raw):
        rect=clip_detection_box(box,(height,width))
        if rect is not None:boxes.append(dict(proposal_index=idx,box_xyxy=list(rect)))
    require(boxes==group['boxes'] and bool(boxes),'Structural region box or original proposal index differs')


def verify_source_node_references(caption,anchors,epoch):
    lines=caption.splitlines()
    for j,anchor in enumerate(anchors):
        header=f"Anchor View {j} (room: {anchor['room']}; observed at step {anchor['step']};"
        locations=[i for i,line in enumerate(lines) if line.startswith(header)]
        require(len(locations)==1 and locations[0]+1<len(lines)
                and lines[locations[0]+1]==f"Map node A{anchor['step']} is the observing camera for this group.",
                'Anchor map label differs from original source step')
        for det in anchor['evidence']:
            prefix=(f"Anchor View {j} detail from step {anchor['step']}, possible {det['label']} "
                    f"(map object O{det['object_id']} observed from A{anchor['step']})")
            require(det['object_epoch']==epoch and any(line.startswith(prefix)
                    and f"source pixel box {det['box_xyxy']}: <image>" in line for line in lines),
                    'Crop map label differs from source object or epoch')
