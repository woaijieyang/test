"""Update the decision-scoped context and manage event-triggered reads."""

from dataclasses import dataclass
import json
import math
from ..storage.archive import IntegrityError
from dataclasses import field


@dataclass(frozen=True)
class ContextWindow:
    fields: dict
    provenance: dict

    def render(self):
        return '\nHistorical graph record:\n'+json.dumps(self.fields,separators=(',',':'),allow_nan=False)


def build_window(reader,current,lower_seq,attachment=None):
    """Read the recorded path since the previous decision boundary, up to the pin."""
    cutoff=reader.cutoff['capture_seq']
    if reader.identity['episode_uid']!=current.episode_uid or current.snapshot_id!=reader.snapshot_id or cutoff>current.capture_seq:
        raise IntegrityError('Context window crossed episode, snapshot or current observation')
    if type(lower_seq)is not int or not 0<=lower_seq<=cutoff:raise IntegrityError('Invalid previous publication cutoff')
    start=max(1,lower_seq)
    trace=reader.get_trace(start+1,cutoff) if cutoff>start else ()
    fields={'as_of_step':current.env_step}
    refs={'history_snapshot':reader.snapshot_id,'current_source_snapshot':current.source_snapshot_id,'cutoff':cutoff,
          'map_version':reader.versions['pose_map_version'],'edges':[]}
    if trace:
        previous=None;visited=[];length=0.;forward=0;turns=[];blocked=0
        if len(trace)!=cutoff-start:raise IntegrityError('Incomplete recorded primitive interval')
        for ordinal,e in enumerate(trace,start+1):
            pre,post=e['pre'],e['post']
            source=reader.get_retrieval_view(pre);target=reader.get_retrieval_view(post)
            temporal=e['motion']['temporal']
            if (source is None or target is None or source.capture_seq!=ordinal-1 or target.capture_seq!=ordinal
                    or source.episode_uid!=current.episode_uid or target.episode_uid!=current.episode_uid
                    or (pre,post,'temporal_next')!=(temporal['src'],temporal['dst'],temporal['type'])
                    or (previous is not None and previous!=pre)):
                raise IntegrityError('Unverified temporal link in graph context')
            if not visited:visited.append(source)
            visited.append(target);previous=post
            refs['edges'].append(temporal['id'])
            a=e['action'];mov=e['motion'].get('traversed')
            if mov is not None:
                distance=mov['estimated_translation_m']
                if (mov['src'],mov['dst'],mov['type'])!=(pre,post,'traversed') or a['action_id']!=1 or a['collision'] is not False or not math.isfinite(distance) or distance<=0:
                    raise IntegrityError('Unverified traversed link in graph context')
                length+=distance;forward+=1;refs['edges'].append(mov['id'])
            if a['action_id'] in (2,3) and a['collision'] is False:turns.append('left' if a['action_id']==2 else 'right')
            if a['collision'] is True:blocked+=1
        part=dict(from_step=visited[0].env_step,to_step=visited[-1].env_step)
        if forward:part['recorded_forward_m']=round(length,1)
        if turns:part['executed_turn_primitives']=turns
        if blocked:part['recorded_collisions']=blocked
        if len(part)>2:fields['recent_path']=part
    if attachment is not None:
        anchor=reader.get_retrieval_view(attachment.slot.frame_uid)
        if (anchor is None or anchor.snapshot_id!=reader.snapshot_id or anchor.episode_uid!=current.episode_uid
                or anchor.capture_seq>=current.capture_seq or anchor.capture_seq>cutoff):
            raise IntegrityError('Memory anchor is not available at this decision')
        refs['anchor']=anchor.frame_uid
        if (anchor.position is not None and current.position is not None and current.pose_map_version is not None
                and anchor.pose_map_version==current.pose_map_version==reader.versions['pose_map_version']):
            distance=math.dist(anchor.position,current.position)
            if not math.isfinite(distance):raise IntegrityError('Invalid position evidence')
            fields['distance_to_historical_camera_m_estimate']=round(distance,1)
    return ContextWindow(fields,refs)


class WindowCursor:
    def __init__(self):
        self.identity=None;self.seq=0;self.view=None;self.start=0;self.revision=None
    def bind(self,episode,instance,frame,snapshot,cutoff):
        identity=(episode,instance)
        if self.identity!=identity:
            self.__init__();self.identity=identity
        if cutoff<self.seq:raise IntegrityError('Visible publication cutoff regressed')
        if self.view!=frame:self.start=self.seq
        self.view=frame;self.seq=cutoff;self.revision=snapshot
        return self.start


@dataclass
class LandmarkDelivery:
    """Track source records consumed by generate during one native reasoning interval."""
    scope: tuple
    sources: set = field(default_factory=set)

    @staticmethod
    def evidence_key(policy,source_refs,owner,label):
        if policy=='once_per_reasoning':return source_refs
        if (policy!='object_once_per_reasoning' or not owner or owner.get('member') not in source_refs
                or not isinstance(owner.get('epoch'),str) or type(owner.get('object_id')) is not int
                or not isinstance(label,str) or not label):
            raise IntegrityError('Object delivery needs a verified owner and source class')
        return owner['epoch'],owner['object_id'],label

    @classmethod
    def for_decision(cls, previous, episode_uid, instance, reasoning_event):
        scope = (episode_uid, instance, reasoning_event)
        return previous if previous is not None and previous.scope == scope else cls(scope)


@dataclass
class DecisionGate:
    session: tuple | None = None
    last_endpoint: str | None = None
    blocked: bool = False
    active_event: str | None = None
    last_reasoning_event: int | None = None
    consumed_events: set = field(default_factory=set)
    delivered: set = field(default_factory=set)

    def trigger(self, session, uid, action, reasoning_event):
        if self.session != session:
            self.session=session
            self.last_endpoint=None
            self.active_event=None
            self.last_reasoning_event=None
            self.blocked=False
            self.consumed_events.clear()
            self.delivered.clear()
        if uid!=self.last_endpoint:
            collided=action.get('action_id')==1 and action.get('collision') is True
            self.active_event=('forward_collision:'+uid) if collided and not self.blocked else None
            self.blocked=collided
            self.last_endpoint=uid
        if reasoning_event is not None and reasoning_event!=self.last_reasoning_event:
            self.active_event='native_reasoning:'+str(reasoning_event)
            self.last_reasoning_event=reasoning_event
        return self.active_event

    def consume_event(self,event):
        if not event or event!=self.active_event or event in self.consumed_events:
            return False
        self.consumed_events.add(event)
        return True


@dataclass(frozen=True)
class HistoricalMotion:
    slots: tuple
    source_ref: str
    turns: tuple
    forward_metres: float

    def render(self):
        turns = ', then '.join(f'{direction} {degrees} degrees' for direction,degrees in self.turns)
        return (f'Between images {self.slots[0]} and {self.slots[1]}, '
                f'recorded turns: {turns}. Recorded forward travel: about {self.forward_metres:.1f} m.')


def motion_between_slots(slot_frames, executions, *, turn_degrees, cutoff):
    """Take the latest completed slot interval with rotation and verified motion.

    All start/end identities come from the selected public views. Use existing
    primitive order, turn calibration and traversed-edge distances. Missing,
    discontinuous or blocked motion cannot substantiate this historical summary.
    """
    import math
    if not (type(turn_degrees) in (float,int) and math.isfinite(turn_degrees) and 0<turn_degrees<=180):
        raise IntegrityError('Invalid static turn calibration')
    edges_by_post={}
    for e in executions:
        if e['post'] in edges_by_post:
            raise IntegrityError('Two recorded primitives end at the same frame')
        edges_by_post[e['post']]=e
    real=[(i,uid,seq)for i,uid,seq in slot_frames if uid is not None and seq<=cutoff]
    if any(a[2]>=b[2] for a,b in zip(real,real[1:])):
        raise IntegrityError('Historical motion intervals require ordered real images')
    for (j,start,lo),(k,end,hi) in reversed(list(zip(real,real[1:]))):
        curr=end; path=[]
        for _ in range(hi-lo):
            edge=edges_by_post.get(curr)
            if edge is None:break
            path.append(edge);curr=edge['pre']
        if len(path)!=hi-lo or curr!=start:continue
        rotations=[];distance=0.;previous=None
        for e in reversed(path):
            action=e['action']['action_id']; motion=e['motion']
            temporal=motion['temporal']
            if (temporal['src'],temporal['dst'],temporal['type'])!=(e['pre'],e['post'],'temporal_next'):
                raise IntegrityError('Motion record/temporal endpoint mismatch')
            if action in (2,3) and e['action'].get('collision') is False:
                side='left' if action==2 else 'right'
                if action==previous:
                    rotations[-1]=(side,rotations[-1][1]+turn_degrees)
                else:rotations.append((side,turn_degrees))
            elif action==1 and e['action'].get('collision') is False and motion.get('traversed'):
                t=motion['traversed']
                if (t['src'],t['dst'],t['type'])!=(e['pre'],e['post'],'traversed'):
                    raise IntegrityError('Motion record/traversed endpoint mismatch')
                length=t['estimated_translation_m']
                if not math.isfinite(length) or length<=0:raise IntegrityError('Invalid travel distance')
                distance+=length
            else:break
            previous=action
        else:
            if rotations and len(rotations)<=3 and distance>0:
                return HistoricalMotion((j,k),start+'..'+end,tuple(rotations),round(distance,6))
    return None



def side_depth_change(before,after,*,voxel_size_m):
    """Compare measured optical-z on the same two image ray bands across a forward primitive.

    Inputs are public observation/depth products. This observation alone has no room,
    doorway, target or navigability semantics.
    """
    import numpy as np
    from poseAdapter.coordinate.transforms import checked_transform
    if not np.isfinite(voxel_size_m) or voxel_size_m<=0:raise ValueError("Invalid voxel size")
    a,b=before["packet"],after["packet"]
    if a["episode_uid"]!=b["episode_uid"] or a["capture_seq"]+1!=b["capture_seq"] or a["env_step"]+1!=b["env_step"]:
        raise IntegrityError("Side-depth interval is not consecutive in the same episode")
    if b["action"]["action_id"]!=1 or b["action"]["collision"] is not False:return None
    old,new=a["pose_record"],b["pose_record"]
    if (not old["valid"] or not new["valid"] or old["episode_instance"]!=new["episode_instance"]
            or old["map_version"]!=new["map_version"] or old["source"]!=new["source"]):
        return None
    K=np.asarray(a["K"],float)
    if not a["calibration_hash"] or not np.array_equal(K,np.asarray(b["K"],float)) or a["calibration_hash"]!=b["calibration_hash"]:return None
    if K.shape!=(3,3) or not np.isfinite(K).all() or min(K[0,0],K[1,1])<=0:raise IntegrityError("Invalid side-depth camera")
    T=np.linalg.solve(checked_transform(old["T_map_camera_cv"]),checked_transform(new["T_map_camera_cv"]))
    if not np.allclose(T[:3,:3],np.eye(3),atol=1e-5,rtol=0) or T[2,3]<=0 or np.linalg.norm(T[:2,3])>voxel_size_m:return None
    z0,z1=(np.asarray(x["depth"]) for x in (before,after))
    v0,v1=(np.asarray(x["valid"]) for x in (before,after))
    if (z0.ndim!=2 or z1.shape!=z0.shape or any(v.shape!=z0.shape or v.dtype!=np.bool_ for v in (v0,v1))):
        raise IntegrityError("Incompatible aligned depth grids")
    h,w=z0.shape
    # Outer image strips with a small vertical window around the principal ray.
    cy=int(round(K[1,2]));half=max(1,h//32); y=slice(max(0,cy-half),min(h,cy+half+1))
    sides={}
    for side,lo,hi in (("left",1,3),("right",13,15)):
        cols=slice(lo*w//16,hi*w//16)
        areas=[]
        for z,mask in ((z0,v0),(z1,v1)):
            strip=z[y,cols];valid=mask[y,cols] & np.isfinite(strip) & (strip>0)
            if strip.size==0 or not valid.any() or valid.sum()*2<strip.size:return None
            areas.append(np.quantile(strip[valid],[.25,.5,.75]))
        old_q,new_q=areas
        if new_q[0] <= old_q[2]+voxel_size_m:continue
        sides[side]=[round(float(old_q[1]),1),round(float(new_q[1]),1)]
    if not sides:return None
    return dict(from_step=a["env_step"],to_step=b["env_step"],optical_depth_m=sides)

    
def read_side_depth_change(reader, execution):
    """Resolve one previously executed movement against its pinned geometry and immutable RGB-D sources."""
    edge=execution["motion"].get("traversed")
    if edge is None:return None
    pre,post=execution["pre"],execution["post"]
    if (edge["src"],edge["dst"],edge["type"])!=(pre,post,"traversed"):
        raise IntegrityError("Side-depth query has an unbound traversal")
    samples=[]
    for uid in (pre,post):
        view=reader.get_view(uid,include_images=False,include_depth=True)
        p=view["capture"]
        if (view["frame_uid"]!=uid or p["frame_uid"]!=uid or view["snapshot_id"]!=reader.snapshot_id
                or p["episode_uid"]!=reader.identity["episode_uid"] or p["capture_seq"]!=view["capture_seq"]
                or p["capture_seq"]>reader.cutoff["capture_seq"] or p["event_seq"]>reader.cutoff["event_seq"]):
            raise IntegrityError("Depth evidence outside the publication")
        if (view.get("depth") is None or p["pose_record"]["map_version"]!=reader.versions["pose_map_version"]
                or view.get("pose_map_version")!=reader.versions["pose_map_version"]):
            return None
        samples.append(dict(packet=p,depth=view["depth"]["aligned_depth"],valid=view["depth"]["valid_mask"]))
    if samples[-1]["packet"]["action"]!=execution["action"]:
        raise IntegrityError("Snapshot action differs from capture")
    fields=side_depth_change(*samples,voxel_size_m=float(reader._graph["geometry_state"]["voxel_size"]))
    if fields is None:return None
    return dict(fields=fields,source=dict(snapshot_id=reader.snapshot_id,from_frame=pre,to_frame=post,edge=edge["id"]))
