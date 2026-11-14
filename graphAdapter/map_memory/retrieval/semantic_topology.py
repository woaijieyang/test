"""Read the geometry coverage, objects, view anchors and their typed edges at one publication."""
from ..storage.store import IntegrityError
from ..visualization import slice_points
from .host_input_compiler import plain

def visible_detection_owners(reader,uid):
    """Map source-frame detection ordinals to unique active owners on a pinned anchor edge."""
    from types import MappingProxyType
    if not hasattr(reader,'_visible_detection_owners'):
        graph=reader._graph
        epoch=graph.get('scene_state',{}).get('epoch')
        vsm=graph.get('vsm',{})
        anchors=vsm.get('anchors',{})
        edges={tuple(edge) for edge in vsm.get('visibility_edges',())}
        expected={(frame,oid) for frame,node in anchors.items() for oid in node['objects']}
        if edges!=expected:
            raise IntegrityError('Pinned anchor visibility and object list disagree')
        owners={}
        active_ids=set()
        claimed=set()
        for entity in graph.get('entities',()):
            if entity['status']!='active' or entity['epoch']!=epoch:continue
            oid=entity['id']
            if oid in active_ids:raise IntegrityError('Duplicate active object identity')
            active_ids.add(oid)
            for ref in entity['members']:
                frame,separator,suffix=ref.rpartition(':d')
                if frame not in anchors:continue
                if not separator or not suffix.isascii() or not suffix.isdecimal():
                    raise IntegrityError('Invalid detection identity on anchor')
                i=int(suffix)
                if ref!=f'{frame}:d{i:05d}' or (frame,i) in claimed:
                    raise IntegrityError('Noncanonical or multiply owned anchor detection')
                claimed.add((frame,i))
                if (frame,oid) in edges:owners.setdefault(frame,{})[i]=oid
        if any(oid not in active_ids for _,oid in edges):
            raise IntegrityError('Anchor edge refers to missing active object')
        reader._visible_detection_owners={frame:MappingProxyType(items) for frame,items in owners.items()}
    return reader._visible_detection_owners.get(uid,{})


def competing_anchor_member(reader, selected, ranked, vocabulary, current_seq):
    """Check visible active members before the decision, including native views and unranked detections."""
    if not 0 < reader.cutoff['capture_seq'] <= current_seq:
        raise IntegrityError("Ambiguity search requires a historical publication")
    label = selected['label']
    owner = selected['object_id']
    for row in ranked:
        if row['label'] == label and row['object_id'] != owner:
            return dict(status='competing', source=row, origin='ranked')
    target = vocabulary.labels.index(label)
    graph = reader._graph
    unknown = False
    # The chosen instance may own many views. Only open class records for frames
    # that have a visible member belonging to another active object.
    for uid in graph['vsm']['anchors']:
        seq = graph['views'][uid]['capture_seq']
        if seq > reader.cutoff['capture_seq']:
            raise IntegrityError("Future anchor in ambiguity search")
        if seq == current_seq:
            continue
        others = [(ordinal, oid) for ordinal, oid in visible_detection_owners(reader, uid).items() if oid != owner]
        if not others:
            continue
        record = reader.get_view_class_ids(uid)
        if record['frame_uid'] != uid or record['snapshot_id'] != reader.snapshot_id:
            raise IntegrityError("Ambiguity source differs from the pinned anchor")
        if record['status'] != 'available':
            unknown = True
            continue
        if record['capture_seq'] != seq or record['model_identity']['vocabulary_sha256'] != vocabulary.source_sha256:
            raise IntegrityError("Ambiguity source frame or vocabulary mismatch")
        classes = record['class_ids']
        for ordinal, oid in others:
            if not 0 <= ordinal < len(classes) or not 0 <= int(classes[ordinal]) < len(vocabulary.labels):
                raise IntegrityError("Invalid ambiguity source detection")
            if int(classes[ordinal]) == target:
                return dict(status='competing', origin='historical_anchor',
                            source=dict(frame_uid=uid, step=seq-1, label=label, object_id=oid, member=f'{uid}:d{ordinal:05d}'))
    return dict(status='incomplete' if unknown else 'no_competitor', origin='historical_anchors')


def native_object_slot(reader,history,owner,label,vocabulary):
    """Locate an independently recorded detection of the selected graph object in a native RGB slot."""
    if history.snapshot_id!=reader.snapshot_id:raise IntegrityError('Native object lookup crossed revision')
    slots={s.frame_uid:(s.index,s.sensor_seq,s.env_step) for s in history.slots if s.frame_uid
           and s.source_snapshot_id==reader.snapshot_id and s.sensor_seq<=reader.cutoff['capture_seq']
           and s.raw_pixel_hash and s.raw_pixel_hash==s.host_pixel_hash}
    return _match_native_object(reader,slots,owner,label,vocabulary,
                                lambda uid,index:history.images[index-1].size)


def preflight_native_object(reader,native_views,native_ids,host_images,owner,label,vocabulary):
    """Decode only a prospective matching native frame and verify its actual host pixels."""
    import numpy as np
    by_uid={v.frame_uid:v for v in native_views}
    slots={uid:(index,by_uid[uid].capture_seq,by_uid[uid].env_step) for index,uid in enumerate(native_ids,1)
           if uid is not None and by_uid[uid].source_snapshot_id==reader.snapshot_id
           and by_uid[uid].capture_seq<=reader.cutoff['capture_seq']}
    def verified_size(uid,index):
        ref=by_uid[uid]
        source=reader.get_view(uid,include_images=True,include_depth=False)
        cap=source['capture']
        if (source['snapshot_id']!=reader.snapshot_id or cap['episode_uid']!=ref.episode_uid
                or cap['frame_uid']!=uid or source['frame_uid']!=uid or source['capture_seq']!=ref.capture_seq
                or cap['event_seq']!=ref.event_seq or cap['env_step']!=ref.env_step
                or source['raw_rgb_ref']['sha256']!=ref.image_hash or source['host_view_ref']['sha256']!=ref.host_image_hash):
            raise IntegrityError('Native preflight archive identity differs')
        pixels=np.asarray(host_images[ref.capture_seq-1])
        if not np.array_equal(pixels,source['host_view']):
            raise IntegrityError('Native preflight pixels differ from the host observation')
        if not np.array_equal(pixels,source['raw_rgb']):
            return None
        return pixels.shape[1],pixels.shape[0]
    return _match_native_object(reader,slots,owner,label,vocabulary,verified_size)


def _match_native_object(reader,slots,owner,label,vocabulary,image_size):
    from ..storage.store import clip_detection_box
    entity=reader.get_object(owner['epoch'],owner['object_id'],revision=reader.snapshot_id)
    if (entity['epoch']!=owner['epoch'] or entity['id']!=owner['object_id'] or entity['status']!='active'
            or owner['member'] not in entity['members']):
        raise IntegrityError('Native object lookup has no matching active source')
    by_slot={}
    for member in entity['members']:
        uid,sep,suffix=member.rpartition(':d')
        if uid not in slots:continue
        if not sep or not suffix.isascii() or not suffix.isdecimal() or member!=f'{uid}:d{int(suffix):05d}':
            raise IntegrityError('Malformed native detection member')
        by_slot.setdefault(slots[uid][0],[]).append((int(suffix),member,uid))
    for slot_index in sorted(by_slot,reverse=True):
        candidates=sorted(by_slot[slot_index])
        uid=candidates[0][2];slot=slots[uid]
        record=reader.get_view_class_ids(uid,include_boxes=True)
        if record['status']!='available':continue
        if (record['frame_uid']!=uid or record['snapshot_id']!=reader.snapshot_id
                or record['capture_seq']!=slot[1] or record['model_identity']['vocabulary_sha256']!=vocabulary.source_sha256):
            raise IntegrityError('Native slot and camera evidence differ')
        for i,member,_ in candidates:
            if i>=len(record['class_ids']):raise IntegrityError('Native object member outside source detections')
            class_id=int(record['class_ids'][i])
            if not 0<=class_id<len(vocabulary.labels):raise IntegrityError('Unknown native object class')
            if vocabulary.labels[class_id]!=label:continue
            size=image_size(uid,slot_index)
            if size is None:break
            w,h=size
            box=clip_detection_box(record['xyxy'][i],(h,w))
            if box is not None:
                return dict(slot=slot_index,step=slot[2],member=member,box_xyxy=box)
    return None


def _anchor_detection_labels(reader, anchors, objects):
    """Resolve anchor labels from the pinned camera record once per source frame."""
    from pathlib import Path
    from .contracts import CategoryVocabulary
    out={}
    vocabulary=None
    for anchor in anchors:
        uid=anchor["uid"]
        out[uid]={}
        refs={m for oid in anchor["objects"] for m in objects[oid]["sources"] if m.rpartition(":d")[0]==uid}
        if not refs:continue
        record=reader.get_view_class_ids(uid)
        if record["status"]!="available":continue
        if record["snapshot_id"]!=reader.snapshot_id or record["frame_uid"]!=uid:
            raise IntegrityError("Anchor class record differs from pinned view")
        if vocabulary is None:
            vocab_file=Path(__file__).resolve().parents[4]/"vendor_sources/EvoMemNav/data/scannet200_classes.txt"
            vocabulary=CategoryVocabulary.from_file(vocab_file)
        if record["model_identity"]["vocabulary_sha256"]!=vocabulary.source_sha256:
            raise IntegrityError("Anchor detector vocabulary differs from camera record")
        classes=record["class_ids"]
        for ref in sorted(refs):
            suffix=ref.rpartition(":d")[2]
            if not suffix.isascii() or not suffix.isdecimal() or int(suffix)>=len(classes):
                raise IntegrityError("Invalid anchor source index")
            label=int(classes[int(suffix)])
            if not 0<=label<len(vocabulary.labels):raise IntegrityError("Unknown anchor source class")
            out[uid][ref]=vocabulary.labels[label]
    return out


def read_semantic_topology(reader, *, episode_uid, snapshot_id, decision_capture_seq, height="auto"):
    """A historical evidence product. The caller supplies an already pinned reader."""
    topology=_topology_index(reader,episode_uid,snapshot_id,decision_capture_seq)
    points,states,slice_info=slice_points(reader,height)
    topology.update(geometry_slice=slice_info,points=points[:,[0,2]].tolist(),states=states.tolist())
    return topology


def _topology_index(reader,episode_uid,snapshot_id,decision_capture_seq):
    cap = reader.cutoff["capture_seq"]
    if type(decision_capture_seq) is not int or decision_capture_seq < 1:
        raise IntegrityError("Invalid decision capture sequence")
    if reader.identity["episode_uid"] != episode_uid or reader.snapshot_id != snapshot_id or cap > decision_capture_seq:
        raise IntegrityError("Semantic topology requires a causal pin in the decision episode")
    graph = reader._graph
    views = {uid: dict(seq=v["capture_seq"], base=v.get("T_G_base"), room=v.get("room_type_hint"))
             for uid, v in graph["views"].items()}
    if any(v["seq"] > cap for v in views.values()):
        raise IntegrityError("View exceeds semantic topology cutoff")
    entities = {e["id"]: e for e in graph["entities"] if e["status"] == "active"}
    objects = []
    for o in graph["scene_state"]["objects"]:
        members = entities[o["id"]]["members"]
        if any(m.rpartition(":d")[0] not in views for m in members):
            raise IntegrityError("Object evidence refers outside the pinned views")
        objects.append(dict(id=o["id"], label=o["class_name"], bbox=o["bbox"],
                            count=o["num_detections"], sources=members))
    vsm = graph["vsm"]
    anchors = [dict(uid=uid, objects=n["objects"], room=n.get("room_type_hint"), position=n["position"])
               for uid,n in vsm["anchors"].items()]
    visibility = vsm["visibility_edges"]
    objects_by_id = {o["id"]: o for o in objects}
    expected={(a["uid"], oid) for a in anchors for oid in a["objects"]}
    if any(a["uid"] not in views for a in anchors) or expected != set(map(tuple,visibility)):
        raise IntegrityError("Unbound or inconsistent anchor visibility")
    if any(oid not in objects_by_id for _,oid in visibility):
        raise IntegrityError("Visibility references an inactive object")
    edges=[dict(src=e["src"],dst=e["dst"]) for e in graph["edges"] if e["type"]=="traversed"]
    if any(e[k] not in views for e in edges for k in ("src","dst")):
        raise IntegrityError("Unbound recorded path edge")
    return plain(dict(episode_uid=episode_uid,snapshot_id=snapshot_id,pose_map_version=reader.versions["pose_map_version"],
        cutoff=dict(reader.cutoff),
        views=views,objects=objects,anchors=anchors,visibility=visibility,traversed=edges,
        anchor_detection_labels=_anchor_detection_labels(reader,anchors,objects_by_id)))


def coverage_at_view(topology, uid, *, radius_cells=10):
    """Evidence in a bounded horizontal window about one published base pose."""
    import numpy as np
    if type(radius_cells) is not int or not 0 <= radius_cells <= 128:
        raise ValueError("Require a bounded nonnegative radius in cells")
    step = float(topology["geometry_slice"]["voxel_size_m"])
    if not np.isfinite(step) or step <= 0:
        raise IntegrityError("Invalid geometry grid spacing")
    base = topology["views"][uid]["base"]
    if base is None:
        return None
    center = np.asarray(base,dtype=float)[[0,2],3]
    points = np.asarray(topology["points"],dtype=float).reshape(-1,2)
    states = np.asarray(topology["states"])
    if (len(states)!=len(points) or not np.isfinite(points).all() or not np.isfinite(center).all()
            or not np.isin(states,(1,2,3)).all()):
        raise IntegrityError("Invalid geometry evidence")
    # World-aligned bins: combine coincident free + surface evidence as conflict.
    indices = np.floor(points / step + 0.5).astype(np.int64)
    origin = np.floor(center / step + 0.5).astype(np.int64) - radius_cells
    local = indices - origin
    width = 2*radius_cells + 1
    keep = ((local >= 0) & (local < width)).all(axis=1)
    grid = np.zeros((width,width),dtype=np.uint8)
    np.bitwise_or.at(grid,(local[keep,0],local[keep,1]),states[keep].astype(np.uint8))
    counts = np.bincount(grid.ravel(),minlength=4).tolist()
    return dict(window_width_cells=width, cell_size_m=step,
                sampled_height_m=topology["geometry_slice"]["sampled_height_m"],
                unknown=counts[0],free=counts[1],surface=counts[2],conflict=counts[3])


class TopologyMenu:
    """Decision-local view choices. The model sees short option IDs, never storage names."""

    @classmethod
    def from_reader(cls,reader,*,episode_uid,snapshot_id,decision_capture_seq,decision_id,order=None,labels=None):
        """Read the decision index; geometry tiles are needed only for explicit coverage requests."""
        topology=_topology_index(reader,episode_uid,snapshot_id,decision_capture_seq)
        return cls(topology,episode_uid=episode_uid,snapshot_id=snapshot_id,
                   decision_capture_seq=decision_capture_seq,decision_id=decision_id,order=order,labels=labels)

    def __init__(self, topology, *, episode_uid, snapshot_id, decision_capture_seq, decision_id, order=None, labels=None):
        import string
        if (topology["episode_uid"] != episode_uid or topology["snapshot_id"] != snapshot_id
                or type(decision_capture_seq) is not int or topology["cutoff"]["capture_seq"] > decision_capture_seq):
            raise IntegrityError("Topology menu scope differs from the decision")
        objects = {o["id"]: o for o in topology["objects"]}
        camera_labels=topology.get("anchor_detection_labels")
        visibility = set(map(tuple, topology["visibility"]))
        views = topology["views"]
        by_view = {}
        self._choices = {}
        self._source_owners = {}
        for anchor in topology["anchors"]:
            uid = anchor["uid"]
            seq = views[uid]["seq"]
            if seq > topology["cutoff"]["capture_seq"] or seq < 1:
                raise IntegrityError("Anchor outside publication")
            if seq == decision_capture_seq:
                continue
            visible = []
            sources = []
            for oid in sorted(anchor["objects"]):
                if (uid, oid) not in visibility:
                    raise IntegrityError("Missing anchor-object edge")
                obj = objects[oid]
                direct = [m for m in obj["sources"] if m.rpartition(":d")[0] == uid]
                if not direct:
                    continue
                for ref in direct:
                    if ref in self._source_owners:
                        raise IntegrityError("Source detection appears more than once on the topology menu")
                    self._source_owners[ref] = oid
                if camera_labels is None:
                    # Legacy topology summaries have no detector class bytes. State the available scope.
                    visible.append(obj["label"])
                    sources.extend(direct)
                else:
                    observed=camera_labels[uid]
                    for ref in direct:
                        if ref in observed:
                            visible.append(observed[ref])
                            sources.append(ref)
            if visible:
                by_view[uid] = (dict(view_step=seq-1, room_hint=anchor["room"] or "unknown",
                                     objects=sorted(set(visible)),
                                     label_scope="anchor_detections" if camera_labels is not None else "aggregate_only"), tuple(sources))
        ordered = sorted(by_view, key=lambda uid: views[uid]["seq"]) if order is None else list(order)
        if len(ordered) != len(by_view) or set(ordered) != set(by_view):
            raise IntegrityError("Menu order differs from eligible evidence")
        # Short default labels; larger graphs retain every eligible node.
        option_ids = ([string.ascii_uppercase[i] if i < 26 else f"V{i+1}" for i in range(len(ordered))]
                      if labels is None else list(labels))
        if (len(option_ids) != len(ordered) or len(set(option_ids)) != len(ordered)
                or any(not isinstance(k,str) or not k.isascii() or not k.isalnum() or not k.isupper() or k=="NONE" for k in option_ids)):
            raise ValueError("Use distinct uppercase menu choices")
        self.episode_uid, self.snapshot_id = episode_uid, snapshot_id
        if type(decision_id) is not int or decision_id < 1:
            raise ValueError("Explicit decision identity required")
        self._clock = (decision_capture_seq, decision_id)
        display = []
        self._verified_labels = {}
        for label, uid in zip(option_ids, ordered):
            fields, sources = by_view[uid]
            display.append(dict(option=label, **fields))
            if camera_labels is not None:
                self._verified_labels[label]={ref:camera_labels[uid][ref] for ref in sources}
            self._choices[label] = (uid, sources)

        self._display=tuple(display)

    @property
    def entries(self):
        # Callers can serialize or annotate their own copy without changing resolution.
        return [dict(entry,objects=list(entry["objects"])) for entry in self._display]

    def materialize(self, reply, reader, *, episode_uid, snapshot_id, decision_capture_seq, decision_id):
        """Resolve one offered option to verified original pixels and source-grid boxes."""
        from pathlib import Path
        from .contracts import CategoryVocabulary
        from ..storage.store import clip_detection_box
        selected=self.resolve(reply,episode_uid=episode_uid,snapshot_id=snapshot_id,
                              decision_capture_seq=decision_capture_seq,decision_id=decision_id)
        if selected is None:return None
        if reader.identity["episode_uid"]!=episode_uid or reader.snapshot_id!=snapshot_id:
            raise IntegrityError("Photo reader differs from menu scope")
        uid,refs=selected
        source=reader.get_view_class_ids(uid,include_boxes=True)
        if source["status"]!="available" or source["capture_seq"]>=decision_capture_seq:
            raise IntegrityError("Selected photo lacks a historical detector record")
        if source["snapshot_id"]!=snapshot_id or source["frame_uid"]!=uid:
            raise IntegrityError("Selected detection record differs from menu source")
        view=reader.get_view(uid,include_images=True,include_depth=False)
        if (view["snapshot_id"]!=snapshot_id or view["frame_uid"]!=uid or view["capture_seq"]!=source["capture_seq"]
                or view["raw_rgb"] is None or view["raw_rgb_ref"] is None):
            raise IntegrityError("Selected camera evidence differs from menu source")
        vocabulary=CategoryVocabulary.from_file(Path(__file__).resolve().parents[4]/"vendor_sources/EvoMemNav/data/scannet200_classes.txt")
        if vocabulary.source_sha256!=source["model_identity"]["vocabulary_sha256"]:
            raise IntegrityError("Vocabulary differs from selected frame")
        boxes=source["xyxy"]
        classes=source["class_ids"]
        if boxes.shape!=(len(classes),4):
            raise IntegrityError("Selected box and class arrays disagree")
        cached=self._verified_labels.get(reply.strip())
        owners=visible_detection_owners(reader,uid)
        epoch=reader._graph["scene_state"]["epoch"]
        detections=[]
        for ref in refs:
            frame,sep,ordinal=ref.rpartition(":d")
            if frame!=uid or not sep or not ordinal.isascii() or not ordinal.isdecimal() or int(ordinal)>=len(classes):
                raise IntegrityError("Detection outside selected frame")
            i=int(ordinal);category=int(classes[i])
            if not 0<=category<len(vocabulary.labels):
                raise IntegrityError("Unknown detection category in selected frame")
            label=vocabulary.labels[category]
            if cached is not None and cached[ref]!=label:
                raise IntegrityError("Displayed label differs from selected frame")
            owner=self._source_owners[ref]
            if owners.get(i)!=owner:
                raise IntegrityError("Materialized detection belongs to a different graph object")
            detections.append(dict(member=ref,source_label=label,object_epoch=epoch,object_id=owner,
                                   box_xyxy=clip_detection_box(boxes[i],view["raw_rgb"].shape)))
        return dict(frame_uid=uid,snapshot_id=snapshot_id,env_step=view["capture"]["env_step"],raw_rgb=view["raw_rgb"],
                    raw_rgb_ref=view["raw_rgb_ref"],detections=tuple(detections))

    def resolve(self, reply, *, episode_uid, snapshot_id, decision_capture_seq, decision_id):
        if (episode_uid,snapshot_id,(decision_capture_seq,decision_id))!=(self.episode_uid,self.snapshot_id,self._clock):
            raise IntegrityError("Menu reply belongs to a different decision scope")
        key = reply.strip() if isinstance(reply,str) else ""
        if key == "NONE":
            return None
        if key not in self._choices:
            raise ValueError("Model did not return an offered option or NONE")
        return self._choices[key]

    def suggested_view(self, instruction, reasoning):
        """Rank source-bound views only when the native reasoning shares a map cue with the instruction."""
        import re
        from evomemnav.policy.coarse import AnchorCandidate, rank_anchors
        from .evidence import landmark_query_cues, match_category_cues
        if not instruction or not reasoning:
            return None
        entries = self.entries
        labels = sorted({label for entry in entries for label in entry["objects"]})
        hints = sorted({entry["room_hint"] for entry in entries} - {"unknown", None})
        vocabulary = sorted(set(labels + hints))
        # Full native outputs include a scene description and completed actions. Only
        # the explicit next plan can request evidence. Bare cues remain usable by readers.
        if "<BEGIN_OF_REASONING>" in reasoning or re.search(r"\bnext (?:step|plan) is to\b", reasoning, re.I):
            cues = set(landmark_query_cues(instruction, reasoning, vocabulary))
        else:
            cues = set(match_category_cues(reasoning, match_category_cues(instruction, vocabulary)))
        categories = sorted(cues.intersection(labels))
        rooms = sorted(cues.intersection(hints))
        rows = [AnchorCandidate(entry["option"], entry["room_hint"], entry["objects"], entry["view_step"])
                for entry in entries
                if entry["room_hint"] in rooms or cues.intersection(entry["objects"])]
        if not rows:
            return None
        ranked = rank_anchors(rows, target="", room_hints=rooms, category_hints=categories)
        return ranked[0].view_id if ranked else None

    
from functools import lru_cache


@lru_cache(maxsize=1)
def _exit_room_patterns():
    import re
    from pathlib import Path
    import yaml
    cfg=Path(__file__).resolve().parents[4]/"vendor_sources/EvoMemNav/cfg/evomemnav_goatbench.yaml"
    labels=yaml.safe_load(cfg.read_text())["vsmgraph"]["room_vocab"]
    if not isinstance(labels,list) or not all(isinstance(label,str) and label for label in labels):
        raise IntegrityError("Invalid room vocabulary for historical approach")
    names="|".join(re.escape(label) for label in sorted(set(labels)-{"unknown"},key=len,reverse=True))
    verb=r"(?:exit|leave|(?:go|head|walk|step) (?:back )?out of)"
    return re.compile(r"\b"+verb+r" (?:this |the |a )?("+names+r")\b",re.I)


def requested_exit_room(instruction, reasoning):
    """Read an explicit exit intent in the native upcoming plan. Ambiguity yields no request."""
    import re
    if not instruction or not reasoning:
        return None
    plan = re.split(r"\b(?:the |my )?next (?:plan|step) is to\s+",reasoning,flags=re.I)
    if len(plan)!=2:
        return None
    pattern = _exit_room_patterns()
    match = pattern.match(plan[1])
    if match is None:
        return None
    room = match.group(1).casefold()
    # A negated exit clause does not license an affirmative history read.
    for cue in pattern.finditer(instruction):
        if cue.group(1).casefold()!=room:
            continue
        prefix=instruction[:cue.start()].rstrip()
        if not re.search(r"\b(?:not|never|don't|don’t)(?:\s+to)?$",prefix,re.I):
            return room
    return None


def historical_approach(reader, current_seq, room):
    """Retrieve the observed approach to a run of room-hinted anchors within one pinned graph."""
    g=reader._graph
    views=g["views"]
    anchors=g["vsm"]["anchors"]
    ordered=sorted((uid for uid in anchors if views[uid]["capture_seq"] < current_seq),
                   key=lambda uid:views[uid]["capture_seq"])
    def hint(uid):return anchors[uid].get("room_type_hint")
    if not ordered or hint(ordered[-1])!=room:
        return None
    first=len(ordered)-1
    while first>0 and hint(ordered[first-1])==room:
        first-=1
    if first==0:return None
    before,inside=ordered[first-1:first+1]
    early,late=(views[uid]["capture_seq"] for uid in (before,inside))
    if not 0<early<late<=reader.cutoff["capture_seq"]:
        raise IntegrityError("Approach anchors crossed the publication cutoff")
    trace=reader.get_trace(early+1,late)
    if len(trace)!=late-early:return None
    prev=before
    moved=[]
    unverified_forward_steps=[]
    for sequence,row in enumerate(trace,early+1):
        if row["pre"]!=prev or row["post"] not in views or views[row["post"]]["capture_seq"]!=sequence:
            raise IntegrityError("Historical approach contains a discontinuity")
        edge=row["motion"].get("traversed")
        if edge is not None:
            if ((edge["src"],edge["dst"])!=(row["pre"],row["post"]) or
                    row["action"]["action_id"]!=1 or row["action"]["collision"] is not False):
                raise IntegrityError("Invalid approach traversal")
            moved.append(edge["id"])
        elif row["action"]["action_id"]==1:
            unverified_forward_steps.append(sequence-1)
        prev=row["post"]
    if prev!=inside or not moved:return None
    return dict(before=before,inside=inside,before_step=early-1,inside_step=late-1,
                room_hint=room,traversed_edges=moved,unverified_forward_steps=unverified_forward_steps)


def _depth_grid(view):
    import numpy as np
    from poseAdapter.coordinate.transforms import checked_transform
    depth=np.asarray(view["depth"]); valid=np.asarray(view["valid"])
    K=np.asarray(view["K"],dtype=float)
    if (depth.ndim!=2 or valid.shape!=depth.shape or valid.dtype!=np.bool_ or K.shape!=(3,3)
            or not np.isfinite(K).all() or min(K[0,0],K[1,1])<=0
            or not np.allclose(K[2],[0,0,1]) or K[0,1]!=0 or K[1,0]!=0):
        raise IntegrityError("Invalid rectified RGB-D grid or intrinsics")
    return depth,valid,K,checked_transform(view["pose"])


def _source_points(source,stride):
    import numpy as np
    depth,valid,K,pose=_depth_grid(source)
    yy,xx=np.nonzero((valid & np.isfinite(depth) & (depth>0))[::stride,::stride])
    yy*=stride;xx*=stride
    z=depth[yy,xx].astype(float)
    return np.column_stack(((xx-K[0,2])*z/K[0,0],(yy-K[1,2])*z/K[1,1],z)),pose


def _depth_support(xyz,source_pose,target,tolerance,*,return_pixels=False):
    """Return original source indices, so overlap across target cameras is counted once."""
    import numpy as np
    depth,valid,K,pose=_depth_grid(target)
    transform=np.linalg.solve(pose,source_pose)
    coords=xyz@transform[:3,:3].T+transform[:3,3]
    indices=np.flatnonzero(coords[:,2]>1e-5)
    visible=coords[indices]
    u=K[0,0]*visible[:,0]/visible[:,2]+K[0,2]
    v=K[1,1]*visible[:,1]/visible[:,2]+K[1,2]
    h,w=depth.shape
    keep=(u>=-.5)&(u<w-.5)&(v>=-.5)&(v<h-.5)
    cols=np.floor(u[keep]+.5).astype(int);rows=np.floor(v[keep]+.5).astype(int)
    indices=indices[keep]
    observed=depth[rows,cols]
    comparable=valid[rows,cols] & np.isfinite(observed) & (observed>0)
    agree=comparable & (np.abs(coords[indices,2]-observed)<=tolerance)
    counts=(indices[agree],len(indices),int(comparable.sum()))
    return (*counts,cols[agree],rows[agree]) if return_pixels else counts


def depth_coverage_across_views(source,targets,*,voxel_size_m,stride=4):
    """Measure agreement with an ordered set of depth observations in one common pose chart."""
    import numpy as np
    if not np.isfinite(voxel_size_m) or voxel_size_m<=0 or type(stride) is not int or stride<1:
        raise ValueError("Invalid evidence sampling policy")
    xyz,pose=_source_points(source,stride)
    supported=np.zeros(len(xyz),dtype=bool)
    views=[]
    for target in targets:
        agreed,projected,comparable=_depth_support(xyz,pose,target,voxel_size_m)
        supported[agreed]=True
        views.append(dict(projected_pixels=projected,comparable_depths=comparable,shared_samples=len(agreed)))
    return dict(source_samples=len(xyz),covered_samples=int(supported.sum()),views=views,
                tolerance_m=voxel_size_m,sampling_stride=stride)


def shared_depth_samples(source, target, *, voxel_size_m, stride=4):
    """Count sampled points consistent with a measured surface in both camera views."""
    coverage=depth_coverage_across_views(source,(target,),voxel_size_m=voxel_size_m,stride=stride)
    return dict(source_samples=coverage["source_samples"],**coverage["views"][0],
                tolerance_m=voxel_size_m,sampling_stride=stride)


def _bound_depth_pair(old_reader, current_reader, source_uid, current):
    """Use only the requested history revision and the exact, independently bound host view."""
    if (old_reader.identity["episode_uid"]!=current.episode_uid or current_reader.identity["episode_uid"]!=current.episode_uid
            or old_reader.snapshot_id!=current.snapshot_id or current_reader.snapshot_id!=current.source_snapshot_id):
        raise IntegrityError("Photo support crossed an episode or snapshot")
    if old_reader.cutoff["capture_seq"]>current.capture_seq or current_reader.cutoff["capture_seq"]!=current.capture_seq:
        raise IntegrityError("Photo support requires a historical cutoff and the exact current publication")
    def frame(reader,uid):
        row=reader.get_view(uid,include_images=False,include_depth=True)
        if (row["frame_uid"]!=uid or row["capture"]["frame_uid"]!=uid or row["snapshot_id"]!=reader.snapshot_id
                or row["capture"]["episode_uid"]!=current.episode_uid or row["capture_seq"]>reader.cutoff["capture_seq"]):
            raise IntegrityError("Unbound RGB-D support source")
        return row
    old=frame(old_reader,source_uid);new=frame(current_reader,current.frame_uid)
    if old['capture_seq']>=current.capture_seq or new['capture_seq']!=current.capture_seq:
        raise IntegrityError("Invalid temporal order in photo support")
    version=old_reader.versions['pose_map_version']
    result=dict(source_frame=source_uid,current_frame=current.frame_uid,source_snapshot=old_reader.snapshot_id,
                current_snapshot=current_reader.snapshot_id,pose_map_version=version,shared_samples=0)
    if current.pose_map_version!=version or any(row.get('pose_map_version')!=version for row in (old,new)):
        return dict(result,status='pose_version_unavailable'),None,None
    if any(row.get('depth') is None or row.get('T_G_cv') is None or row['capture'].get('K') is None for row in (old,new)):
        return dict(result,status='rgbd_unavailable'),None,None
    def measured(row):
        return dict(depth=row['depth']['aligned_depth'],valid=row['depth']['valid_mask'],
                    K=row['capture']['K'],pose=row['T_G_cv'])
    return result,measured(old),measured(new)


def approach_photo_support(old_reader, current_reader, source_uid, current):
    result,old,new=_bound_depth_pair(old_reader,current_reader,source_uid,current)
    if old is None:
        return result
    counts=shared_depth_samples(old,new,voxel_size_m=float(old_reader._graph['geometry_state']['voxel_size']))
    return dict(result,**dict(counts,status='shared_surface_samples' if counts['shared_samples'] else 'no_shared_surface_samples'))


def observed_door_support(old_reader, current_reader, source_uid, current,*,locate=False):
    """Measure each archived door proposal against the exact current camera depth, once per frame pair.

    Proposal indices identify raw 2D observations within source_uid. Surface agreement does not assign
    a physical instance, establish that a door is open, or determine traversal order.
    """
    import numpy as np
    binding,source,target=_bound_depth_pair(old_reader,current_reader,source_uid,current)
    binding.pop("shared_samples")
    evidence=old_reader.get_observed_doors(source_uid)
    if evidence.get("snapshot_id")!=binding["source_snapshot"] or evidence.get("frame_uid")!=source_uid:
        raise IntegrityError("Door evidence does not belong to the pinned source")
    if evidence["status"]!="available":
        return dict(binding,status=evidence["status"],regions=())
    if source is None:
        return dict(binding,regions=())
    if tuple(evidence["image_hw"])!=source["depth"].shape:
        raise IntegrityError("Door mask and depth image grids differ")
    tolerance=float(old_reader._graph["geometry_state"]["voxel_size"])
    regions=[]
    for ordinal in range(evidence["count"]):
        packed=evidence["door_mask_bits"][ordinal]
        mask=np.unpackbits(packed,axis=1,count=source["depth"].shape[1],bitorder="little").astype(bool)
        masked=dict(source,valid=source["valid"] & mask)
        if locate:
            xyz,pose=_source_points(masked,4)
            agreed,projected,comparable,u,v=_depth_support(xyz,pose,target,tolerance,return_pixels=True)
            counts=dict(source_samples=len(xyz),projected_pixels=projected,comparable_depths=comparable,
                        shared_samples=len(agreed),tolerance_m=tolerance,sampling_stride=4,
                        supported_xyxy=None if not len(u) else [int(u.min()),int(v.min()),int(u.max())+1,int(v.max())+1])
        else:counts=shared_depth_samples(masked,target,voxel_size_m=tolerance)
        regions.append(dict(proposal_index=int(evidence["door_proposal_indices"][ordinal]),
                            xyxy=tuple(map(float,evidence["door_xyxy"][ordinal])),
                            detector_confidence=float(evidence["door_confidence"][ordinal]),**counts))
    return dict(binding,status="available",regions=tuple(regions),**({"current_hw":list(target["depth"].shape)} if locate else {}))


def selected_object_position(reader, current_reader, current, attachment, card, vocabulary):
    """Bind a selected historical detection to its unique active, class-consistent box."""
    from ..visualization import box_corners
    from .host_input_compiler import relative_spatial_fact
    if (reader.snapshot_id!=current.snapshot_id or current_reader.snapshot_id!=current.source_snapshot_id
            or any(r.identity["episode_uid"]!=current.episode_uid for r in (reader,current_reader))
            or reader.cutoff["capture_seq"]>current.capture_seq or current_reader.cutoff["capture_seq"]!=current.capture_seq):
        raise IntegrityError("Unbound object-position reader")
    slot=attachment.slot
    if slot.source_snapshot_id!=reader.snapshot_id or slot.sensor_seq>=current.capture_seq or slot.sensor_seq>reader.cutoff["capture_seq"]:
        raise IntegrityError("Unbound landmark photograph")
    member,=attachment.record.source_refs
    uid,sep,index=member.rpartition(":d")
    if not sep or uid!=slot.frame_uid or not index.isdecimal() or card.observed_step!=slot.env_step:
        raise IntegrityError("Object member and selected source photo differ")
    graph=reader._graph
    owners=[e for e in graph["entities"] if e["status"]=="active" and member in e["members"]]
    if len(owners)!=1:
        return None
    obj=owners[0]
    if (obj["epoch"]!=graph["scene_state"]["epoch"] or
            (uid,obj["id"]) not in map(tuple,graph["vsm"]["visibility_edges"])):
        return None
    attrs=obj.get("attributes")
    if not attrs or attrs.get("class_name")!=card.landmark or not attrs.get("bbox"):
        return None
    # The fused center covers all associated detections, not only the selected class.
    ids=set(attrs.get("class_id",()))
    if len(ids)!=1 or next(iter(ids))!=vocabulary.labels.index(card.landmark):
        return None
    row=current_reader.get_view(current.frame_uid,include_images=False,include_depth=False)
    if (row["capture"]["episode_uid"]!=current.episode_uid or row["frame_uid"]!=current.frame_uid
            or row["capture_seq"]!=current.capture_seq or row["snapshot_id"]!=current.source_snapshot_id):
        raise IntegrityError("Wrong current camera for object position")
    if (obj.get("pose_map_version")!=reader.versions["pose_map_version"]
            or row.get("pose_map_version")!=current.pose_map_version):
        return None
    center,_=box_corners(attrs["bbox"])
    fact=relative_spatial_fact(center,entity_pose_version=obj.get("pose_map_version"),current_T_G_cv=row.get("T_G_cv"),
                               current_pose_version=current.pose_map_version,source_slot=slot.index,source_ref=member)
    if fact is None:return None
    x,y,z=fact.relative_current_cv
    fields=dict(right_m=round(x,1),forward_m=round(z,1))
    source=dict(member=member,epoch=obj["epoch"],object_id=obj["id"],source_snapshot=reader.snapshot_id,
                current_snapshot=current.source_snapshot_id,pose_version=fact.pose_map_version,center_G=center.tolist())
    return fields,source
