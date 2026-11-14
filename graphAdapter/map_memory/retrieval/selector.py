"""Pure bounded selection; host retains responsibility for original padding."""
from graphAdapter.map_memory.retrieval.protocol import native_slot_indices
from .contracts import Selection
from .bundles import singleton
from ..storage.archive import IntegrityError


def select_history(candidates,bundles,current,*,budget):
    if type(budget)is not int or budget<1:raise ValueError('Positive original model image budget required')
    if budget<=2:return Selection((),(),(),(),'budget_le_two',budget)
    if current.snapshot_id!=candidates.snapshot_id:raise IntegrityError('Current selection snapshot mismatch')
    by_uid={v.frame_uid:v for v in candidates.views}
    if len(by_uid)!=len(candidates.views):raise IntegrityError('Duplicate pool frame identity')
    legal={};rejected=list(candidates.rejected)
    for uid,view in by_uid.items():
        if view.episode_uid!=current.episode_uid or view.snapshot_id!=current.snapshot_id:
            raise IntegrityError('Cross-episode/snapshot selection input')
        if view.capture_seq>=current.capture_seq:
            rejected.append((uid,'future'if view.capture_seq>current.capture_seq else 'duplicate'));continue
        if not view.image_hash or not view.host_image_hash:
            rejected.append((uid,'unavailable'));continue
        legal[uid]=view
    selected={current.frame_uid:current};hashes={current.image_hash:current.frame_uid}
    protected=[]
    recent=min(3,max(1,(budget-1)//2))
    for view in sorted(legal.values(),key=lambda v:(v.capture_seq,v.frame_uid),reverse=True):
        if len(protected)>=recent:break
        if view.image_hash in hashes:
            rejected.append((view.frame_uid,'duplicate'));continue
        selected[view.frame_uid]=view;hashes[view.image_hash]=view.frame_uid;protected.append(view.frame_uid)
    if not candidates.ranked:return Selection((),(),tuple(protected),tuple(sorted(set(rejected))),'no_global_candidates',budget)
    pending=list(bundles);groups=[];relation_types=set();bins=set()
    low=min((v.capture_seq for v in legal.values()),default=0)
    high=max((v.capture_seq for v in legal.values()),default=low)
    def time_bin(view):return min(3,4*(view.capture_seq-low)//max(1,high-low+1))
    while pending and len(selected)<budget:
        options=[]
        for bundle in pending:
            if len(bundle.views)>3 or not any(v.frame_uid==bundle.seed_ref for v in bundle.views):
                raise IntegrityError('Malformed evidence bundle')
            if any(v.frame_uid not in legal or legal[v.frame_uid]!=v for v in bundle.views):
                rejected.append((bundle.seed_ref,'unavailable'));continue
            if bundle.seed_ref in selected:
                rejected.append((bundle.seed_ref,'redundant'));continue
            seed=legal[bundle.seed_ref]
            if seed.image_hash in hashes:
                rejected.append((bundle.seed_ref,'duplicate'));continue
            proposal=bundle
            duplicate=any(v.image_hash in hashes and hashes[v.image_hash]!=v.frame_uid for v in bundle.views)
            if duplicate or len({v.image_hash for v in bundle.views})!=len(bundle.views):
                rejected.append((bundle.seed_ref,'duplicate'))
                proposal=singleton(bundle,'singleton_duplicate_context')
            cost=sum(v.frame_uid not in selected for v in proposal.views)
            if cost>budget-len(selected):
                rejected.append((bundle.seed_ref,'out_of_budget'))
                proposal=singleton(bundle,'singleton_out_of_budget');cost=1
            new_types=set(proposal.edge_types)-relation_types
            # No graph bonus for flat/singleton evidence.
            new_bins={time_bin(v)for v in proposal.views}-bins if proposal.edge_types else set()
            marginal=(proposal.relevance+.1*len(new_types)+.1*len(new_bins))/(1+cost)
            options.append((-marginal,seed.capture_seq,seed.frame_uid,proposal,bundle))
        if not options:break
        _,_,_,chosen,original=min(options,key=lambda row:row[:3]);pending.remove(original)
        groups.append(chosen)
        for view in chosen.views:
            selected[view.frame_uid]=view;hashes[view.image_hash]=view.frame_uid
        relation_types.update(chosen.edge_types)
        if chosen.edge_types:bins.update(time_bin(v)for v in chosen.views)
    for bundle in pending:
        rejected.append((bundle.seed_ref,'redundant'if bundle.seed_ref in selected else 'out_of_budget'))
    if not groups:return Selection((),(),tuple(protected),tuple(sorted(set(rejected))),'no_global_candidates',budget)
    # Unused evidence slots retain native timeline context. Only a genuinely
    # short or duplicate-only history should need black padding. These observations
    # carry no graph facts and do not masquerade as grounded landmarks.
    if len(selected)<budget:
        timeline=sorted(legal.values(),key=lambda v:(v.capture_seq,v.frame_uid))+[current]
        native_indices = native_slot_indices(len(timeline), budget)[:-1]
        native = {timeline[i].frame_uid for i in native_indices if i is not None}
        while len(selected)<budget:
            remaining=[v for v in timeline if v.frame_uid not in selected and v.image_hash not in hashes]
            if not remaining:break
            def context_priority(v):
                distance=min(abs(v.capture_seq-s.capture_seq)for s in selected.values())
                return (v.frame_uid not in native,-distance,v.capture_seq,v.frame_uid)
            v=min(remaining,key=context_priority)
            selected[v.frame_uid]=v
            hashes[v.image_hash]=v.frame_uid
    slots=tuple(sorted(selected.values(),key=lambda v:(v.capture_seq,v.frame_uid)))
    if slots[-1]!=current or len(slots)>budget or len({v.image_hash for v in slots})!=len(slots):
        raise IntegrityError('Final history/current/unique-image budget invariant')
    return Selection(slots,tuple(groups),tuple(protected),tuple(sorted(set(rejected))),None,budget)


def select_grounded_single_slot(candidates, current, *, budget):
    """One visual landmark substitution in the original host timeline (diagnostic)."""
    import numpy as np
    from .contracts import EvidenceBundle
    fallback=lambda reason: Selection((),(),(),(),reason,budget)
    if budget<=2:return fallback('budget_le_two')
    timeline=sorted((*candidates.views,current),key=lambda view:(view.capture_seq,view.frame_uid))
    if timeline[-1]!=current or any(v.snapshot_id!=current.snapshot_id or v.episode_uid!=current.episode_uid for v in timeline):
        raise IntegrityError('Single-slot diagnostic requires one causal snapshot and current observation')
    if len(timeline)<budget:return fallback('short_native_history')
    # Preserve the original host sample when ordinal gaps preclude reproducing it.
    if [v.capture_seq for v in timeline]!=list(range(1,current.capture_seq+1)):
        return fallback('incomplete_native_timeline')
    native=[timeline[i] for i in native_slot_indices(len(timeline),budget)]
    if len({v.image_hash for v in native})!=budget:return fallback('duplicate_native_image')
    for candidate in candidates.ranked:
        if not candidate.matched_categories:continue
        seed=candidate.view
        if seed.image_hash==current.image_hash:continue
        # Retain chronological order, both timeline endpoints and the image count.
        allowed=[i for i in range(1,budget-1) if native[i-1].capture_seq<seed.capture_seq<native[i+1].capture_seq
                 and all(other.image_hash!=seed.image_hash for j,other in enumerate(native)if j!=i)]
        if seed.frame_uid==native[0].frame_uid:allowed=[0]
        if not allowed:continue
        slot=min(allowed,key=lambda i:(abs(native[i].capture_seq-seed.capture_seq),i))
        selected=list(native);selected[slot]=seed
        group=EvidenceBundle(seed.frame_uid,(seed,),(),(),(),(seed.capture_seq,seed.capture_seq),seed.pose_map_version,
            None,candidate.score,(),'single_grounded_landmark')
        return Selection(tuple(selected),(group,),(),(),None,budget)
    return fallback('no_instruction_grounded_seed')


def select_linked_view(candidates, current, index, *, budget, full_image_feature=None):
    """Recall an instruction-ranked view plus a real connection to a retained slot.

    Keep the first and current host frames. Replace at most one historical slot.
    The edge itself supplies context. No inferred category or ordinal is required.
    """
    import numpy as np
    from .contracts import EvidenceBundle
    def fallback(reason):
        return Selection((), (), (), (), reason, budget)
    if budget <= 2:
        return fallback('budget_le_two')
    timeline = sorted((*candidates.views, current), key=lambda v: (v.capture_seq, v.frame_uid))
    if any(v.episode_uid != current.episode_uid or v.snapshot_id != current.snapshot_id for v in timeline):
        raise IntegrityError('Linked view outside pinned episode or snapshot')
    if len(timeline) < budget or [v.capture_seq for v in timeline] != list(range(1, current.capture_seq + 1)):
        return fallback('short_or_incomplete_native_timeline')
    native = [timeline[i] for i in native_slot_indices(len(timeline),budget)]
    if len({v.image_hash for v in native}) != budget:
        return fallback('duplicate_native_image')
    by_uid = {v.frame_uid: v for v in candidates.views}
    native_ids = {v.frame_uid for v in native}
    native_images = {v.image_hash for v in native}
    links = {}
    for e in index['edges']:
        if e['type'] not in ('traversed','temporal_next'):
            continue
        pre, post = by_uid.get(e['src']), by_uid.get(e['dst'])
        if pre is None or post is None:
            continue
        if post.capture_seq != pre.capture_seq + 1:
            raise IntegrityError('Primitive history edge does not link consecutive captures')
        for seed, other in ((pre,post),(post,pre)):
            if other.frame_uid in native_ids:
                links.setdefault(seed.frame_uid, []).append((other, e))
    query_ranks = {uid: rank for rank,uid in enumerate(candidates.channels['Q'],1)}
    feature_vectors = {}
    def unit_vector(uid):
        if uid not in feature_vectors:
            raw = full_image_feature(uid)
            if raw is None:
                feature_vectors[uid] = None
            else:
                arr = np.asarray(raw,dtype=np.float64)
                norm = np.linalg.norm(arr)
                if arr.ndim!=1 or not np.isfinite(norm) or norm<=0:
                    raise IntegrityError('Invalid archived full-image feature for slot comparison')
                feature_vectors[uid] = arr / norm
        return feature_vectors[uid]
    def improves_slot(seed, slot):
        if full_image_feature is None:
            return True
        old = native[slot]
        if query_ranks[seed.frame_uid] >= query_ranks.get(old.frame_uid,float('inf')):
            return False
        retained = [unit_vector(v.frame_uid) for i,v in enumerate(native) if i!=slot]
        incoming, outgoing = unit_vector(seed.frame_uid), unit_vector(old.frame_uid)
        if incoming is None or outgoing is None or any(v is None for v in retained):
            return False
        return max(float(incoming @ v)for v in retained) <= max(float(outgoing @ v)for v in retained)
    # Inspect the bounded fused rankings. Q participation binds selection to the
    # full instruction and retained edges keep the visual pair interpretable.
    for candidate in candidates.ranked:
        seed = candidate.view
        if seed.frame_uid not in candidates.channels['Q'] or seed.image_hash in native_images:
            continue
        options = []
        for other, e in links.get(seed.frame_uid, ()):
            for slot in range(1, budget-1):
                if other.frame_uid == native[slot].frame_uid:
                    continue
                if native[slot-1].capture_seq < seed.capture_seq < native[slot+1].capture_seq:
                    if not improves_slot(seed,slot):
                        continue
                    options.append((e['type']!='traversed', abs(native[slot].capture_seq-seed.capture_seq),
                                    slot, other.capture_seq, e['id'], other, e))
        if not options:
            continue
        _, _, slot, _, _, other, e = min(options, key=lambda x:x[:5])
        selected = list(native);selected[slot]=seed
        pair = tuple(sorted((seed,other), key=lambda v:v.capture_seq))
        refs = (e['id'],) if e['type']=='traversed' else ()
        group = EvidenceBundle(seed.frame_uid,pair,refs,(),(e['type'],),
            (pair[0].capture_seq,pair[1].capture_seq),current.pose_map_version,None,
            candidate.score,(),'instruction_ranked_recorded_pair')
        return Selection(tuple(selected),(group,),(),(),None,budget)
    return fallback('no_new_instruction_ranked_linked_view')
