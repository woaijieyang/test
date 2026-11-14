"""Host adaptation of the upstream ordered anchor evidence; one pinned read per generation."""
from contextlib import contextmanager,nullcontext
from dataclasses import dataclass
from pathlib import Path
import sys

import numpy as np
from PIL import Image

from .contracts import MemoryQuery
from .host_input_compiler import ImageSlot,PreparedHistory,pixel_hash
from ..storage.store import IntegrityError,load_episode
from ..storage.archive import UnavailableMaterial


@contextmanager
def _upstream_path():
    # The host does not inherit the graph worker's import path. Only import the
    # upstream pure rank/prompt modules; no agent, Habitat scene or HTTP client.
    root=str(Path(__file__).resolve().parents[4]/'vendor_sources/EvoMemNav')
    inserted=root not in sys.path
    if inserted:sys.path.insert(0,root)
    try:yield
    finally:
        if inserted:sys.path.remove(root)


@dataclass(frozen=True)
class PinnedEvidence:
    root: Path
    snapshot_id: str
    episode_uid: str
    material: dict
    camera_offsets: dict
    traces: dict
    context: tuple=()


def verify_evo_reply(reader,reply,raw_query,current,vocabulary,*,include_relations=False,include_context=False):
    """Independent host read of the same pinned metadata before rendering any worker proposal."""
    from .evo_material import read_evo_material
    fields=dict(raw_query)
    fields.pop('decision_id',None)
    query=MemoryQuery(**dict(fields,current_position=current.position,pose_map_version=current.pose_map_version))
    with _upstream_path():
        expected=read_evo_material(reader,query,vocabulary)
    if reply.get('evo_material')!=expected:
        raise IntegrityError('Evo material differs from the host-pinned sources')
    if 'channels' in reply and reply['channels']!={'EvoAnchor':[item['uid'] for item in expected['anchors']]}:
        raise IntegrityError('Evo channel order differs from the verified source anchors')
    context=()
    if include_context:
        from .evo_context_host import verify_context
        context=tuple(verify_context(reader,query,current,reply['evo_context'],vocabulary))
    elif 'evo_context' in reply:
        raise IntegrityError('Unexpected Q/V/C context for reproduction baseline')
    offsets={};traces={}
    if not include_relations:
        return PinnedEvidence(reader.root,reader.snapshot_id,query.episode_uid,expected,offsets,traces,context)
    if current.source_snapshot_id is not None:
        with (nullcontext(reader) if current.source_snapshot_id==reader.snapshot_id else
              closing_reader(reader.root,current.source_snapshot_id)) as live:
            row=live.get_view(current.frame_uid,include_images=False,include_depth=False)
            if (live.identity['episode_uid']!=query.episode_uid or row['frame_uid']!=current.frame_uid
                    or row['capture_seq']!=current.capture_seq or row['snapshot_id']!=current.source_snapshot_id):
                raise IntegrityError('Unbound current camera in topology material')
            valid=(row.get('T_G_cv') is not None and current.pose_map_version is not None
                   and row.get('pose_map_version')==current.pose_map_version==reader.versions['pose_map_version'])
            for anchor in expected['anchors']:
                uid=anchor['uid'];old=reader._graph['views'][uid]
                if valid and old.get('T_G_cv') is not None and old.get('pose_map_version')==current.pose_map_version:
                    off=np.linalg.solve(np.asarray(row['T_G_cv']),np.asarray(old['T_G_cv']))[:3,3]
                    if not np.isfinite(off).all():raise IntegrityError('Invalid relative camera position')
                    offsets[uid]=[round(float(value),2) for value in off]
    ordered=sorted(expected['anchors'],key=lambda a:a['step'])
    edge_index=_route_edges(reader)
    for earlier,later in zip(ordered,ordered[1:]):
        traces[later['uid']]=recorded_anchor_route(reader,earlier,later,edge_index)
    return PinnedEvidence(reader.root,reader.snapshot_id,query.episode_uid,expected,offsets,traces,context)



def _route_edges(reader):
    rows=reader._graph['edges']
    result={e['id']:e for e in rows}
    if len(result)!=len(rows):raise IntegrityError('Duplicate published route edge identity')
    return result


def recorded_anchor_route(reader,earlier,later,edge_index):
    """Read executed primitives along the temporal chain; never infer a shortcut or reverse edge."""
    start=earlier['step']+1;end=later['step']+1
    views=reader._graph['views']
    if (not 1<=start<end<=reader.cutoff['capture_seq'] or
            views[earlier['uid']]['capture_seq']!=start or views[later['uid']]['capture_seq']!=end):
        raise IntegrityError('Invalid anchor route endpoints or cutoff')
    runs=[];edges=[];prev=earlier['uid']
    for seq,item in enumerate(reader.get_trace(start+1,end),start+1):
        if item['pre']!=prev or seq>end or item['post'] not in views or views[item['post']]['capture_seq']!=seq:
            raise IntegrityError('Historical path discontinuity')
        action=item['action']['action_id'];collision=item['action']['collision']
        if type(action) is not int or (collision is not None and type(collision) is not bool):
            raise IntegrityError('Invalid historical action or collision feedback')
        motion=item['motion'];edge=motion.get('traversed')
        if edge is not None and (action!=1 or collision is not False or edge['src']!=prev or edge['dst']!=item['post']):
            raise IntegrityError('Contradictory traversed source')
        for kind,record in [('temporal_next',motion['temporal']),('traversed',edge)]:
            if record is None:
                if kind=='temporal_next':raise IntegrityError('Missing historical sequence edge')
                continue
            if (record.get('type')!=kind or record.get('src')!=prev or record.get('dst')!=item['post']
                    or edge_index.get(record['id'])!=dict(record)):
                raise IntegrityError('Historical route edge differs from published graph')
        label={0:'stop',1:'forward',2:'left turn',3:'right turn'}.get(action,'other action')
        if collision is True:label+=' (collision)'
        elif collision is None:label+=' (feedback unknown)'
        elif action==1:label+=' (measured)' if edge else ' (no measured traversal)'
        if runs and runs[-1][0]==label:runs[-1][1]+=1
        else:runs.append([label,1])
        edges.append(motion['temporal']['id'])
        if edge is not None:edges.append(edge['id'])
        prev=item['post']
    if prev!=later['uid']:raise IntegrityError('Historical path misses endpoint')
    return dict(start_uid=earlier['uid'],from_step=start-1,to_step=end-1,runs=runs,edge_ids=edges)


def anchor_route_caption(route):
    labels={'forward (measured)':'verified forward movement','forward (collision)':'forward attempt with collision',
            'forward (no measured traversal)':'forward attempt without a measured traversal',
            'forward (feedback unknown)':'forward attempt with unknown feedback'}
    steps='; '.join(f"{labels.get(action,action)} x{count}" for action,count in route['runs'])
    return f"Past actions from A{route['from_step']} to A{route['to_step']}, in order: {steps}. Current and reverse passability unknown."


@contextmanager
def closing_reader(root,pin,image_cache=None,page_cache=None):
    reader=load_episode(root,revision=pin,image_cache=image_cache,_history_cache=page_cache)
    try:yield reader
    finally:reader.close()


def _proposal_text(item,idx,source_slot,offset):
    where=f"native image {source_slot}" if source_slot else "historical full view"
    caption=f"Anchor View {idx} (room: {item['room']}; observed at step {item['step']}; {where})."
    if offset is not None:
        caption+=f" Earlier camera relative to the current camera in metres [right, down, forward]: {offset}."
    return caption


def observed_door_boxes(reader,uid):
    """Frame-local pre-filter detector boxes on the original RGB grid."""
    from ..storage.store import clip_detection_box
    record=reader.get_observed_doors(uid,include_masks=False)
    if record.get('snapshot_id')!=reader.snapshot_id or record.get('frame_uid')!=uid:
        raise IntegrityError('Structural door proposal crossed frame or revision')
    if record['status']!='available':
        if record['status'] not in ('not_recorded','unavailable'):raise IntegrityError('Unexpected door evidence status')
        return None
    height,width=record['image_hw']
    boxes=[]
    for i in range(record['count']):
        rect=clip_detection_box(record['door_xyxy'][i],(height,width))
        if rect is not None:
            boxes.append(dict(proposal_index=int(record['door_proposal_indices'][i]),box_xyxy=list(map(int,rect))))
    return dict(frame_uid=uid,source_ref=record['source_ref']['sha256'],raw_signature=record['raw_signature'],
                image_hw=[height,width],boxes=boxes)


def door_current_support(history,source_uid,current_uid,current_pin,decision_event):
    from types import SimpleNamespace
    from .semantic_topology import observed_door_support
    with (nullcontext(history) if current_pin==history.snapshot_id else
          closing_reader(history.root,current_pin,page_cache=getattr(history,'history_page_cache',None))) as live:
        current=live.get_camera_pose_view(current_uid)
        old=history.get_camera_pose_view(source_uid)
        now=current['capture'];past=old['capture'];ep=history.identity['episode_uid']
        for row,cap,reader,uid in [(current,now,live,current_uid),(old,past,history,source_uid)]:
            if (reader.identity['episode_uid']!=ep or row['snapshot_id']!=reader.snapshot_id
                    or row['frame_uid']!=uid or cap['frame_uid']!=uid or cap['episode_uid']!=ep
                    or row['capture_seq']!=cap['capture_seq'] or row['source_event_seq']!=cap['event_seq']
                    or cap['capture_seq']>reader.cutoff['capture_seq'] or cap['event_seq']>reader.cutoff['event_seq']):
                raise IntegrityError('Door projection observation differs from source pin')
        if (current['capture_seq']!=live.cutoff['capture_seq'] or not old['capture_seq']<current['capture_seq']
                or not past['event_seq']<now['event_seq']<decision_event or now['pose_record']['source']!='simulator_ground_truth'
                or now['pose_record']['episode_instance']!=past['pose_record']['episode_instance']):
            raise IntegrityError('Door projection crossed a session or decision cutoff')
        from ...observation_pose.provider_contract import validate_simulator_pose_record
        from ..geometry.core import Q
        for row,cap,reader in [(old,past,history),(current,now,live)]:
            try:pose=validate_simulator_pose_record(cap['pose_record'],cap['T_base_camera'])
            except (TypeError,ValueError) as error:raise IntegrityError('Door projection pose or calibration differs') from error
            if pose.episode_id!=ep or pose.frame_id!=cap['frame_uid'] or pose.timestamp_ns!=cap['sensor_timestamp_ns']:
                raise IntegrityError('Door projection pose identity differs')
            if not pose.valid or pose.map_version!=reader.versions['pose_map_version']:return None
            if row['T_G_cv'] is None or not np.allclose(row['T_G_cv'],Q@np.asarray(cap['pose_record']['T_map_camera_cv']),rtol=0,atol=1e-9):
                raise IntegrityError('Door projection camera transform differs from calibrated pose')
        ref=SimpleNamespace(episode_uid=ep,snapshot_id=history.snapshot_id,source_snapshot_id=current_pin,
            capture_seq=current['capture_seq'],frame_uid=current_uid,pose_map_version=current['pose_map_version'])
        data=observed_door_support(history,live,source_uid,ref,locate=True)
        if data['status']!='available':return None
        return dict(current_snapshot=current_pin,current_uid=current_uid,decision_event=decision_event,
                    current_step=now['env_step'],current_hw=data['current_hw'],source_calibration=past['calibration_hash'],
                    current_calibration=now['calibration_hash'],regions=[
                    {k:r[k] for k in ('proposal_index','source_samples','projected_pixels','comparable_depths',
                                      'shared_samples','supported_xyxy','sampling_stride','tolerance_m')}
                    for r in data['regions']])


def door_region_caption(group,anchor,tag):
    step=anchor['step'];slot=anchor['native_slot']
    photo=f'native image {slot}' if slot is not None else 'the historical full view above'
    h,w=group['image_hw']
    regions=', '.join(f"r{box['proposal_index']} {box['box_xyxy']}" for box in group['boxes'])
    caption=(f"Possible door regions seen from {tag} at step {step}, in {photo} "
            f"(source {w}x{h} pixels; boxes left, top, right, bottom): {regions}. "
            "Frame-local detections; doorway identity and passability unknown.")

    support=group.get('current_support')
    if support:
        measurements=[]
        h,w=support['current_hw']
        for row in support['regions']:
            n=row['source_samples'];p=row['projected_pixels'];a=row['shared_samples']
            if a:
                box=row['supported_xyxy']
                side='left half' if box[2]<=w/2 else 'right half' if box[0]>=w/2 else 'across the image center'
                evidence=f"{a}/{n} sampled surface points agree in depth, {side}; extent {box}"
            elif not n:evidence="no valid source depth samples"
            elif not p:evidence=f"all {n} sampled points outside current view"
            else:evidence=f"{p}/{n} project inside; {row['comparable_depths']} comparable depths, none agree"
            measurements.append(f"r{row['proposal_index']}: "+evidence)
        caption+=f" Current RGB slot 8, step {support['current_step']} ({w}x{h} pixels): "+'; '.join(measurements)+'.'
    return caption


def compile_evo(decision,question,prompt_fn,tokenize,per_image,limit):
    """Budget complete author-ordered groups before decoding RGB; preserve the original question."""
    proof=decision.evo_evidence
    with closing_reader(proof.root,proof.snapshot_id,getattr(decision.hook,'retrieval_image_cache',None),
                        getattr(decision.hook,'retrieval_page_cache',None)) as reader:
        if reader.identity['episode_uid']!=proof.episode_uid:
            raise IntegrityError('Evo material lease crossed episode')
        return _compile_pinned(decision,question,prompt_fn,tokenize,per_image,limit,reader)


def _compile_pinned(decision,question,prompt_fn,tokenize,per_image,limit,reader):
    proof=decision.evo_evidence
    with _upstream_path():
        from evomemnav.vlm.prompts import AnchorPromptItem,build_selection_query
    groups=proof.material['anchors'];native=decision.history
    native_slots={s.frame_uid:s.index for s in native.slots if s.frame_uid and s.raw_pixel_hash==s.host_pixel_hash}
    summary=proof.material['summary']
    global_mode=decision.settings.get('global_map',False)
    global_info=None;global_image=None;global_caption='';map_nodes=[];omitted_nodes=[]
    anchor_tags={};object_tags={}
    if global_mode:
        from .evo_global_map import MapTileColumns,global_map_caption,render_global_map
        camera_args={'grounded':True} if decision.settings.get('grounded_node_summary') else {}
        if decision.settings.get('source_node_labels'):camera_args['source_labels']=True
        src=native.slots[-1]
        if decision.settings.get('current_camera_overlay') and src.source_snapshot_id!=reader.snapshot_id:
            camera_args.update(camera_source=src.source_snapshot_id,decision_event=decision.event['event_seq'])
        if decision.hook is None:
            global_image,global_info=render_global_map(reader,native.slots[-1].frame_uid,**camera_args)
        else:
            cache=getattr(decision.hook,'global_map_tile_cache',None)
            if cache is None:
                capacity=decision.hook.profile['map_memory']['geometry']['max_resident_tiles']
                cache=MapTileColumns(reader,capacity)
                decision.hook.global_map_tile_cache=cache
            hits,decodes=cache.hits,cache.decodes
            global_image,global_info=render_global_map(reader,native.slots[-1].frame_uid,tile_cache=cache,**camera_args)
            decision.emit('GlobalMapTileRead',snapshot_id=reader.snapshot_id,hits=cache.hits-hits,
                          decodes=cache.decodes-decodes,resident_tiles=len(cache.items))
        if global_info['episode_uid']!=proof.episode_uid or global_info['snapshot_id']!=proof.snapshot_id:
            raise IntegrityError('Global topology image crossed its publication')
        if global_image is None:
            # A missing geometry layer does not invalidate independently pinned anchors.
            global_mode=False
            decision.emit('GlobalMapUnavailable',snapshot_id=proof.snapshot_id,reason=global_info['reason'])
            if not groups and not proof.context:
                decision.use_uniform('global_map_'+global_info['reason'])
                return question
        elif global_image.mode!='RGB' or global_image.size!=(512,512):
            raise IntegrityError('Invalid global topology image')
    if global_mode:
        anchor_tags={a['uid']:a['id'] for a in global_info['nodes']['anchors']}
        object_tags={(o['epoch'],o['id']):o['map_id'] for o in global_info['nodes']['objects']}
        global_caption=global_map_caption(global_info)
    if not groups and not proof.context and not global_mode:
        decision.use_uniform('no_historical_anchor_material')
        return question
    prefix='\nHistorical graph memory through observation step '+str(decision.evo_cutoff_step)+'. Room names are visual hints; frontier evidence is not enabled.\n'
    if global_mode and decision.settings.get('grounded_node_summary'):prefix='\n'
    def fits(text,k):
        ids=tokenize(prompt_fn(question+text)).reshape(-1)
        return len(ids)+(native.budget+k+int(global_mode))*(per_image-1)+256<=limit
    # Use the upstream parts builder for ordering and crop-to-parent grouping. The
    # token/role plan uses opaque image references until we know the budget fits.
    delivered_context=[]
    anchor_routes=[]
    door_regions={}
    def render(selected):
        items=[];lookup={};source_ids={a['uid'] for a,crops in selected}
        for j,(a,crops) in enumerate(selected):
            full=('whole',a['uid']);lookup[full]=(j,a,None)
            evidence=[]
            for d in crops:
                crop=('crop',a['uid'],d['member']);lookup[crop]=(j,a,d)
                evidence.append((d['aggregate_label'],crop))
            items.append(AnchorPromptItem(full,a['room'],evidence))
        parts=build_selection_query(question='',goal_image=None,egocentric_view=None,topo_summary=summary,
                                    anchors=items,frontiers=[])
        text=prefix+global_caption
        if global_mode:
            if map_nodes:
                if decision.settings.get('grounded_node_summary'):
                    text+='\n'.join(n['caption']+'.' for n in map_nodes)+'\n'
                else:text+='Map node descriptions: '+'; '.join(n['caption'] for n in map_nodes)+'.\n'
            if omitted_nodes:text+=f"{len(omitted_nodes)} more node descriptions omitted for context; the map still covers the full publication.\n"
        assets=[];facts=[]
        for part in parts[1:]:  # target question and current RGB already occupy native positions
            if isinstance(part,str):
                if part.startswith('Shortlisted Frontier') or part.startswith('No Frontier'):continue
                text+=part+'\n'
                continue
            _,ref=part;j,a,d=lookup[ref];uid=a['uid']
            if d is None:
                idx=native_slots.get(uid)
                text+=_proposal_text(a,j,idx,proof.camera_offsets.get(uid))+'\n'
                if global_mode:text+=f"Map node {anchor_tags[uid]} is the observing camera for this group.\n"
                if idx is None:text+='<image>\n';assets.append((a,None))
                if uid in door_regions:
                    text+=door_regions[uid]['caption']+'\n'
                traces=proof.traces.get(uid)
                if traces and traces['start_uid'] in source_ids:
                    evidence=', '.join(f'{count} {act}' for act,count in traces['runs'])
                    text+=f"Recorded steps {traces['from_step']} to {traces['to_step']} in order: {evidence}.\n"
                    facts.append(traces)
            else:
                text+=f"Anchor View {j} detail from step {a['step']}, possible {d['label']}"
                if global_mode:text+=f" (map object {object_tags[(d['object_epoch'],d['object_id'])]} observed from {anchor_tags[uid]})"
                if d['label']!=d['aggregate_label']:text+=f" (fused label: {d['aggregate_label']})"
                text+=f"; source pixel box {d['box_xyxy']}: <image>\n";assets.append((a,d))
        for route in anchor_routes:text+=anchor_route_caption(route)+'\n'
        for section in delivered_context:text+=section['text']+'\n'
        return text,assets,facts
    kept=[];dropped=[]
    caption_style='full'
    if global_mode:
        # First price the complete map and its legend, including the true omitted count.
        # Only shorten the legend when the actual tokenizer requires it.
        omitted_nodes.extend(global_info['nodes']['anchors']+global_info['nodes']['objects'])
        def map_minimum_fits():
            intro,_,_=render([])
            if fits(intro,0):return True
            map_nodes[:]=omitted_nodes;omitted_nodes.clear()
            intro,_,_=render([])
            complete_fits=fits(intro,0)
            omitted_nodes[:]=map_nodes;map_nodes.clear()
            return complete_fits
        if not map_minimum_fits():
            caption_style='compact'
            global_caption=global_map_caption(global_info,caption_style)
            if not map_minimum_fits():
                global_mode=False;global_caption=''
                dropped.append(dict(role='global_map',reason='context_budget'))
                decision.emit('GlobalMapUnavailable',snapshot_id=proof.snapshot_id,reason='context_budget')
                if not groups and not proof.context:
                    decision.use_uniform('global_map_caption_exceeds_budget')
                    return question
        omitted_nodes.clear()
    if global_mode:
        # The full map is reserved before local photos. Describe every anchor/object
        # when possible; describe omitted counts truthfully when the publication is large.
        selected_frames={a['uid'] for a in groups}
        selected_objects={(d['object_epoch'],d['object_id']) for a in groups for d in a['evidence']}
        nodes=global_info['nodes']
        all_nodes=sorted(nodes['anchors'],key=lambda a:a['uid'] not in selected_frames)+sorted(
            nodes['objects'],key=lambda o:(o['epoch'],o['id']) not in selected_objects)
        omitted_nodes.extend(all_nodes)
        # Optional node descriptions share remaining space with local evidence.
        # Reserve one highest-ranked group that can fit, including its first crop
        # when possible. render() accounts for native-slot reuse and group captions.
        def first_local():
            for a in groups:
                for evidence in ([a['evidence'][:1],[]] if a['evidence'] else [[]]):
                    trial=[(a,evidence)]
                    text,assets,_=render(trial)
                    if fits(text,len(assets)):return trial
            return []
        reserve=first_local()
        if not reserve and groups and caption_style=='full':
            # When a shorter legend recovers a local group, keep both evidence channels.
            full_caption=global_caption
            global_caption=global_map_caption(global_info,'compact')
            reserve=first_local()
            if reserve:caption_style='compact'
            else:global_caption=full_caption
        for node in all_nodes:
            omitted_nodes.remove(node);map_nodes.append(node)
            intro,assets,_=render(reserve)
            if not fits(intro,len(assets)):map_nodes.pop();omitted_nodes.append(node)
        intro,_,_=render([])
        if not fits(intro,0):
            # A complete node list can be shorter than an omitted-count notice on a tiny map.
            map_nodes[:]=all_nodes;omitted_nodes.clear()
            intro,_,_=render([])
            if not fits(intro,0):
                raise IntegrityError('Reserved global map exceeded its validated budget')
    for a in groups:
        # Keep higher-ranked whole views independently representable. A crop always
        # retains its own parent context. Truncation happens only between units.
        trial=kept+[(a,[])]
        text,assets,_=render(trial)
        if fits(text,len(assets)):kept=trial
        else:dropped.append(dict(frame=a['uid'],role='whole_group',reason='context_budget'))
    if global_mode and decision.settings.get('anchor_routes') and len(kept)>1:
        ordered=sorted((a for a,_ in kept),key=lambda a:a['step'])
        edge_index=_route_edges(reader)
        for left,right in zip(ordered,ordered[1:]):
            route=recorded_anchor_route(reader,left,right,edge_index)
            anchor_routes.append(route)
            text,assets,_=render(kept)
            if not fits(text,len(assets)):
                anchor_routes.pop()
                dropped.append(dict(role='anchor_route',from_step=left['step'],to_step=right['step'],reason='context_budget'))
    for section in proof.context:
        delivered_context.append(section)
        text,assets,_=render(kept)
        if not fits(text,len(assets)):
            delivered_context.pop()
            dropped.append(dict(role='context_bundle',seed=section['seed'],reason='context_budget'))
    terms=proof.material.get('query_sources',{})
    door_requested=any('door' in terms.get(channel,{}) for channel in ('instruction','reasoning'))
    if global_mode and decision.settings.get('structural_door_regions') and door_requested:
        for anchor,_ in kept:
            uid=anchor['uid']
            try:group=observed_door_boxes(reader,uid)
            except UnavailableMaterial as error:
                dropped.append(dict(role='door_regions',frame=uid,reason=error.reason))
                continue
            if group is None or not group['boxes']:
                dropped.append(dict(role='door_regions',frame=uid,reason='not_recorded' if group is None else 'no_valid_boxes'))
                continue
            group['map_anchor']=anchor_tags[uid]
            group['caption']=door_region_caption(group,dict(anchor,native_slot=native_slots.get(uid)),anchor_tags[uid])
            door_regions[uid]=group
            text,assets,_=render(kept)
            if not fits(text,len(assets)):
                del door_regions[uid]
                dropped.append(dict(role='door_regions',frame=uid,reason='context_budget'))
        if decision.settings.get('locate_door_regions'):
            src=native.slots[-1]
            for a,_ in kept:
                uid=a['uid'];group=door_regions.get(uid)
                if group is None:continue
                try:support=door_current_support(reader,uid,src.frame_uid,src.source_snapshot_id,decision.event['event_seq'])
                except UnavailableMaterial as error:
                    dropped.append(dict(role='door_current_support',frame=uid,reason=error.reason))
                    continue
                if support is None:
                    dropped.append(dict(role='door_current_support',frame=uid,reason='unavailable_geometry'))
                    continue
                original=group['caption']
                group['current_support']=support
                group['caption']=door_region_caption(group,dict(a,native_slot=native_slots.get(uid)),anchor_tags[uid])
                text,assets,_=render(kept)
                if not fits(text,len(assets)):
                    del group['current_support'];group['caption']=original
                    dropped.append(dict(role='door_current_support',frame=uid,reason='context_budget'))

    map_caption='Observed top-down map from this publication. Blue A labels mark observation anchors; boxes mark estimated objects. Unknown space has no recorded coverage on this slice. Recorded travel does not establish present passability: <image>\n'
    map_requested=decision.settings.get('topology_image',False)
    group_text,group_assets,_=render(kept)
    map_fits=map_requested and fits(group_text+map_caption,len(group_assets)+1)
    if map_requested and not map_fits:
        dropped.append(dict(role='topology_map',reason='context_budget'))
    missing_sources={}
    def pack_crops(reserve_map):
        rejected_crops=[]
        for _,crops in kept:
            crops.clear()
        for a,crops in kept:
            if a['uid'] in missing_sources:continue
            for det in a['evidence']:
                crops.append(det)
                text,assets,_=render(kept)
                if not fits(text+(map_caption if reserve_map else ''),len(assets)+int(reserve_map)):
                    crops.pop()
                    rejected_crops.append(dict(member=det['member'],role='crop',reason='context_budget'))
        return rejected_crops
    sources={}
    def resolve_sources(reserve_map):
        nonlocal kept
        # A newly unavailable source is excluded from every later pass. Successful
        # sources stay materialized while the compiler re-packs and re-numbers groups.
        while True:
            rejected=pack_crops(reserve_map)
            text,assets,facts=render(kept)
            unavailable=[]
            for a,det in assets:
                uid=a['uid']
                if uid in sources or uid in missing_sources:continue
                try:
                    row=reader.get_view(uid,include_images=True,include_depth=False)
                except UnavailableMaterial as error:
                    if error.reason not in ('missing_material','undecodable_image'):raise
                    missing_sources[uid]=error.reason
                    unavailable.append(a)
                    continue
                if (row['frame_uid']!=uid or row['snapshot_id']!=proof.snapshot_id or
                        row['capture']['env_step']!=a['step'] or row['capture']['episode_uid']!=proof.episode_uid):
                    raise IntegrityError('Evo source photo crossed its frame or revision')
                rgb=Image.fromarray(np.asarray(row['raw_rgb']),'RGB')
                sources[uid]=(row,rgb,pixel_hash(rgb))
            if not unavailable:return text,assets,facts,rejected
            for a in unavailable:
                uid=a['uid'];reason=missing_sources[uid]
                if uid in native_slots:
                    dropped.extend(dict(role='crop',member=d['member'],reason=reason) for d in a['evidence'])
                else:dropped.append(dict(role='whole_group',frame=uid,reason=reason))
            kept=[(a,crops) for a,crops in kept if a['uid'] not in missing_sources or a['uid'] in native_slots]
            retained_steps={a['step'] for a,_ in kept}
            anchor_routes[:]=[r for r in anchor_routes if r['from_step'] in retained_steps and r['to_step'] in retained_steps]
    suffix,assets,facts,dropped_crops=resolve_sources(map_fits)
    if not kept and not delivered_context and not global_mode:
        decision.use_uniform('no_available_evo_source' if missing_sources else 'no_evo_group_within_context')
        return question
    images=list(native.images);slots=list(native.slots)
    map_proof=None
    if global_mode:
        from ..storage.archive import canonical,digest
        value=pixel_hash(global_image)
        compact={k:global_info[k] for k in ('schema_version','snapshot_id','episode_uid','cutoff','pose_map_version','current_uid','current_status','coverage','caption')}
        if 'label_scheme' in global_info:compact.update(label_scheme=global_info['label_scheme'],object_epoch=global_info['object_epoch'])
        if 'node_summary' in global_info:compact['node_summary']=global_info['node_summary']
        if 'camera_overlay' in global_info:compact['camera_overlay']=global_info['camera_overlay']
        map_proof=dict(role='global',manifest=compact,full_manifest_hash=digest(canonical(global_info)),pixel_hash=value,
                       caption=global_caption,node_captions=[v['caption'] for v in map_nodes],
                       omitted_node_count=len(omitted_nodes))
        if caption_style!='full':map_proof['caption_style']=caption_style
        map_sources=(proof.snapshot_id,)
        if 'camera_overlay' in compact:
            map_proof['decision_event']=decision.event['event_seq']
            map_sources+=(compact['camera_overlay']['snapshot_id'],)
        images.append(global_image)
        slots.append(ImageSlot(len(images),None,None,None,'evo_global_map',map_sources,
                               None,None,None,None,value,False,proof.snapshot_id))
    map_image=None
    if map_fits:
        from .evo_map_image import render_evo_map
        current_uid=native.slots[-1].frame_uid
        map_image,manifest=render_evo_map(reader,[dict(a,evidence=ds) for a,ds in kept],current_uid)
        if map_image is None:
            dropped.append(dict(role='topology_map',reason=manifest.get('reason','unavailable_map')))
        else:
            if (manifest['snapshot_id']!=proof.snapshot_id or manifest['episode_uid']!=proof.episode_uid
                    or map_image.mode!='RGB' or map_image.size!=(512,512)):
                raise IntegrityError('Rendered topology map differs from its publication')
            value=pixel_hash(map_image);map_proof=dict(manifest=manifest,pixel_hash=value)
            # Materialize the derived map after all source image slots.
        if map_image is None:
            suffix,assets,facts,dropped_crops=resolve_sources(False)
    dropped.extend(dropped_crops)
    for a,det in assets:
        uid=a['uid']
        row,rgb,raw_hash=sources[uid]
        if det is None:
            image=rgb.resize((360,360));ref=uid;role='evo_anchor'
        else:
            box=tuple(det['box_xyxy'])
            if not (0<=box[0]<box[2]<=rgb.width and 0<=box[1]<box[3]<=rgb.height):
                raise IntegrityError('Evo crop outside source RGB')
            patch=rgb.crop(box);ratio=min(120/patch.width,120/patch.height)
            image=patch.resize((max(1,int(patch.width*ratio)),max(1,int(patch.height*ratio))))
            ref=det['member'];role='evo_crop'
        images.append(image)
        slots.append(ImageSlot(len(images),uid,a['step'],row['capture_seq'],role,(ref,),row['raw_rgb_ref']['sha256'],
                     row['host_view_ref']['sha256'],None,raw_hash,pixel_hash(image),False,proof.snapshot_id))
    if map_image is not None:
        suffix+=map_caption
        images.append(map_image)
        slots.append(ImageSlot(len(images),None,None,None,'evo_topology_map',(proof.snapshot_id,),
                               None,None,None,None,map_proof['pixel_hash'],False,proof.snapshot_id))
    lines=suffix.splitlines()
    captions=[]
    for i,line in enumerate(lines):
        if '<image>' not in line:continue
        if line.count('<image>')!=1:raise IntegrityError('Ambiguous image caption placeholder')
        begin=i
        if line.strip()=='<image>':
            begin=i-1
            if begin>=0 and lines[begin].startswith('Map node '):begin-=1
        statement='\n'.join(lines[begin:i+1])
        if begin<0 or not statement.replace('<image>','').strip():
            raise IntegrityError('Supplementary image lacks a local caption')
        captions.append(statement)
    if len(captions)!=len(slots)-native.budget:raise IntegrityError('Unpaired caption or image')
    bindings=[]
    for slot,caption in zip(slots[native.budget:],captions):
        if (slot.source_kind in ('evo_global_map','evo_topology_map') and 'map' not in caption.lower()
                or slot.source_kind=='evo_crop' and 'source pixel box' not in caption
                or slot.source_kind=='evo_anchor' and f'observed at step {slot.env_step}' not in caption):
            raise IntegrityError('Image role differs from its caption')
        bindings.append(dict(slot=slot.index,role=slot.source_kind,frame_uid=slot.frame_uid,
                             source_ref=list(slot.evidence_group),caption=caption))
    decision.combined=PreparedHistory(tuple(images),tuple(slots),proof.snapshot_id,len(images))
    decision.emit('EvoTopologyCompiled',**(dict(crop_query_schema=2,query_sources=proof.material['query_sources'])
                  if 'query_sources' in proof.material else dict(crop_query_schema=1)),snapshot_id=proof.snapshot_id,summary=summary,
                  anchors=[dict(uid=a['uid'],step=a['step'],native_slot=native_slots.get(a['uid']),room=a['room'],evidence=ds,
                                relative_camera=proof.camera_offsets.get(a['uid'])) for a,ds in kept],
                  **({'door_regions':[door_regions[a['uid']] for a,_ in kept if a['uid'] in door_regions]}
                     if decision.settings.get('structural_door_regions') else {}),
                  **({'anchor_routes':anchor_routes} if decision.settings.get('anchor_routes') else {}),
                  relations=facts,dropped=dropped,model_suffix=suffix,coverage=proof.material['coverage'],
                  native_slots=native.budget,attachment_slots=len(images)-native.budget,map_image=map_proof,context_groups=delivered_context,caption_bindings=bindings)
    return question+suffix
