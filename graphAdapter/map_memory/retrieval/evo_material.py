"""Author coarse selection and material references at one immutable publication.

The VLN instruction/reason supplies optional lexical hints to a single coarse pass.
There is no GOAT target class, hint/selection VLM, frontier, experience, or pixel
decode here. Rows cite the first author prompt box and its unique camera member.
"""
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..storage.archive import IntegrityError
from .contracts import CategoryVocabulary, MemoryQuery
from .evidence import category_source_spans,match_category_cues


@lru_cache(maxsize=1)
def _limits():
    from evomemnav.policy import coarse
    import yaml

    config = Path(coarse.__file__).resolve().parents[2] / "cfg/evomemnav_goatbench.yaml"
    with config.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    return (int(data["coarse"]["anchor_budget"]), int(data["selection"]["max_crops_per_anchor"]),
            int(data["selection"]["max_crops_per_class"]))


def _ordered_keys(reader, anchors):
    try:
        keys = reader.pages.lookup(("graph", "scene_state", "anchor_keys"))
    except KeyError:
        if anchors:
            raise IntegrityError("Cannot recover source anchor enumeration")
        return []
    if len(keys) != len(set(keys)) or set(keys) != set(anchors):
        raise IntegrityError("Source anchor order and published anchor set differ")
    return keys


def topology_projection(reader):
    """Export stable JSON identifiers for an offline exact-set check; no blobs."""
    index = reader.get_retrieval_index()
    lookup = reader.pages.lookup
    entities = lookup(("graph", "entities"))
    vsm = lookup(("graph", "vsm"))
    views = lookup(("graph", "views"))
    return dict(
        views=sorted(views, key=lambda uid: (views[uid]["capture_seq"], uid)),
        anchors_in_order=_ordered_keys(reader, index["anchors"]),
        visited=[[v["id"], v["image_key"]] for v in vsm["visited"]],
        entities=[[e["epoch"], e["id"], e["status"]] for e in entities],
        members=[[e["epoch"], e["id"], member] for e in entities for member in e["members"]],
        aliases=[[a["epoch"], a["src"], a.get("dst_epoch"), a.get("dst"), a["status"]]
                 for a in lookup(("graph", "aliases"))],
        edges=[[e["id"], e["type"], e["src"], e["dst"]] for e in index["edges"]],
        visibility=[list(pair) for pair in index["visibility_edges"]],
        detections=[f"{uid}:d{i:05d}" for uid, v in views.items() if v.get("detection_record")
                    for i in range(v["detection_record"]["metadata"]["count"])],
        room_index=[[room, kind, ref] for room, groups in vsm["room_type_index"].items()
                    for kind, refs in groups.items() for ref in refs],
    )


def _author_box(xyxy, height, width):
    points = np.asarray(xyxy)
    if points.shape != (4,) or not np.isfinite(points).all():
        raise IntegrityError("Invalid source prompt box")
    x0, y0, x1, y1 = map(int, points)
    # Resolve Python slice endpoints exactly as Scene.object_crop, including negatives.
    x0, x1, _ = slice(max(0, x0), max(x0 + 1, x1)).indices(width)
    y0, y1, _ = slice(max(0, y0), max(y0 + 1, y1)).indices(height)
    return [x0, y0, x1, y1] if x1 > x0 and y1 > y0 else None


def _source_crop(uid, oid, epoch, obj, prompt, source, members, image_hw, labels):
    if prompt is None or oid not in prompt["obj_id"]:
        return None, "no_prompt_row"
    row = prompt["obj_id"].index(oid)
    if prompt["class_id"] is None:
        return None, "no_prompt_class"
    category = prompt["class_id"][row]
    box = prompt["xyxy"][row]
    matches = []
    for index in members:
        if not 0 <= index < len(source["class_ids"]):
            raise IntegrityError("Member outside camera detection array")
        if source["class_ids"][index] == category and np.array_equal(source["xyxy"][index], box):
            matches.append(index)
    if len(matches) != 1:
        return None, "ambiguous_camera_row" if matches else "no_camera_match"
    if not 0 <= category < len(labels):
        raise IntegrityError("Source class outside frozen vocabulary")
    bounds = _author_box(box, *image_hw)
    if bounds is None:
        return None, "empty_crop"
    index = matches[0]
    return dict(kind="crop", member=f"{uid}:d{index:05d}", index=index, label=labels[category],
                aggregate_label=obj["class_name"], object_id=oid, object_epoch=epoch,
                box_xyxy=bounds, prompt_row=row), None


def crop_query_match(label,instruction_terms,reason_terms):
    """Provenance for the upstream category priority, separate from visual confidence."""
    from evomemnav.policy.coarse import category_match
    return dict(instruction=[term for term in instruction_terms if category_match(label,[term])],
                reasoning=[term for term in reason_terms if category_match(label,[term])])


def _evidence(reader, node, objects, epoch, owners, labels, hints, limits, dropped):
    from evomemnav.policy.coarse import category_match

    uid = node.id
    if not node.objects:
        return []
    source = reader.get_view_class_ids(uid, include_boxes=True)
    if source["snapshot_id"] != reader.snapshot_id or source["frame_uid"] != uid:
        raise IntegrityError("Source detection revision differs from anchor")
    if source["status"] != "available":
        dropped["missing_camera_record"] += len(node.objects)
        return []
    prompt = reader.pages.lookup(("graph", "scene_state", "views", uid, "prompt"))
    image_hw = reader.pages.lookup(("graph", "views", uid, "detection_record", "metadata", "image_hw"))
    if len(image_hw) != 2 or min(image_hw) <= 0:
        raise IntegrityError("Invalid camera source grid")
    by_owner = defaultdict(list)
    for index, oid in owners.items():
        by_owner[oid].append(index)

    def priority(oid):
        obj = objects[oid]
        return (not category_match(obj["class_name"], hints), -float(obj["conf"]))

    result = []
    counts = Counter()
    _, per_anchor, per_class = limits
    for oid in sorted(node.objects, key=priority):
        label = objects[oid]["class_name"]
        if counts[label] >= per_class:
            continue
        crop, reason = _source_crop(uid, oid, epoch, objects[oid], prompt, source,
                                    by_owner[oid], image_hw, labels)
        if reason:
            dropped[reason] += 1
            continue
        result.append(crop)
        counts[label] += 1
        if len(result) == per_anchor:
            break
    return result


def read_evo_material(reader, query, vocabulary, *, max_views=None):
    """Return author-ordered history groups, full-pin room summary and small coverage."""
    from evomemnav.memory.vsmgraph import VSMGraph, ViewNode
    from evomemnav.policy.coarse import AnchorCandidate, select_candidates
    from .semantic_topology import visible_detection_owners

    if not isinstance(query, MemoryQuery) or not isinstance(vocabulary, CategoryVocabulary):
        raise TypeError("Require MemoryQuery and source-bound CategoryVocabulary")
    if (query.snapshot_id != reader.snapshot_id or query.episode_uid != reader.identity["episode_uid"]
            or query.cutoff_capture_seq != reader.cutoff["capture_seq"]
            or query.cutoff_event_seq != reader.cutoff["event_seq"]):
        raise IntegrityError("Query differs from immutable reader/cutoff")
    limits = _limits()
    if max_views is not None and (type(max_views) is not int or max_views < 0):
        raise ValueError("max_views must be a nonnegative integer")
    budget = limits[0] if max_views is None else min(max_views, limits[0])
    index = reader.get_retrieval_index()
    anchors = index["anchors"]
    order = _ordered_keys(reader, anchors)
    model = index["model_identity"]
    if (order or model) and model.get("vocabulary_sha256") != vocabulary.source_sha256:
        raise IntegrityError("Vocabulary differs from pinned source")
    objects = {}
    if order:
        for obj in reader.pages.lookup(("graph", "scene_state", "objects")):
            if obj["id"] in objects:
                raise IntegrityError("Multiple scene objects share an identity")
            objects[obj["id"]] = obj

    graph = VSMGraph()
    epoch = index["scene_epoch"]
    graph.objects = {oid: dict(category=o["class_name"], anchor=o.get("image")) for oid, o in objects.items()}
    candidates = []
    steps = {}
    for recency, uid in enumerate(order):
        value = anchors[uid]
        room = value.get("room_type_hint") or "unknown"
        node = ViewNode(id=uid, kind="anchor", position=None, image_key=uid,
                        room=room, objects=list(value["objects"]))
        if not set(node.objects) <= objects.keys() or len(set(node.objects)) != len(node.objects):
            raise IntegrityError("Invalid anchor visibility references")
        graph.anchors[uid] = node
        view = reader.pages.lookup(("graph", "views", uid))
        seq = view["capture_seq"]
        if seq > query.cutoff_capture_seq or view["source_event_seq"] > query.cutoff_event_seq:
            raise IntegrityError("Future anchor in pinned source")
        if (uid == query.current_frame_uid) != (seq == query.current_capture_seq):
            raise IntegrityError("Current observation UID and ordinal disagree")
        if uid != query.current_frame_uid:
            steps[uid] = view["env_step"]
            candidates.append(AnchorCandidate(uid, room, [objects[o]["class_name"] for o in node.objects], recency))

    def separate_cues(labels):
        return (match_category_cues(query.instruction,labels),
                match_category_cues(query.last_reasoning,labels) if query.last_reasoning else ())

    sources=dict(instruction=category_source_spans(query.instruction,vocabulary.labels),
                 reasoning=category_source_spans(query.last_reasoning,vocabulary.labels) if query.last_reasoning else {})
    instruction_terms,reason_terms=tuple(sources['instruction']),tuple(sources['reasoning'])
    categories=tuple(dict.fromkeys((*instruction_terms,*reason_terms)))
    room_labels=tuple(dict.fromkeys(n.room for n in graph.anchors.values() if n.room != "unknown"))
    room_instruction,room_reason=separate_cues(room_labels)
    rooms=tuple(dict.fromkeys((*room_instruction,*room_reason)))
    choices = select_candidates(candidates, [], target="", room_hints=rooms, category_hints=categories,
                                k_a=budget, k_f=0, w_gain=0., w_distance=0.)
    result = []
    dropped = Counter()
    for candidate in choices.anchors[:budget]:
        uid = candidate.view_id
        node = graph.anchors[uid]
        owners = visible_detection_owners(reader, uid)
        evidence = _evidence(reader, node, objects, epoch, owners, vocabulary.labels, categories, limits, dropped)
        for crop in evidence:
            crop['query_match']=crop_query_match(crop['aggregate_label'],instruction_terms,reason_terms)
        result.append(dict(uid=uid, step=steps[uid], room=node.room, evidence=evidence))
    return dict(snapshot_id=reader.snapshot_id, episode_uid=query.episode_uid,
                summary=graph.summary(rooms, categories), anchors=result,query_sources=sources,
                coverage=dict(views=len(index["view_uids"]), anchors=len(order), eligible_anchors=len(candidates),
                              entities=len(index["entities"]), edges=len(index["edges"]),
                              visibility=len(index["visibility_edges"]), selected_anchors=len(result),
                              dropped_crop_reasons=dict(dropped)))
