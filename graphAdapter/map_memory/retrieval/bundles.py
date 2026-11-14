"""One-hop bundles; existing graph edges are evidence, not new assertions."""
from .contracts import EvidenceBundle
from ..storage.archive import IntegrityError
from .host_input_compiler import plain


def selected_relations(selection,index):
    """Extract only the source relations needed by the selected evidence groups."""
    edge_ids={ref for group in selection.groups for ref in group.execution_refs}
    entity_ids={tuple(ref)for group in selection.groups for ref in group.entity_refs}
    selected_uids={v.frame_uid for v in selection.slots}
    relations=dict(edges=[plain(e)for e in index['edges']if e['id']in edge_ids],
        entities=[dict(plain(e),view_uids=[uid for uid in e['view_uids']if uid in selected_uids])for e in index['entities']if (e['epoch'],e['id'])in entity_ids],
        visibility_edges=[list(row)for row in index['visibility_edges']if row[0]in selected_uids and (index['scene_epoch'],row[1])in entity_ids],
        scene_epoch=index['scene_epoch'])
    return relations


def singleton(bundle,reason='singleton'):
    seed=next(v for v in bundle.views if v.frame_uid==bundle.seed_ref)
    return EvidenceBundle(seed.frame_uid,(seed,),(),(),(),(seed.capture_seq,seed.capture_seq),
        seed.pose_map_version,None,bundle.relevance,tuple(sorted(set(bundle.missing_evidence)|{'endpoints_only'})),reason)


def build_bundles(candidates,index,*,pose_map_version,expand=True):
    if not expand:
        by_uid={v.frame_uid:v for v in candidates.views}
        result=[]
        for candidate in candidates.ranked:
            seed=candidate.view
            if seed.snapshot_id!=candidates.snapshot_id or by_uid.get(seed.frame_uid)!=seed:
                raise IntegrityError('Candidate does not belong to the pinned pool')
            result.append(EvidenceBundle(seed.frame_uid,(seed,),(),(),(),(seed.capture_seq,seed.capture_seq),
                pose_map_version if seed.pose_map_version==pose_map_version else None,None,candidate.score,
                ('missing_before','missing_after'),'singleton'))
        return tuple(result)
    views={v.frame_uid:v for v in candidates.views}
    adjacency={uid:{}for uid in views}
    for edge in index.get('edges',()):
        if edge['type'] not in ('temporal_next','traversed'):continue
        a,b=edge['src'],edge['dst']
        if a not in views or b not in views or a==b:continue
        if views[a].capture_seq>=views[b].capture_seq:
            raise IntegrityError('Stored forward temporal/traversed edge is not chronological')
        for src,dst in ((a,b),(b,a)):
            adjacency[src].setdefault(dst,[]).append((edge['type'],edge['id'],None))
    # Stored object membership is a co-visibility association, not proof of a
    # single physical object. Epoch is part of every object reference.
    visible={}
    for entity in index.get('entities',()):
        key=(entity['epoch'],entity['id'])
        visible.setdefault(key,set()).update(uid for uid in entity.get('view_uids',())if uid in views)
    epoch=index.get('scene_epoch')
    for uid,entity_id in index.get('visibility_edges',()):
        if uid in views and epoch is not None:visible.setdefault((epoch,entity_id),set()).add(uid)
    memberships={uid:[]for uid in views}
    for entity,uids in visible.items():
        for uid in uids:memberships[uid].append((entity,uids))
    result=[]
    for candidate in candidates.ranked:
        seed=candidate.view
        if seed.frame_uid not in views or views[seed.frame_uid]!=seed or seed.snapshot_id!=candidates.snapshot_id:
            raise IntegrityError('Candidate does not belong to the pinned pool')
        neighbors={uid:list(relations)for uid,relations in adjacency[seed.frame_uid].items()}
        for entity,uids in memberships[seed.frame_uid]:
            for uid in uids:
                if uid!=seed.frame_uid:neighbors.setdefault(uid,[]).append(('object_visibility',None,entity))
        def priority(uid):
            kinds={kind for kind,_,_ in neighbors[uid]}
            return (0 if 'temporal_next'in kinds else 1 if 'traversed'in kinds else 2,
                    abs(views[uid].capture_seq-seed.capture_seq),views[uid].capture_seq,uid)
        selected=[seed];missing=[];hashes={seed.image_hash}
        for side,predicate in [('before',lambda v:v.capture_seq<seed.capture_seq),('after',lambda v:v.capture_seq>seed.capture_seq)]:
            eligible=sorted((uid for uid in neighbors if predicate(views[uid])),key=priority)
            picked=next((views[uid]for uid in eligible if views[uid].image_hash not in hashes),None)
            if picked is None:missing.append('missing_'+side)
            else:selected.append(picked);hashes.add(picked.image_hash)
        selected.sort(key=lambda v:(v.capture_seq,v.frame_uid))
        relations=[row for v in selected if v.frame_uid!=seed.frame_uid for row in neighbors[v.frame_uid]]
        kinds=tuple(sorted({kind for kind,_,_ in relations}))
        executions=tuple(sorted({ref for kind,ref,_ in relations if kind=='traversed'}))
        entities=tuple(sorted({entity for kind,_,entity in relations if kind=='object_visibility'}))
        version=pose_map_version if all(v.pose_map_version==pose_map_version for v in selected)else None
        result.append(EvidenceBundle(seed.frame_uid,tuple(selected),executions,entities,kinds,
            (selected[0].capture_seq,selected[-1].capture_seq),version,None,candidate.score,
            tuple(missing),'one_hop_recorded'if len(selected)>1 else 'singleton'))
    return tuple(result)
