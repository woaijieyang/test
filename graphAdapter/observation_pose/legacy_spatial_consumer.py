"""Prepare and commit geometric views without rewriting ST semantics or online logs."""
from collections import deque
from dataclasses import asdict
import threading,time
from poseAdapter.coordinate.transforms import raw_to_harness,yaw

class PreparedChanges:
    def __init__(self):self.changes=[];self.applied=[]
    def set(self,obj,name,value):
        self.changes.append((obj,name,getattr(obj,name),value))
    def apply(self):
        try:
            for obj,name,old,new in self.changes:
                setattr(obj,name,new);self.applied.append((obj,name,old))
        except Exception:
            self.rollback();raise
    def rollback(self):
        for obj,name,old in reversed(self.applied):setattr(obj,name,old)
        self.applied=[]

class HarnessSpatialState:
    def __init__(self,adapter,harness):
        self.adapter=adapter;self.h=harness;self.owner_thread=threading.get_ident()

    def prepare(self,geometry):
        if threading.get_ident()!=self.owner_thread:raise RuntimeError("Harness geometry must publish on its control thread")
        started=time.monotonic();self.last_prepare_timings={}
        h=self.h;adapter=self.adapter;changes=PreparedChanges()
        geometry.validate_references()
        def pose_for(key):
            from poseAdapter import Pose
            if key not in geometry.bindings:raise ValueError("Spatial state has no source binding: "+key)
            matrix=raw_to_harness(geometry.resolve(geometry.bindings[key]))
            return Pose(*[float(x) for x in matrix[:3,3]],yaw(matrix))
        metadata={}
        for key,meta in h.memory.observation_meta.items():
            if not meta.get("pose_estimate"):raise ValueError("Native historical observation lacks pose provenance")
            from poseAdapter import PoseEstimate
            estimate=geometry.corrected_estimate(PoseEstimate.from_record(meta["pose_estimate"]))
            metadata[key]={**meta,"pose":asdict(estimate.planar()),"pose_estimate":estimate.to_record()}
        changes.set(h.memory,"observation_meta",metadata)
        places={k:{**v,"pose":asdict(pose_for("place:"+k))} for k,v in h.graph.places.items()}
        entities={k:({**v,"position":asdict(pose_for("entity:"+k))} if v.get("position") is not None else dict(v))
                  for k,v in h.graph.entities.items()}
        changes.set(h.graph,"places",places);changes.set(h.graph,"entities",entities)
        for key,target in {**getattr(h,"retired_targets",{}), **h.targets}.items():
            if target.position is not None:changes.set(target,"position",pose_for("target:"+key))
        events=[{**event,"pose":asdict(pose_for("event:"+event["id"]))} for event in h.memory.events]
        event_map={event["id"]:event for event in events}
        feedback=deque((event_map[event["id"]] for event in h.memory.feedback),maxlen=h.memory.feedback.maxlen)
        changes.set(h.memory,"events",events);changes.set(h.memory,"feedback",feedback)
        observed={}
        for ob in [*h.observations.values(),*h.memory.working,*h.views]:observed[id(ob)]=ob
        for ob in observed.values():
            if ob.pose_estimate is None:raise ValueError("Cached native observation lacks pose provenance")
            estimate=geometry.corrected_estimate(ob.pose_estimate)
            changes.set(ob,"pose_estimate",estimate);changes.set(ob,"pose",estimate.planar())
        for attr,key in [("observation_anchor","anchor:observation"),("decision_anchor","anchor:decision")]:
            if getattr(h,attr) is not None:changes.set(h,attr,pose_for(key))
        if h.orchestrator is not None:
            o=h.orchestrator
            for attr,key in [("anchor","orchestrator:anchor"),("last_scan_pose","orchestrator:last_scan")]:
                if getattr(o,attr) is not None:changes.set(o,attr,pose_for(key))
            if o.last_stop_rejection is not None:
                changes.set(o,"last_stop_rejection",{**o.last_stop_rejection,"pose":asdict(pose_for("orchestrator:stop_rejection"))})
            if o.intent is not None and o.intent.get("position") is not None:
                changes.set(o,"intent",{**o.intent,"position":asdict(pose_for("orchestrator:intent"))})
            routes=[{**route,**adapter.route_geometry(route.get("pose_route_id"),geometry=geometry)} for route in o.failed_routes]
            changes.set(o,"failed_routes",routes)
        # Reuse original raycasting/floor/collision rules on separate state.
        self.last_prepare_timings["history_geometry_ms"]=(time.monotonic()-started)*1000
        map_started=time.monotonic()
        try:rebuilt=adapter._map_journal.rebuild(geometry,h.observation)
        finally:self.last_prepare_timings["occupancy_rebuild_ms"]=(time.monotonic()-map_started)*1000
        summary=adapter._map_journal.summary()
        update=summary.get("last_rebuild",{})
        for key in ("mode","changed_entries","affected_cells"):
            if key in update:self.last_prepare_timings["map_rebuild_"+key]=update[key]
        self.last_prepare_timings["map_cache_bytes"]=summary.get("cache_bytes",0)
        rebuilt.pose_map_version=geometry.version
        changes.set(h,"map",rebuilt);changes.set(h.executor,"map",rebuilt)
        for attr in ["frontiers","candidate_actions","probe_candidates"]:changes.set(h,attr,{})
        changes.set(h,"pose_map_version",geometry.version)
        return changes


def bind_legacy_consumer(adapter,host):
    """Explicit external compatibility adapter; no host object is retained by the pose core."""
    adapter.initialize_map_journal(host.map)
    host.pose_map_version=adapter.spatial_bindings()["map_version"]
    host.map.pose_map_version=host.pose_map_version
    adapter.attach_spatial_consumer(HarnessSpatialState(adapter,host))
    if adapter.get_status()["observation_cache"] is None:
        adapter.configure_observation_cache(host.output/"pose-decode-cache")
