"""Seal the object and approach relationships actually used by stage 002 before releasing map history."""
from contextlib import closing
from itertools import groupby
from operator import itemgetter
from pathlib import Path
from .archive import canonical,IntegrityError
from .lifecycle import compress_jsonl,inside,json_rows
from .store import load_episode


def decision_reads(events):
    """Only requests actually referenced in model-material or native-slot decisions need witnesses."""
    seen=set()
    for event in events:
        kind=event['kind']
        if kind=='EvoTopologyCompiled':
            rid=event['request_id']
            if rid in seen:raise IntegrityError('Duplicate Evo read for a request')
            seen.add(rid)
            fields=('request_id','episode_uid','decision_id','event_seq','frame_uid','env_step',
                    'snapshot_id','summary','coverage','anchors','dropped','native_slots','attachment_slots')
            yield 'evo_reads', dict({k:event[k] for k in fields},map_image=event.get('map_image'),context_groups=event.get('context_groups',[]),door_regions=event.get('door_regions',[]),anchor_routes=event.get('anchor_routes',[]))
            continue
        if kind=='ApproachCompiled':
            rid=event['request_id']
            if rid in seen:raise IntegrityError('Duplicate historical read for a request')
            seen.add(rid)
            yield 'approach_reads', {k:event[k] for k in ('request_id','episode_uid','decision_id','snapshot_id','source','frame_uid')}
            continue
        if kind=='LandmarkInNativeSlot':
            owner=event['source'];members=[owner['member'],event['native']['member']]
        elif kind=='DynamicContextCompiled' and event.get('attachment_frame'):
            owner=event['source']['anchor_object'];members=[owner['member']]
            if members[0].rpartition(':d')[0]!=event['attachment_frame']:
                raise IntegrityError('Compiled object refers to another photograph')
        else:continue
        rid=event['request_id']
        if rid in seen:raise IntegrityError('Multiple object decisions for a request')
        seen.add(rid)
        yield 'object_reads', dict(request_id=rid,episode_uid=event['episode_uid'],decision_id=event['decision_id'],
                   snapshot_id=event['snapshot_id'],owner=owner,members=members)


def _object_witness(reader,claim):
    src=claim['owner'];epoch=src['epoch'];oid=src['object_id']
    if reader.snapshot_id!=claim['snapshot_id'] or reader.identity['episode_uid']!=claim['episode_uid']:
        raise IntegrityError('Object witness crossed episode or publication')
    if type(oid)is not int or not isinstance(epoch,str):raise IntegrityError('Malformed historical object ID')
    obj=reader.get_object(epoch,oid,revision=reader.snapshot_id)
    members=claim['members'];uid=src['member'].rpartition(':d')[0]
    vsm=reader._graph['vsm']
    if (obj['status']!='active' or obj['id']!=oid or obj['epoch']!=epoch or not set(members)<=set(obj['members'])
            or oid not in vsm['anchors'].get(uid,{}).get('objects',())
            or (uid,oid) not in map(tuple,vsm['visibility_edges'])):
        raise IntegrityError('Historical object member or visibility edge is absent')
    for member in members:
        frame,sep,index=member.rpartition(':d')
        view=reader._graph['views'].get(frame)
        if not sep or not index.isascii() or not index.isdecimal() or member!=f'{frame}:d{int(index):05d}' or view is None or view['capture_seq']>reader.cutoff['capture_seq']:
            raise IntegrityError('Historical detection outside published views')
    attrs=obj['attributes']
    # Store the class set needed for the fused-center test and just the exact detections involved.
    from .final_snapshot import plain
    entity=dict(id=oid,epoch=epoch,members=members,version=obj['pose_map_version'],label=attrs['class_name'],
                classes=sorted(set(attrs['class_id'])),bbox=plain(attrs.get('bbox')))
    return dict(request_id=claim['request_id'],decision_id=claim['decision_id'],epoch=reader.identity['episode_uid'],
                pin=reader.snapshot_id,cutoff=dict(reader.cutoff),entities=[entity],visibility=[[uid,oid]])


def _approach_witness(reader, claim):
    graph = reader._graph
    if reader.snapshot_id != claim['snapshot_id'] or reader.identity['episode_uid'] != claim['episode_uid']:
        raise IntegrityError('Approach evidence crossed episode or publication')
    src = claim['source']
    # Retain every eligible anchor so the reader can independently find the most recent
    # continuous run of matching room hints, including anchors after the inside view.
    decision_frame = claim['frame_uid']
    episode, sep, number = decision_frame.rpartition(':f')
    if episode != claim['episode_uid'] or not sep or not number.isascii() or not number.isdecimal():
        raise IntegrityError('Approach decision has an invalid frame')
    current = int(number)
    if reader.cutoff['capture_seq'] > current:
        raise IntegrityError('Approach evidence postdates the decision')
    anchors = sorted((dict(frame=uid, seq=graph['views'][uid]['capture_seq'], room=node.get('room_type_hint'))
                      for uid,node in graph['vsm']['anchors'].items()
                      if graph['views'][uid]['capture_seq'] < current), key=itemgetter('seq'))
    frames = {a['frame']: a['seq'] for a in anchors}
    early, late = frames[src['before']], frames[src['inside']]
    if not 0 < early < late <= reader.cutoff['capture_seq']:
        raise IntegrityError('Approach views outside the historical interval')
    edges = [dict(id=e['id'], src=e['src'], dst=e['dst']) for e in graph['edges']
             if e['type']=='traversed' and early < graph['views'][e['dst']]['capture_seq'] <= late]
    return dict(request_id=claim['request_id'], decision_id=claim['decision_id'], pin=reader.snapshot_id,
                epoch=reader.identity['episode_uid'], cutoff=dict(reader.cutoff), anchors=anchors, edges=edges)



def _evo_crop_witness(uid, proposal, graph, active, owners, visibility, camera, labels):
    """Derive the author row and unique camera row independently of the selector."""
    import numpy as np
    scene = graph['scene_state']
    oid = proposal['object_id']
    epoch = scene['epoch']
    if (type(oid) is not int or (uid, oid) not in visibility or
            oid not in graph['vsm']['anchors'][uid]['objects'] or oid not in active):
        raise IntegrityError('Evo crop has no pinned visible active object')
    prompt = scene['views'][uid]['prompt']
    if not prompt or oid not in prompt['obj_id']:
        raise IntegrityError('Evo crop has no source prompt row')
    p = prompt['obj_id'].index(oid)
    cls = prompt['class_id'][p]
    source_box = prompt['xyxy'][p]
    matches = [d for d in owners.get((uid, oid), ())
               if camera['class_ids'][d] == cls and np.array_equal(camera['xyxy'][d], source_box)]
    if len(matches) != 1 or not 0 <= cls < len(labels):
        raise IntegrityError('Evo crop lacks a unique source detection')
    d, = matches
    height, width = graph['views'][uid]['detection_record']['metadata']['image_hw']
    x, y, xx, yy = map(int, source_box)
    x, xx, _ = slice(max(0, x), max(x + 1, xx)).indices(width)
    y, yy, _ = slice(max(0, y), max(y + 1, yy)).indices(height)
    if x >= xx or y >= yy:
        raise IntegrityError('Evo crop is empty')
    witnessed = dict(kind='crop', member=f'{uid}:d{d:05d}', index=d, label=labels[cls],
                     aggregate_label=active[oid]['class_name'], object_id=oid, object_epoch=epoch,
                     box_xyxy=[x, y, xx, yy], prompt_row=p)
    if canonical(witnessed) != canonical({k:proposal[k] for k in witnessed}):
        raise IntegrityError('Compiled Evo crop differs from camera, source member or owner')
    return dict(witnessed, raw_xyxy=source_box, source_class_id=cls)


def _evo_witness(reader, claim):
    from ..retrieval.contracts import CategoryVocabulary
    from ..retrieval.protocol import native_slot_indices
    from .archive import digest
    if reader.snapshot_id != claim['snapshot_id'] or reader.identity['episode_uid'] != claim['episode_uid']:
        raise IntegrityError('Evo witness crossed episode or pin')
    graph = reader._graph
    scene, vsm, views = graph.get('scene_state') or {}, graph.get('vsm') or {}, graph['views']
    order = scene.get('anchor_keys',[])
    nodes = vsm.get('anchors',{})
    if len(order) != len(set(order)) or set(order) != set(nodes):
        raise IntegrityError('Evo source anchor enumeration differs')
    current = claim['env_step'] + 1
    if (claim['frame_uid'] != f"{claim['episode_uid']}:f{current:06d}" or
            reader.cutoff['capture_seq'] > current or claim['event_seq'] <= reader.cutoff['event_seq']):
        raise IntegrityError('Evo witness has invalid current frame or publication clock')
    visible = {(u, o) for u, o in vsm.get('visibility_edges',[])}
    if visible != {(u, o) for u, node in nodes.items() for o in node['objects']}:
        raise IntegrityError('Evo visible edges differ from anchor objects')
    active = {}
    members = {}
    owners = {}
    for e in graph['entities']:
        if e['status'] != 'active' or e['epoch'] != scene['epoch']:
            continue
        oid = e['id']
        if oid in active:
            raise IntegrityError('Duplicate active Evo owner')
        active[oid] = e
        for member in e['members']:
            u, _, suffix = member.rpartition(':d')
            if u not in nodes:
                continue
            if not suffix.isascii() or not suffix.isdecimal():
                raise IntegrityError('Invalid Evo camera detection ordinal')
            d = int(suffix)
            if member != f'{u}:d{d:05d}' or member in members:
                raise IntegrityError('Invalid or multiply owned Evo member')
            members[member] = oid
            owners.setdefault((u, oid), []).append(d)
    rooms = {}
    for uid in order:
        rooms.setdefault(nodes[uid].get('room_type_hint') or 'unknown', dict(A=0,F=0,O=0))['A'] += 1
    for obj in scene.get('objects',[]):
        representative = obj.get('image')
        if representative in nodes:
            rooms[nodes[representative].get('room_type_hint') or 'unknown']['O'] += 1
    by_count = sorted(rooms, key=lambda name: -rooms[name]['A'])
    room_line = 'Rooms(now): ' + '; '.join(f"{room}:A{rooms[room]['A']}/F0/O{rooms[room]['O']}" for room in by_count[:8])
    if [line for line in claim['summary'].splitlines() if line.startswith('Rooms(now):')] != ([room_line] if rooms else []):
        raise IntegrityError('Evo room counts differ from the historical publication')
    eligible = sum(uid != claim['frame_uid'] for uid in order)
    coverage = dict(views=len(views), anchors=len(order), eligible_anchors=eligible,
                    entities=len(graph['entities']), edges=len(graph['edges']), visibility=len(visible))
    if any(type(claim['coverage'].get(k)) is not int or claim['coverage'][k] != v for k,v in coverage.items()):
        raise IntegrityError('Evo coverage differs from the historical publication')
    selected = claim['coverage']['selected_anchors']
    rejected = [d['frame'] for d in claim['dropped'] if d['role'] == 'whole_group']
    delivered = [a['uid'] for a in claim['anchors']]
    all_uids = rejected + delivered
    independent_material=(claim.get('map_image') or {}).get('role')=='global' or bool(claim.get('context_groups'))
    if (type(selected) is not int or not 0 <= selected <= eligible
            or selected==0 and (eligible!=0 or not independent_material) or len(all_uids) != selected
            or len(set(all_uids)) != len(all_uids) or not set(all_uids) <= set(order) or claim['frame_uid'] in all_uids):
        raise IntegrityError('Evo selected/dropped anchor identities disagree')
    coverage['selected_anchors'] = selected
    vocab = CategoryVocabulary.from_file(Path(__file__).resolve().parents[4]/'vendor_sources/EvoMemNav/data/scannet200_classes.txt')
    model_identity=graph.get('model_identity') or {}
    if (order or model_identity) and vocab.source_sha256!=model_identity.get('vocabulary_sha256'):
        raise IntegrityError('Evo witness detector vocabulary mismatch')
    native = {step:i for i,step in enumerate(native_slot_indices(current,claim['native_slots']),1) if step is not None}
    witnesses = []
    attachments = 0
    for a in claim['anchors']:
        uid = a['uid']
        view, node = views[uid], nodes[uid]
        step = view['env_step']
        slot = native.get(step)
        if slot is not None and a['native_slot'] is None:
            import numpy as np
            pixels=reader.get_view(uid,include_images=True,include_depth=False)
            if not np.array_equal(pixels['raw_rgb'],pixels['host_view']):
                slot=None
        room = node.get('room_type_hint') or 'unknown'
        if (view['capture_seq'] > reader.cutoff['capture_seq'] or view['source_event_seq'] > reader.cutoff['event_seq']
                or view['capture_seq'] != step + 1 or step >= claim['env_step'] or
                canonical([step, slot, room]) != canonical([a['step'], a['native_slot'], a['room']])):
            raise IntegrityError('Evo historical anchor frame, native slot or room differs')
        evidence = []
        if a['evidence']:
            cam = reader.get_view_class_ids(uid, include_boxes=True)
            if cam['frame_uid'] != uid or cam['snapshot_id'] != reader.snapshot_id or cam['status'] != 'available':
                raise IntegrityError('Unbound Evo camera source')
            evidence = [_evo_crop_witness(uid,c,graph,active,owners,visible,cam,vocab.labels) for c in a['evidence']]
            if len({c['object_id'] for c in evidence}) != len(evidence):
                raise IntegrityError('Duplicate crop for one visible object')
        attachments += len(evidence) + int(slot is None)
        witnesses.append(dict(uid=uid, step=step, source_anchor_index=order.index(uid), room=room, native_slot=slot,
                              evidence=evidence, visibility=[[uid,c['object_id']] for c in evidence]))
    routes=claim.get('anchor_routes',[])
    if routes:
        from ..retrieval.evo_host import recorded_anchor_route,_route_edges
        kept={a['step']:a for a in claim['anchors']}
        ordered=sorted(kept)
        allowed=set(zip(ordered,ordered[1:]))
        seen=set()
        edge_index=_route_edges(reader)
        for route in routes:
            pair=(route['from_step'],route['to_step'])
            if pair not in allowed or pair in seen:raise IntegrityError('Invalid delivered anchor interval')
            seen.add(pair)
            expected=recorded_anchor_route(reader,kept[pair[0]],kept[pair[1]],edge_index)
            if canonical(route)!=canonical(expected):raise IntegrityError('Anchor route differs from recorded movement')
    door_groups=claim.get('door_regions',[])
    if door_groups:
        from ..retrieval.evo_host import observed_door_boxes,door_region_caption,door_current_support
        kept={a['uid']:a for a in claim['anchors']}
        used=set()
        for group in door_groups:
            uid=group['frame_uid']
            if uid not in kept or uid in used:raise IntegrityError('Door region lacks a unique delivered parent view')
            used.add(uid)
            expected=observed_door_boxes(reader,uid)
            if not expected or not expected['boxes']:raise IntegrityError('Missing source door boxes')
            map_manifest=(claim.get('map_image') or {}).get('manifest',{})
            tag='A'+str(kept[uid]['step'] if map_manifest.get('label_scheme')=='source_identity_v1' else order.index(uid)+1)
            if 'current_support' in group:
                ref=group['current_support']
                if type(ref['decision_event']) is not int or ref['decision_event']>=claim['event_seq']:
                    raise IntegrityError('Door projection clock differs')
                expected['current_support']=door_current_support(reader,uid,claim['frame_uid'],ref['current_snapshot'],ref['decision_event'])
            expected.update(map_anchor=tag,caption=door_region_caption(expected,kept[uid],tag))
            if canonical(group)!=canonical(expected):raise IntegrityError('Door region differs from its source grid or map anchor')
    context=claim.get('context_groups',[])
    edge_index={row['id']:row for row in graph['edges']} if context else {}
    context_receipts={}
    for block in context:
        group=block['group']
        endpoints={v['uid'] for v in group['views']}
        if len(endpoints)!=len(group['views']) or group['seed_ref'] not in endpoints or block['seed']!=group['seed_ref']:
            raise IntegrityError('Evo context witness lacks seed')
        for v in group['views']:
            u=v['uid']
            if (u not in views or views[u]['env_step']!=v['step'] or v['step']>=claim['env_step']
                    or views[u]['capture_seq']!=v['capture_seq'] or v['capture_seq']>reader.cutoff['capture_seq']):
                raise IntegrityError('Evo context view witness differs')
        for e in group['edges']:
            stored=edge_index.get(e['id'])
            if (stored is None or {e['src'],e['dst']}-endpoints or
                    any(stored[k]!=e[k] for k in ('type','src','dst'))):
                raise IntegrityError('Evo context edge witness differs')
        for item in group['visibility']:
            member=item['member'];uid=item['uid'];oid=item['object_id']
            if ((uid,oid) not in visible or uid not in endpoints or members.get(member)!=oid or
                    member.rpartition(':d')[0]!=uid or item['epoch']!=scene['epoch']):
                raise IntegrityError('Evo context visibility witness differs')
        from ..retrieval.evo_context_host import context_facts
        refs={v['uid']:v for v in group['views']}
        facts=context_facts(reader,group,refs,edge_index,vocab,context_receipts)
        expected='Historical evidence around step '+str(views[block['seed']]['env_step'])+': '+ '; '.join(facts)+'.'
        if not facts or block['text']!=expected:
            raise IntegrityError('Sealed context text differs from its source facts')
    map_trace_digest=None
    map_proof=claim.get('map_image')
    if map_proof is not None:
        from ..retrieval.evo_map_image import render_evo_map
        from ..retrieval.host_input_compiler import pixel_hash
        if map_proof.get('role')=='global':
            from ..retrieval.evo_global_map import global_map_caption,render_global_map
            overlay=map_proof['manifest'].get('camera_overlay')
            args={'grounded':True} if map_proof['manifest'].get('node_summary')=='grounded' else {}
            if map_proof['manifest'].get('label_scheme')=='source_identity_v1':args['source_labels']=True
            if overlay is not None:
                clock=map_proof.get('decision_event')
                if type(clock) is not int or clock>=claim['event_seq']:
                    raise IntegrityError('Invalid camera overlay decision clock')
                args.update(camera_source=overlay['snapshot_id'],decision_event=clock)
            image,manifest=render_global_map(reader,claim['frame_uid'],**args)
            compact={k:manifest[k] for k in ('schema_version','snapshot_id','episode_uid','cutoff','pose_map_version','current_uid','current_status','coverage','caption')}
            if 'label_scheme' in manifest:compact.update(label_scheme=manifest['label_scheme'],object_epoch=manifest['object_epoch'])
            if 'node_summary' in manifest:compact['node_summary']=manifest['node_summary']
            if 'camera_overlay' in manifest:compact['camera_overlay']=manifest['camera_overlay']
            nodes=[v['caption'] for v in manifest['nodes']['anchors']+manifest['nodes']['objects']]
            sent=map_proof['node_captions']
            if (digest(canonical(manifest))!=map_proof['full_manifest_hash']
                    or map_proof.get('caption')!=global_map_caption(manifest,map_proof.get('caption_style','full'))
                    or type(map_proof['omitted_node_count']) is not int or map_proof['omitted_node_count']<0
                    or len(set(sent))!=len(sent) or any(v not in nodes for v in sent)
                    or len(sent)+map_proof['omitted_node_count']!=len(nodes)):
                raise IntegrityError('Global map node binding differs')
        else:
            image,manifest=render_evo_map(reader,claim['anchors'],claim['frame_uid'])
            compact=manifest
        if image is None or pixel_hash(image)!=map_proof['pixel_hash'] or canonical(compact)!=canonical(map_proof['manifest']):
            raise IntegrityError('Derived topology image cannot be reproduced on its historical pin')
        import hashlib
        map_trace_digest=hashlib.sha256(image.mode.encode()+str(image.size).encode()+image.tobytes()).hexdigest()
        attachments+=1
    if attachments != claim['attachment_slots']:
        raise IntegrityError('Evo material attachment count differs')
    return dict(schema_version=1, kind='evo_compiled_witness', episode_uid=claim['episode_uid'],
                request_id=claim['request_id'], decision_id=claim['decision_id'], event_seq=claim['event_seq'],
                frame_uid=claim['frame_uid'], pin=reader.snapshot_id, cutoff=dict(reader.cutoff),
                room_counts=rooms, coverage=coverage, anchor_order_sha256=digest(canonical(order)),
                compiled_anchor_count=len(witnesses), attachment_slots=attachments, anchors=witnesses,**({'anchor_routes':routes} if routes else {}),map_image=map_proof,map_trace_digest=map_trace_digest,context_groups=context,**({'door_regions':door_groups} if door_groups else {}))


def seal_decision_reads(memory, work, result, flow, plan):
    grouped = {}
    for kind, claim in decision_reads(json_rows(flow, max_bytes=plan['max_trace_raw_bytes'])):
        grouped.setdefault(kind, []).append(claim)
    streams = {}
    for kind, claims in grouped.items():
        witness = {'approach_reads':_approach_witness, 'object_reads':_object_witness, 'evo_reads':_evo_witness}[kind]
        streams[kind] = _seal_witnesses(memory, work, result, kind, claims, witness, plan)
    return streams


def _seal_witnesses(memory,work,result,kind,claims,witness,plan):
    claims.sort(key=itemgetter('snapshot_id'))
    root=inside(work,memory)
    if not (root/'CURRENT.json').is_file():raise IntegrityError('Object decision source map missing at seal')
    from tempfile import NamedTemporaryFile
    temporary=None
    try:
        with NamedTemporaryFile(dir=work,prefix=kind+'-',suffix='.jsonl',delete=False)as stream:
            temporary=Path(stream.name);total=0
            for sid,batch in groupby(claims,key=itemgetter('snapshot_id')):
                with closing(load_episode(root,revision=sid)) as reader:
                    for claim in batch:
                        line=canonical(witness(reader,claim))+b'\n';total+=len(line)
                        if total>plan['max_trace_raw_bytes']:raise IntegrityError('Object decision evidence exceeds retained stream limit')
                        stream.write(line)
        return compress_jsonl(temporary,result/(kind+'.jsonl.gz'),max_raw=plan['max_trace_raw_bytes'],
                              max_compressed=plan['max_trace_compressed_bytes'])
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
