"""Bounded async tests using real frozen MemoryWorkerClient methods, local RPC."""
import copy,hashlib,json,sys,threading
from pathlib import Path
from dataclasses import replace
import pytest
sys.path.insert(0,str(Path(__file__).parent))
from test_continuous_graph import item
from poseAdapter.interfaces.mapping import CorrectionSnapshot
from graphAdapter.map_memory.worker import MemoryWorkerClient
from graphAdapter.map_memory.async_admission import (AsyncObservationChannel,FrozenObservation,FrozenCorrection,AdmissionFull,ConsumerFailed)

def visual(n):
 p,a,m=item(n);pose=p.to_record()["pose_record"]
 pose.update(valid=False,tracking_state="unobservable",geometry_status="unavailable",T_map_camera_cv=None)
 p=replace(p,pose_record=pose)
 a["committed_receipt"]["packet_record_hash"]=hashlib.sha256(json.dumps(p.to_record(),sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
 return p,a,None

class LocalRPC:
 def __init__(self,*,gate=None,fail_seq=None,close_error=False,noop=False):
  self.gate=gate;self.entered=threading.Event();self.fail_seq=fail_seq;self.close_error=close_error;self.noop=noop
  self.calls=[];self.commits=[];self.closed=False;self.ended=False;self.prepared=None
  self.client=MemoryWorkerClient.__new__(MemoryWorkerClient)
  self.client.profile={"pose_input_mode":"continuous"};self.client.active_episode="unit";self.client.count=0
  self.client.lifecycle_session=None;self.client.routing=None
  self.client._begin_episode=lambda p:setattr(self.client,"active_episode",p.episode_uid)
  self.client.call=lambda message:json.loads(json.dumps(self.dispatch(copy.deepcopy(message))))
 def dispatch(self,m):
  self.calls.append(m)
  if m["op"]=="prepare":
   p=m["packet"];self.entered.set()
   if self.gate is not None:assert self.gate.wait(3),"test gate timed out"
   if p["capture_seq"]==self.fail_seq:raise RuntimeError("backend failed frame "+str(self.fail_seq))
   sample=m.get("mapping_sample");version=sample["native_map_version"]if sample is not None else p["pose_record"].get("map_version")
   self.prepared=(p,version)
   return {"result":{"duplicate":False,"target_pose_map_version":version,"candidate_hash":"prepared","mapping_correction_applied":False}}
  if m["op"]=="prepare_correction":
   if self.noop:return {"result":dict(self.last_reply,duplicate=True)}
   p=self.prepared[0];version=m["correction"]["native_map_version"];self.prepared=(p,version)
   return {"result":{"duplicate":False,"frame_uid":p["frame_uid"],"target_pose_map_version":version,"candidate_hash":"correction"}}
  if m["op"]=="commit":
   p,version=self.prepared;self.commits.append(p["capture_seq"])
   sid=hashlib.sha256(json.dumps([p["frame_uid"],version,len(self.commits)]).encode()).hexdigest()
   self.last_reply={"snapshot_id":sid,"versions":{"pose_map_version":version},"cutoff":{"capture_seq":p["capture_seq"],"event_seq":p["event_seq"]},
    "frame_uid":p["frame_uid"],"source_packet_event_seq":p["event_seq"]}
   return {"result":self.last_reply}
  if m["op"]=="end_episode":self.ended=True;return {"result":{"ended":True}}
  raise AssertionError(m["op"])
 def consume(self,*a,**k):return self.client.consume(*a,**k)
 def flush_mapping_correction(self,*a,**k):return self.client.flush_mapping_correction(*a,**k)
 def end_episode(self,*a,**k):return self.client.end_episode(*a,**k)
 def close(self,**k):
  self.closed=True
  if self.close_error:raise OSError("resource release failed")

def channel(backend,capacity=3):
 c=AsyncObservationChannel(backend,capacity=capacity,max_episode_observations=20)
 c.begin_episode("unit","attempt-a");return c
def submit(c,n):
 p,a,m=item(n)
 return c.submit_observation(p,a["committed_receipt"],mapping_sample=m,episode_instance="attempt-a")
def finish(c):
 c.seal_episode(correction=None);done=c.drain(3);c.end_episode();return done

def test_real_client_fifo_commit_receipts_and_end_drain():
 b=LocalRPC();c=channel(b)
 try:
  a1=submit(c,1);a2=submit(c,2);done=finish(c)
  assert [x.admission.ordinal for x in done]==[a1.ordinal,a2.ordinal]
  assert [x.publication()["capture_seq"]for x in done]==[1,2]
  assert b.commits==[1,2]and b.ended
  assert all(x.completed_monotonic_ns>=x.admission.submitted_monotonic_ns for x in done)
  assert c.status()["published_seq"]==2
 finally:c.close()
 assert b.closed

def test_capacity_preserves_frozen_retry_and_active_task_is_not_empty():
 gate=threading.Event();b=LocalRPC(gate=gate);c=channel(b,1)
 try:
  submit(c,1);assert b.entered.wait(2)
  p,a,m=item(2)
  with pytest.raises(AdmissionFull)as full:c.submit_observation(p,a["committed_receipt"],mapping_sample=m,episode_instance="attempt-a")
  assert c.status()["admitted_seq"]==1 and c.status()["published_seq"]==0
  assert c.status()["active"]and c.status()["oldest_pending_age_seconds"]>=0
  with pytest.raises(TimeoutError):c.drain(.01)
  gate.set();completed=c.wait_for_capacity(3);assert len(completed)==1
  c.submit_frozen(full.value.frozen_input);done=finish(c)
  assert [x.publication()["capture_seq"]for x in done]==[2]and b.commits==[1,2]
 finally:gate.set();c.close()

def test_background_failure_retains_all_unpublished_and_propagates():
 gate=threading.Event();b=LocalRPC(gate=gate,fail_seq=1);c=channel(b)
 try:
  submit(c,1);submit(c,2);gate.set()
  with pytest.raises(ConsumerFailed):c.drain(3)
  state=c.failure_snapshot();assert len(state["unpublished"])==2
  assert state["failure"]["frame_uid"]==item(1)[0].frame_uid
  state["failure"]["message"]="caller mutation"
  assert c.failure_snapshot()["failure"]["message"]!="caller mutation"
  assert c.poll_completions()==()
 finally:gate.set();c.close()
 assert len(c.failure_snapshot()["unpublished"])==2 and b.closed

def test_none_is_frozen_visual_only_and_session_survives_reset():
 b=LocalRPC();c=channel(b)
 try:
  p,a,_=visual(1)
  old=FrozenObservation.create(p,a["committed_receipt"],mapping_sample=None,episode_instance="attempt-a")
  with pytest.raises(TypeError):FrozenObservation.create(p,a["committed_receipt"],episode_instance="attempt-a")
  c.submit_frozen(old);done=finish(c);assert len(done)==1
  assert next(x for x in b.calls if x["op"]=="prepare")["mapping_sample"]is None
  c.begin_episode("unit","attempt-b")
  with pytest.raises(ValueError,match="session"):c.submit_frozen(old)
  c.seal_episode(correction=None);c.drain(3);c.end_episode()
 finally:c.close()

def test_duplicate_source_frame_rejected_and_end_requires_host_drain():
 b=LocalRPC();c=channel(b)
 try:
  submit(c,1)
  with pytest.raises(ValueError):submit(c,1)
  with pytest.raises(RuntimeError):c.end_episode()
  c.seal_episode(correction=None)
  with pytest.raises(RuntimeError):c.end_episode()
  assert len(c.drain(3))==1;c.end_episode();c.begin_episode("unit","new-session")
  c.seal_episode(correction=None);c.drain(3);c.end_episode()
 finally:c.close()

def test_close_failure_is_visible():
 b=LocalRPC(close_error=True);c=channel(b)
 c.seal_episode(correction=None);c.drain(3);c.end_episode()
 with pytest.raises(ConsumerFailed,match="release"):c.close()
 assert c.failure_snapshot()["close_error"]["error_type"]=="OSError"

def test_duplicate_correction_is_not_a_publication():
 b=LocalRPC(noop=True);c=channel(b)
 try:
  submit(c,1);assert len(c.drain(3))==1
  p,_,m=item(1);target=CorrectionSnapshot(m.episode_id,m.episode_instance,m.frame_id,m.timestamp_ns,m.native_map_version,m.bindings_json,m.odometry_epoch)
  c.seal_episode(correction=target)
  assert c.drain(3)==()and c.status()["noop_corrections"]==1
  c.end_episode()
 finally:c.close()


def test_submit_freezes_packet_receipt_and_mapping_before_producer_advances():
 gate=threading.Event();b=LocalRPC(gate=gate);c=channel(b)
 class Producer:
  def __init__(self):self.current=item(1);self.queries=0
  def snapshot(self):self.queries+=1;return self.current[2]
 producer=Producer()
 try:
  p,a,_=producer.current;record=p.to_record();receipt=copy.deepcopy(a["committed_receipt"])
  frozen=FrozenObservation.create(record,receipt,mapping_sample=producer.snapshot(),episode_instance="attempt-a")
  c.submit_frozen(frozen);assert b.entered.wait(2)
  record["pose_record"]["timestamp_ns"]=999;receipt["committed"]=False
  producer.current=item(2);p2,a2,_=producer.current
  c.submit_observation(p2,a2["committed_receipt"],mapping_sample=producer.snapshot(),episode_instance="attempt-a")
  producer.current=item(99);gate.set();done=finish(c)
  prepared=[x for x in b.calls if x["op"]=="prepare"]
  assert [x["mapping_sample"]["frame_id"]for x in prepared]==[p.frame_uid,p2.frame_uid]
  assert all(x["receipt"]["committed"]is True for x in prepared)
  assert producer.queries==2 and len(done)==2
 finally:gate.set();c.close()

def test_correction_identity_checked_immediately_and_visual_older_time_allowed():
 p,_,m=item(1)
 target=CorrectionSnapshot(m.episode_id,m.episode_instance,m.frame_id,m.timestamp_ns,m.native_map_version,m.bindings_json,m.odometry_epoch)
 p2,_,_=item(2)
 with pytest.raises(ValueError,match="frame"):FrozenCorrection.create(p2,target)
 visual_p,_,_=visual(2)
 older=CorrectionSnapshot(m.episode_id,m.episode_instance,visual_p.frame_uid,m.timestamp_ns,m.native_map_version,m.bindings_json,None)
 assert FrozenCorrection.create(visual_p,older).correction.timestamp_ns==1
 future=CorrectionSnapshot(m.episode_id,m.episode_instance,visual_p.frame_uid,3,m.native_map_version,m.bindings_json,None)
 with pytest.raises(ValueError,match="timestamp"):FrozenCorrection.create(visual_p,future)

def test_bad_final_correction_does_not_seal_or_emit():
 b=LocalRPC();c=channel(b)
 try:
  submit(c,1);assert len(c.drain(3))==1
  _,_,m=item(2)
  target=CorrectionSnapshot(m.episode_id,m.episode_instance,m.frame_id,m.timestamp_ns,m.native_map_version,m.bindings_json,m.odometry_epoch)
  with pytest.raises(ValueError):c.seal_episode(correction=target)
  assert c.status()["state"]=="active"
  c.seal_episode(correction=None);c.drain(3);c.end_episode()
 finally:c.close()

def test_end_reset_is_atomic_and_closed_channel_cannot_restart():
 b=LocalRPC();c=channel(b)
 for n in range(20):
  c.seal_episode(correction=None);c.drain(3);c.end_episode()
  c.begin_episode("unit","session-"+str(n))
 c.seal_episode(correction=None);c.drain(3);c.end_episode();c.close();c.close()
 with pytest.raises(RuntimeError,match="closed"):c.begin_episode("unit","later")
 assert c.status()["state"]=="closed"

def test_real_async_client_service_visual_only_never_repaired(tmp_path):
 from graphAdapter.map_memory.storage.store import EpisodeStore,load_episode
 from test_service_integration import seeded_service,seed_camera
 from graphAdapter.observation_packet import ObservationPacket
 from poseAdapter.interfaces.mapping import MappingSample
 first,a1,_=visual(1);second,a2,sample=item(2)
 data={first.frame_uid:a1,second.frame_uid:a2}
 class ServiceRPC(LocalRPC):
  def __init__(self):super().__init__();self.store=None;self.service=None;self.creator=None
  def dispatch(self,message):
   if message["op"]=="prepare":
    packet=ObservationPacket(**message["packet"]);args=dict(data[packet.frame_uid])
    if self.store is None:
     self.creator=threading.get_ident();self.store=EpisodeStore(tmp_path/"episode","unit",dataset="r2r")
     self.service=seeded_service(self.store,packet,args)
    else:seed_camera(self.service,packet,args)
    assert self.creator==threading.get_ident()
    args.update(committed_receipt=message["receipt"],bindings=message["bindings"])
    frozen=message["mapping_sample"]
    self.ready=self.service.prepare_endpoint(packet,**args,mapping_sample=None if frozen is None else MappingSample.from_record(frozen))
    return {"result":self.ready}
   if message["op"]=="commit":
    p=self.service.prepared["capture"]if "capture"in self.service.prepared else self.service.prepared["frames"][message["frame_uid"]]
    pointer=self.service.publish_prepared(frame_uid=message["frame_uid"],target_pose_map_version=message["target_pose_map_version"])
    raw=self.service.frames[message["frame_uid"]]
    return {"result":dict(snapshot_id=pointer["snapshot_id"],versions=pointer["versions"],cutoff=pointer["cutoff"],
     frame_uid=raw["frame_uid"],source_packet_event_seq=raw["event_seq"])}
   if message["op"]=="end_episode":
    self.store.close();self.ended=True;return {"result":{"ended":True}}
   raise AssertionError(message["op"])
  def close(self,**kw):
   if self.store is not None:self.store.close()
   self.closed=True
 b=ServiceRPC();c=channel(b)
 try:
  c.submit_observation(first,a1["committed_receipt"],mapping_sample=None,episode_instance="attempt-a")
  c.submit_observation(second,a2["committed_receipt"],mapping_sample=sample,episode_instance="attempt-a")
  c.seal_episode(correction=None);done=c.drain(10)
  reader=load_episode(tmp_path/"episode")
  try:
   assert reader.verify()["views"]==2
   assert reader.get_view(first.frame_uid)["geometry_status"]=="visual_only"
   assert not reader.get_view(first.frame_uid)["geometry_fused"]
   assert reader.get_view(second.frame_uid)["geometry_status"]=="available"
   assert [v.publication()["capture_seq"]for v in done]==[1,2]
  finally:reader.close()
  c.end_episode()
 finally:c.close()
 assert b.closed and b.ended


def test_explicit_correction_fifo_and_delayed_publication_contract():
 from graphAdapter.evaluation.publications import index_publications
 b=LocalRPC();c=channel(b)
 try:
  p,a,m=item(1);submit(c,1)
  bindings=m.bindings;bindings["map_version"]=2
  target=CorrectionSnapshot(m.episode_id,m.episode_instance,p.frame_uid,p.sensor_timestamp_ns,2,
   json.dumps(bindings,sort_keys=True,separators=(",",":")).encode(),m.odometry_epoch)
  c.seal_episode(correction=target);done=c.drain(3)
  assert [x.kind for x in done]==["observation","correction"]
  pubs=[x.publication()for x in done]
  assert pubs[1]["kind"]=="MapCorrectionPublished"
  assert pubs[1]["source_packet_event_seq"]==p.event_seq and pubs[1]["cutoff_event_seq"]==p.event_seq
  endpoints,revisions=index_publications(pubs,{p.frame_uid:p.to_record()})
  assert len(endpoints)==1 and len(revisions)==2
  c.end_episode()
 finally:c.close()

def test_owner_host_poll_and_completion_data_are_private():
 b=LocalRPC();c=channel(b);errors=[]
 try:
  submit(c,1)
  t=threading.Thread(target=lambda:_foreign_poll(c,errors));t.start();t.join()
  assert len(errors)==1 and isinstance(errors[0],RuntimeError)
  c.seal_episode(correction=None);done=c.drain(3)
  r=done[0].result;r["cutoff"]["capture_seq"]=77
  assert done[0].publication()["capture_seq"]==1
  c.end_episode()
 finally:c.close()
def _foreign_poll(c,errors):
 try:c.poll_completions()
 except BaseException as e:errors.append(e)

def test_committed_prefix_not_confused_with_admitted_failed_suffix():
 b=LocalRPC();c=channel(b)
 gate=threading.Event()
 try:
  submit(c,1);assert len(c.drain(3))==1
  b.gate=gate;b.fail_seq=2
  submit(c,2);submit(c,3);gate.set()
  with pytest.raises(ConsumerFailed):c.drain(3)
  s=c.status();assert s["admitted_seq"]==3 and s["published_seq"]==1 and s["pending_count"]==2
  snap=c.failure_snapshot();assert [x["frozen_input"]["packet"]["capture_seq"]for x in snap["unpublished"]]==[2,3]
 finally:gate.set();c.close()

def test_close_does_not_silently_discard_unfinished_frames():
 gate=threading.Event();b=LocalRPC(gate=gate);c=channel(b)
 submit(c,1);assert b.entered.wait(2);submit(c,2)
 timer=threading.Timer(.02,gate.set);timer.start()
 done=c.close();timer.join()
 assert c.status()["state"]=="closed_aborted"
 # Depending on scheduling the current task can finish, but unprocessed work
 # must remain explicitly represented rather than being cleared by close.
 committed={x.admission.frame_uid for x in done}
 pending={x["frozen_input"]["packet"]["frame_uid"]for x in c.failure_snapshot()["unpublished"]}
 assert committed|pending=={item(1)[0].frame_uid,item(2)[0].frame_uid}
 assert not committed&pending



@pytest.mark.parametrize('explicit_force',[False,True])
def test_background_terminal_packet_does_not_implicitly_force_correction(explicit_force):
 from graphAdapter.map_memory.storage.store import canonical
 backend=LocalRPC();backend.client.profile['background_correction']={'enabled':True}
 p,a,m=item(1);p=replace(p,action=dict(p.action,terminal=True))
 receipt=dict(a['committed_receipt'],packet_record_hash=hashlib.sha256(canonical(p.to_record())).hexdigest())
 backend.client.consume(p,receipt,frozen_mapping_sample=m,force_mapping_correction=explicit_force)
 prepare=next(x for x in backend.calls if x['op']=='prepare')
 assert prepare['force_mapping_correction'] is explicit_force
