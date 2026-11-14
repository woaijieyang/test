"""Read existing instruction/visual/coverage selections as small, source-bound text groups.

The selector's protected and fill slots remain internal to the comparison.
Only group views and documented links can become supplementary host text.
"""
from ..storage.archive import IntegrityError
from .bundles import build_bundles
from .candidates import get_candidates
from .selector import select_history
from .semantic_topology import visible_detection_owners


def _group_refs(reader, group, index):
    seed = group.seed_ref
    endpoints = {v.frame_uid for v in group.views}
    edges = []
    for edge in index['edges']:
        src, dst = edge['src'], edge['dst']
        if seed not in (src, dst) or not {src, dst} <= endpoints:
            continue
        if (edge['type'] == 'temporal_next' and 'temporal_next' in group.edge_types
                or edge['type'] == 'traversed' and edge['id'] in group.execution_refs):
            edges.append({k:edge[k] for k in ('id','type','src','dst')})

    missing = set(group.missing_evidence)
    visibility = []
    if group.entity_refs:
        owners = {uid:visible_detection_owners(reader,uid) for uid in endpoints}
        for epoch, oid in group.entity_refs:
            if epoch != index['scene_epoch']:
                missing.add('unconfirmed_visibility')
                continue
            matches = []
            for ref in group.views:
                uid = ref.frame_uid
                ordinals = [d for d, owner in owners[uid].items() if owner == oid]
                if ordinals:
                    # One canonical source witness per view/owner is sufficient.
                    matches.append(dict(epoch=epoch,object_id=oid,uid=uid,member=f'{uid}:d{min(ordinals):05d}'))
            if len(matches) >= 2 and any(m['uid'] == seed for m in matches):
                visibility.extend(matches)
            else:
                # build_bundles can also propose ordinary or retired graph memberships.
                # Expose those as a missing visible identity, never as an observed link.
                missing.add('unconfirmed_visibility')
    return dict(seed_ref=seed,views=[dict(uid=v.frame_uid,step=v.env_step,capture_seq=v.capture_seq)
                                    for v in group.views],
                edges=edges,visibility=visibility,missing_evidence=sorted(missing),
                selection_reason=group.selection_reason)


def read_context_bundle(session,reader,query,current,current_reader,budget):
    """Use the worker-owned encoder/caches and already persisted image features."""
    if (reader.snapshot_id != query.snapshot_id or current.snapshot_id != query.snapshot_id
            or reader.identity['episode_uid'] != query.episode_uid
            or current_reader.identity['episode_uid'] != query.episode_uid or current.episode_uid != query.episode_uid
            or current_reader.snapshot_id != current.source_snapshot_id or current.frame_uid != query.current_frame_uid
            or current.capture_seq != query.current_capture_seq or current_reader.cutoff['capture_seq'] != current.capture_seq):
        raise IntegrityError('Evo context current observation or historical pin mismatch')
    encoded = session.encoder.encode(query)
    current_features = current_reader.get_view_features(query.current_frame_uid)
    if current_features['snapshot_id'] != current_reader.snapshot_id or current_features['frame_uid'] != current.frame_uid:
        raise IntegrityError('Evo context current features differ from the live observation')
    # get_candidates requires the ordinal even when the reader reports no detection record.
    if current_features['status'] != 'available' and 'capture_seq' not in current_features:
        current_features = dict(current_features,capture_seq=current.capture_seq)
    pool = get_candidates(reader,query,encoded,session.vocabulary,current_features=current_features,
                          instruction_scores=session.instruction_scores,reasoning_scores=session.reasoning_scores,metadata_only=True)
    index = reader.get_retrieval_index()
    bundles = build_bundles(pool,index,pose_map_version=reader.versions['pose_map_version'],expand=True)
    selected = select_history(pool,bundles,current,budget=budget)
    groups = [_group_refs(reader,g,index) for g in selected.groups]
    return dict(status='selected' if groups else 'empty',reason=selected.fallback_reason,
                episode_uid=query.episode_uid,snapshot_id=reader.snapshot_id,
                current_source_snapshot_id=current_reader.snapshot_id,current_frame_uid=current.frame_uid,
                query=dict(instruction_sha256=encoded.instruction_hash,reasoning_sha256=encoded.reasoning_hash,
                           model_identity_hash=encoded.model_identity_hash,tokenizer_identity_hash=encoded.tokenizer_identity_hash,
                           instruction_windows=len(encoded.windows),reasoning_windows=0 if encoded.reasoning is None else len(encoded.reasoning)),
                channels={k:list(uids) for k,uids in pool.channels.items()},
                counts=dict(historical_views=len(pool.views),ranked=len(pool.ranked),selected_groups=len(groups)),
                groups=groups)
